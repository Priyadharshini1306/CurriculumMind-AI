"""Resource discovery (YouTube + DuckDuckGo), content extraction, version/freshness checks and ranking.

Every network step is isolated: one broken URL, missing transcript or failed search never aborts the run."""
import asyncio
import hashlib
import logging
import re
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse

import httpx

from app.core.config import get_settings

log = logging.getLogger(__name__)

MAX_TEXT_CHARS = 8000
YT_PER_CONCEPT = 3
WEB_PER_CONCEPT = 4
TRANSCRIPTS_PER_CONCEPT = 2

# Editable: oldest still-acceptable major version per technology. Older mentions trigger an "outdated" warning.
MIN_ACCEPTABLE_MAJOR = {"java": 17, "jdk": 17, "spring boot": 3, "python": 3, "angular": 15, "react": 17,
                        "node": 18, "php": 8, "mysql": 8}
FAST_MOVING_MAX_AGE_YEARS = 4
GENERAL_MAX_AGE_YEARS = 8

TRUSTED_HINTS = ("docs.", "documentation", ".edu", "developer.", "oracle.com", "spring.io", "mozilla.org",
                 "python.org", "learn.microsoft.com", "baeldung.com", "geeksforgeeks.org", "w3schools.com",
                 "freecodecamp.org", "khanacademy.org", "ocw.mit.edu", "coursera.org", "github.com")


def canonical_url(url: str) -> str:
    p = urlparse(url.strip())
    host = p.netloc.lower().removeprefix("www.")
    if "youtube.com" in host and p.path == "/watch":
        m = re.search(r"[?&]v=([\w-]{6,})", "?" + p.query)
        if m:
            return f"https://www.youtube.com/watch?v={m.group(1)}"
    return urlunparse(("https", host, p.path.rstrip("/"), "", "", ""))


def resource_id(url: str) -> str:
    return hashlib.sha1(canonical_url(url).encode()).hexdigest()[:20]


def parse_iso_duration(s: str) -> float | None:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    if not m:
        return None
    d, h, mi, sec = (int(x or 0) for x in m.groups())
    return round(d * 1440 + h * 60 + mi + sec / 60, 1)


def estimate_difficulty(text: str) -> int:
    t = text.lower()
    if re.search(r"\b(advanced|expert|deep dive|internals|masterclass)\b", t):
        return 5 if "expert" in t or "internals" in t else 4
    if re.search(r"\b(beginner|beginners|introduction|intro|basics|basic|101|crash course|for dummies|getting started)\b", t):
        return 1 if re.search(r"\b(absolute beginner|for dummies|101)\b", t) else 2
    if re.search(r"\bintermediate\b", t):
        return 3
    return 3


def detect_version_warnings(text: str, published: datetime | None, fast_moving: bool = True) -> tuple[str | None, list[str]]:
    """Returns (version_hint, warnings). Flags old technology versions and old publication dates."""
    warnings, hint = [], None
    for tech, minimum in MIN_ACCEPTABLE_MAJOR.items():
        for m in re.finditer(rf"\b{re.escape(tech)}\s*(?:v|version)?\s*(\d{{1,2}})(?:\.(\d+))?", text.lower()):
            major = int(m.group(1))
            if tech in ("java", "jdk") and major == 1 and m.group(2):  # "Java 1.8" style
                major = int(m.group(2))
            if major > 60:
                continue
            hint = hint or f"{tech.title()} {major}"
            if major < minimum:
                warnings.append(f"Uses {tech.title()} {major} (older than {minimum})")
                break
    if published:
        age = (datetime.now(timezone.utc) - published).days / 365.25
        limit = FAST_MOVING_MAX_AGE_YEARS if fast_moving else GENERAL_MAX_AGE_YEARS
        if age > limit:
            warnings.append(f"Published {age:.0f} years ago; may be outdated")
    return hint, list(dict.fromkeys(warnings))


def freshness_score(published: datetime | None, warnings: list[str]) -> float:
    if published is None:
        base = 0.6
    else:
        age = (datetime.now(timezone.utc) - published).days / 365.25
        base = 1.0 if age <= 1 else 0.8 if age <= 3 else 0.5 if age <= 5 else 0.25
    return base * (0.6 if any("older than" in w for w in warnings) else 1.0)


def source_quality(url: str, source: str) -> float:
    host = urlparse(url).netloc.lower()
    if any(h in host or h in url.lower() for h in TRUSTED_HINTS):
        return 0.9
    return 0.7 if source == "YOUTUBE" else 0.5


