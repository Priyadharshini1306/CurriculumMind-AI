"""Concept -> embedding -> Neo4j vector search -> graph filtering -> ranking -> COVERS links."""
import logging

from app.repositories import neo4j_repository as repo
from app.services import embedding_service, resource_service as rs

log = logging.getLogger(__name__)
MIN_RELEVANCE = 0.52  # blended embedding + term-match score
TOP_N = 5
CANDIDATES = 20


def _text_for_embedding(r: dict) -> str:
    return f"{r['title']}. {r.get('description', '')} {r.get('text', '')[:1500]}".strip()


def _reasons(sim: float, r: dict, concept: dict) -> list[str]:
    out = [f"{sim:.0%} relevant to this topic"]
    if rs.lexical_match(concept["name"], r) >= 0.99:
        out.append("Covers the concept terms directly")
    if rs.difficulty_fit(r.get("difficulty", 3), concept.get("difficulty", 3)) >= 0.75:
        out.append("Difficulty fits the concept")
    if rs.freshness_score(r.get("published_at_dt"), r.get("warnings", [])) >= 0.8:
        out.append("Recent")
    if rs.source_quality(r["url"], r["source"]) >= 0.9:
        out.append("Trusted source")
    out += [w for w in r.get("warnings", []) if "older than" in w or "years ago" in w]
    return out


async def match_concept(course_name: str, concept: dict) -> dict:
    """Discover + store resources for one concept, then rank them via vector search. Returns a summary."""
    found = await rs.discover(course_name, concept)
    if found:
        vecs = await embedding_service.embed([_text_for_embedding(r) for r in found])
        rows = [{**{k: v for k, v in r.items() if k != "published_at_dt"}, "embedding": v,
                 "published_at": r.get("published_at") and str(r["published_at"]),
                 "has_transcript": r.get("has_transcript", False)} for r, v in zip(found, vecs)]
        await repo.upsert_resources(rows)
    hits = await repo.vector_resources(concept["embedding"], CANDIDATES)
    ranked, seen_titles = [], set()
    for h in hits:
        r, sim = h["r"], h["score"]
        r["published_at_dt"] = rs._parse_dt(r.get("published_at"))
        if rs.relevance(sim, concept["name"], r) < MIN_RELEVANCE:
            continue
        key = "".join(c for c in r["title"].lower() if c.isalnum())
        if key in seen_titles:  # duplicate detection across sources
            continue
        seen_titles.add(key)
        r["warnings"] = r.get("warnings") or []
        ranked.append((rs.rank_score(sim, r, concept), sim, r))
    ranked.sort(key=lambda x: -x[0])
    links = [{"resource_id": r["id"], "similarity": round(sim, 4), "rank_score": score, "rank": i + 1,
              "reasons": _reasons(sim, r, concept)} for i, (score, sim, r) in enumerate(ranked[:TOP_N])]
    await repo.link_covers(concept["id"], links)
    return {"concept_id": concept["id"], "discovered": len(found), "linked": len(links)}
