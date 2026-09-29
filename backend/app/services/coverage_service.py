"""Resource analysis: per-resource coverage of a concept's required sub-points, with quoted evidence.

    Coverage % = covered required subtopics / total required subtopics x 100

A required point counts as covered when some window of the resource text is semantically close to it (embedding
cosine) AND shares at least one significant term with it (so an unrelated but generic page cannot cover a point)."""
import json
import logging

from pydantic import BaseModel, Field, field_validator

from app.services import embedding_service, llm_service
from app.services import resource_service as rs

log = logging.getLogger(__name__)

COVERAGE_THRESHOLD = 0.6      # accept a resource / concept at or above this coverage
POINT_SIMILARITY = 0.42       # min cosine between a required point and a text window
MAX_ITERATIONS = 3            # bounded gap-search loop
WINDOW_WORDS, STRIDE_WORDS = 70, 45
MIN_POINTS, MAX_POINTS = 3, 7


class RequiredPoints(BaseModel):
    points: list[str] = Field(min_length=MIN_POINTS)

    @field_validator("points")
    @classmethod
    def clean(cls, v: list[str]) -> list[str]:
        seen, out = set(), []
        for p in v:
            p = " ".join(str(p).split())
            if 2 < len(p) <= 120 and p.lower() not in seen:
                seen.add(p.lower())
                out.append(p)
        if len(out) < MIN_POINTS:
            raise ValueError(f"need at least {MIN_POINTS} distinct required points")
        return out[:MAX_POINTS]


POINTS_SYSTEM = (
    "You are a curriculum expert. List the required subtopics a learner must cover to truly master the given "
    "concept: 4 to 6 concrete, short noun phrases (2-6 words each). Example for HashMap in Java: "
    "put and get operations; hashing and buckets; collision handling; load factor and resizing; iteration; null keys."
)
POINTS_HINT = 'Reply with JSON only, in this shape:\n{"points":["put and get operations","hashing and buckets"]}'


async def required_points(course: str, concept: dict) -> list[str]:
    payload = {"course": course, "concept": concept["name"], "description": concept.get("description", "")}
    res = await llm_service.generate_json(POINTS_SYSTEM, json.dumps(payload), RequiredPoints, temperature=0.2,
                                          schema_hint=POINTS_HINT, num_predict=300)
    return res.points


def chunk_text(text: str) -> list[str]:
    words = text.split()
    if not words:
        return []
    out, i = [], 0
    while i < len(words):
        out.append(" ".join(words[i:i + WINDOW_WORDS]))
        if i + WINDOW_WORDS >= len(words):
            break
        i += STRIDE_WORDS
    return out


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))  # vectors are L2-normalised, so dot == cosine


def _supported(point: str, chunk: str) -> bool:
    terms = rs._tokens(point)
    if not terms:
        return True
    low = chunk.lower()
    return any(t in low for t in terms)


def evaluate(points: list[str], point_vecs: list[list[float]], chunks: list[str],
             chunk_vecs: list[list[float]], has_full_text: bool) -> dict:
    """Pure function: which points does this text cover, with which evidence?"""
    covered, missing, evidence = [], [], []
    for p, pv in zip(points, point_vecs):
        best, best_i = 0.0, -1
        for i, (c, cv) in enumerate(zip(chunks, chunk_vecs)):
            s = _dot(pv, cv)
            if s > best and _supported(p, c):
                best, best_i = s, i
        if best >= POINT_SIMILARITY:
            covered.append(p)
            evidence.append({"point": p, "score": round(best, 3), "snippet": chunks[best_i][:240]})
        else:
            missing.append(p)
    coverage = len(covered) / len(points) if points else 0.0
    evidence_score = sum(e["score"] for e in evidence) / len(evidence) if evidence else 0.0
    confidence = round(evidence_score * (1.0 if has_full_text else 0.6), 3)
    return {"coverage": round(coverage, 3), "evidence": round(evidence_score, 3), "confidence": confidence,
            "covered_points": covered, "missing_points": missing, "evidence_list": evidence}


async def analyze_resource(concept_name: str, points: list[str], point_vecs: list[list[float]], resource: dict) -> dict:
    text = (resource.get("text") or "").strip()
    has_full = len(text) >= 1200
    chunks = chunk_text(text or resource.get("description") or resource.get("title") or "")
    vecs = await embedding_service.embed(chunks) if chunks else []
    res = evaluate(points, point_vecs, chunks, vecs, has_full)
    res["resource_id"] = resource["id"]
    return res


async def embed_points(concept_name: str, points: list[str]) -> list[list[float]]:
    return await embedding_service.embed([f"{concept_name}: {p}" for p in points])


def final_rank(rel: float, coverage: float, evidence: float, r: dict, concept: dict) -> float:
    return round(
        0.30 * rel + 0.30 * coverage + 0.10 * evidence
        + 0.10 * rs.difficulty_fit(r.get("difficulty", 3), concept.get("difficulty", 3))
        + 0.08 * rs.freshness_score(rs._parse_dt(r.get("published_at")), r.get("warnings") or [])
        + 0.06 * rs.duration_fit(r.get("duration_minutes"), concept.get("estimated_minutes", 60))
        + 0.06 * rs.source_quality(r["url"], r["source"]), 4)


def union_coverage(points: list[str], analyses: list[dict]) -> tuple[float, list[str]]:
    covered = {p for a in analyses for p in a["covered_points"]}
    missing = [p for p in points if p not in covered]
    return (len(covered) / len(points) if points else 0.0), missing


def gap_queries(course: str, concept_name: str, missing: list[str]) -> list[str]:
    """Targeted search queries for what is still missing, e.g. 'Java HashMap collision handling detailed tutorial'."""
    return [f"{course} {concept_name} {m} detailed tutorial" for m in missing[:2]]