def difficulty_fit(resource_difficulty: int, concept_difficulty: int) -> float:
    return max(0.0, 1 - abs(resource_difficulty - concept_difficulty) / 4)


def duration_fit(duration_min: float | None, concept_minutes: int) -> float:
    if not duration_min:
        return 0.6
    ideal = max(concept_minutes, 10)
    if duration_min > ideal * 1.5:
        return max(0.2, ideal * 1.5 / duration_min)
    return 0.7 if duration_min < ideal * 0.2 else 1.0


_STOP = {"and", "the", "of", "in", "to", "a", "an", "for", "with", "java", "programming", "basics", "using"}


def _tokens(s: str) -> set[str]:
    return {w.rstrip("s") for w in re.findall(r"[a-z0-9]+", s.lower()) if w not in _STOP and len(w) > 1}


def lexical_match(concept_name: str, r: dict) -> float:
    """Fraction of the concept-name terms found in the resource title/description/text (guards against embeddings
    that match on the shared course words alone, e.g. every Java page looks similar to every Java concept)."""
    want = _tokens(concept_name)
    if not want:
        return 0.0
    hay = f"{r.get('title', '')} {r.get('description', '')} {(r.get('text') or '')[:2000]}".lower()
    hay_norm = re.sub(r"[^a-z0-9]+", "", hay)
    title = r.get("title", "").lower()
    score = 0.0
    for w in want:
        if w in title:
            score += 1.0
        elif w in hay or w in hay_norm:
            score += 0.6
    return min(1.0, score / len(want))


def relevance(similarity: float, concept_name: str, r: dict) -> float:
    return 0.7 * max(0.0, similarity) + 0.3 * lexical_match(concept_name, r)


def rank_score(similarity: float, r: dict, concept: dict) -> float:
    """Preliminary ranking used before coverage analysis (Phase 11 adds coverage/evidence terms)."""
    return round(
        0.60 * relevance(similarity, concept.get("name", ""), r)
        + 0.12 * difficulty_fit(r.get("difficulty", 3), concept.get("difficulty", 3))
        + 0.12 * freshness_score(r.get("published_at_dt"), r.get("warnings", []))
        + 0.08 * duration_fit(r.get("duration_minutes"), concept.get("estimated_minutes", 60))
        + 0.08 * source_quality(r["url"], r["source"]), 4)


# ------------------------------------------------------------------ search
async def search_youtube(query: str, limit: int = YT_PER_CONCEPT) -> list[dict]:
    key = get_settings().youtube_api_key
    if not key:
        return []
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            s = await c.get("https://www.googleapis.com/youtube/v3/search", params={
                "part": "snippet", "q": query, "type": "video", "maxResults": limit,
                "relevanceLanguage": "en", "videoEmbeddable": "true", "safeSearch": "strict", "key": key})
            s.raise_for_status()
            ids = [i["id"]["videoId"] for i in s.json().get("items", [])]
            if not ids:
                return []
            v = await c.get("https://www.googleapis.com/youtube/v3/videos", params={
                "part": "snippet,contentDetails", "id": ",".join(ids), "key": key})
            v.raise_for_status()
    except (httpx.HTTPError, KeyError, ValueError) as e:
        log.warning("YouTube search failed for %r: %s", query, e)
        return []
    out = []
    for it in v.json().get("items", []):
        sn = it["snippet"]
        out.append({"title": sn["title"], "url": f"https://www.youtube.com/watch?v={it['id']}", "source": "YOUTUBE",
                    "author": sn.get("channelTitle"), "description": sn.get("description", "")[:1000],
                    "duration_minutes": parse_iso_duration(it["contentDetails"]["duration"]),
                    "published_at": sn.get("publishedAt"), "video_id": it["id"]})
    return out


def _ddg_sync(query: str, limit: int) -> list[dict]:
    from ddgs import DDGS
    return DDGS().text(query, max_results=limit) or []


_ddg_gate = asyncio.Semaphore(1)  # DuckDuckGo rate-limits bursts, so searches are serialised
DDG_RETRIES = 3


async def search_web(query: str, limit: int = WEB_PER_CONCEPT) -> list[dict]:
    rows, last = [], None
    for attempt in range(DDG_RETRIES):
        async with _ddg_gate:
            try:
                rows = await asyncio.wait_for(asyncio.to_thread(_ddg_sync, query, limit), timeout=30)
                break
            except Exception as e:
                last = e
            await asyncio.sleep(0.8)
        await asyncio.sleep(2 * (attempt + 1))  # back off outside the gate
    if not rows:
        log.warning("Web search failed for %r: %s", query, last)
        return []
    return [{"title": r.get("title", ""), "url": r["href"], "source": "WEB", "author": None,
             "description": r.get("body", "")[:1000], "duration_minutes": None, "published_at": None}
            for r in rows if r.get("href")]


# ------------------------------------------------------------------ content extraction
def _fetch_page_sync(url: str) -> tuple[str, str | None]:
    import trafilatura
    html = trafilatura.fetch_url(url)
    if not html:
        return "", None
    text = trafilatura.extract(html, include_comments=False, include_tables=False) or ""
    meta = trafilatura.extract_metadata(html)
    return text, (meta.date if meta and meta.date else None)


def _fetch_transcript_sync(video_id: str) -> str:
    from youtube_transcript_api import YouTubeTranscriptApi
    api = YouTubeTranscriptApi()
    tl = api.list(video_id)
    try:
        t = tl.find_transcript(["en", "en-US", "en-GB"])
    except Exception:
        t = next(iter(tl))  # any language / auto-generated
    return " ".join(s.text for s in t.fetch())


async def enrich(r: dict, want_transcript: bool) -> dict:
    """Fill text, published date, difficulty and warnings. Never raises."""
    r = dict(r)
    r["warnings"] = []
    text = ""
    try:
        if r["source"] == "YOUTUBE":
            r["has_transcript"] = False
            if want_transcript:
                try:
                    text = await asyncio.wait_for(asyncio.to_thread(_fetch_transcript_sync, r["video_id"]), 40)
                    r["has_transcript"] = bool(text)
                except Exception:
                    r["warnings"].append("No transcript available")
            else:
                r["warnings"].append("Transcript not fetched")
        else:
            try:
                text, date = await asyncio.wait_for(asyncio.to_thread(_fetch_page_sync, r["url"]), 40)
                if date and not r.get("published_at"):
                    r["published_at"] = date
            except Exception:
                r["warnings"].append("Page could not be fetched")
            if text:
                r["duration_minutes"] = round(len(text.split()) / 200, 1)  # estimated reading time
            else:
                r["warnings"].append("No readable content extracted")
    except Exception as e:  # defensive: enrichment must never crash the run
        log.warning("enrich failed for %s: %s", r.get("url"), e)
    r["text"] = (text or r.get("description", ""))[:MAX_TEXT_CHARS]
    r["published_at_dt"] = _parse_dt(r.get("published_at"))
    r["difficulty"] = estimate_difficulty(f"{r['title']} {r.get('description', '')}")
    hint, vw = detect_version_warnings(f"{r['title']} {r['text'][:3000]}", r["published_at_dt"])
    r["version_hint"] = hint
    r["warnings"] += vw
    r["id"] = resource_id(r["url"])
    return r


def _parse_dt(v) -> datetime | None:
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def dedupe(items: list[dict]) -> list[dict]:
    seen, out = set(), []
    for r in items:
        key = (resource_id(r["url"]), re.sub(r"\W+", "", r["title"].lower()))
        if key[0] in seen or key[1] in seen:
            continue
        seen.update(key)
        out.append(r)
    return out


async def discover(course: str, concept: dict) -> list[dict]:
    """Search both sources for a concept and return enriched, de-duplicated candidates."""
    name = concept["name"]
    yt, web1, web2 = await asyncio.gather(
        search_youtube(f"{course} {name} tutorial"),
        search_web(f"{course} {name} tutorial"),
        search_web(f"{name} {course} documentation"))
    candidates = dedupe(yt + web1 + web2)
    # Only the first few videos get a (slow) transcript fetch.
    video_budget = TRANSCRIPTS_PER_CONCEPT
    tasks = []
    for r in candidates:
        want = False
        if r["source"] == "YOUTUBE" and video_budget > 0:
            want, video_budget = True, video_budget - 1
        tasks.append(enrich(r, want))
    return await asyncio.gather(*tasks)


async def discover_queries(queries: list[str], youtube_queries: int = 1) -> list[dict]:
    """Search targeted queries on the web, and on YouTube for the first `youtube_queries` of them (each YouTube
    search costs 100 API quota units, so it is rationed). Enriched, de-duplicated results."""
    groups = []
    for i, q in enumerate(queries):
        yt, web = await asyncio.gather(search_youtube(q, 2) if i < youtube_queries else asyncio.sleep(0, []),
                                       search_web(q, 3))
        groups += yt + web
    candidates = dedupe(groups)
    video_budget, tasks = 1, []
    for r in candidates:
        want = r["source"] == "YOUTUBE" and video_budget > 0
        video_budget -= 1 if want else 0
        tasks.append(enrich(r, want))
    return await asyncio.gather(*tasks)
