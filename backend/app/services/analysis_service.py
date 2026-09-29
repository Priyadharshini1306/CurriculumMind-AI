"""Per-concept resource analysis: required points -> coverage/evidence per resource -> gap loop (bounded) -> status."""
import json
import logging

from app.repositories import neo4j_repository as repo
from app.services import coverage_service as cov
from app.services import embedding_service, resource_matching, resource_service as rs

log = logging.getLogger(__name__)

UNRESOLVED_MESSAGE = "No suitable resource found. Instructor/custom content required."
KEEP_LINKS = 6


def _row(analysis: dict, r: dict, concept: dict, rel: float) -> dict:
    return {
        "resource_id": r["id"], "coverage": analysis["coverage"], "evidence": analysis["evidence"],
        "confidence": analysis["confidence"], "covered_points": analysis["covered_points"],
        "missing_points": analysis["missing_points"], "evidence_json": json.dumps(analysis["evidence_list"]),
        "similarity": r.get("similarity"),
        "rank_score": cov.final_rank(rel, analysis["coverage"], analysis["evidence"], r, concept),
        "accepted": analysis["coverage"] >= cov.COVERAGE_THRESHOLD,
        "reasons": r.get("reasons") or [],
    }


def _rel(concept: dict, r: dict) -> float:
    r = {**r, "published_at_dt": rs._parse_dt(r.get("published_at"))}
    return rs.relevance(r.get("similarity") or 0.0, concept["name"], r)


async def _analyze_all(concept: dict, points: list[str], pvecs, resources: list[dict]) -> list[dict]:
    """Analyze resources against the required points; returns rows ready to store (best first, ranked)."""
    rows = []
    for r in resources:
        try:
            a = await cov.analyze_resource(concept["name"], points, pvecs, r)
            rows.append(_row(a, r, concept, _rel(concept, r)))
        except Exception as e:  # one unreadable resource must not stop the concept
            log.warning("analysis failed for resource %s: %s", r.get("url"), e)
    rows.sort(key=lambda x: -x["rank_score"])
    for i, row in enumerate(rows):
        row["rank"] = i + 1
    return rows


async def _finish(concept: dict, points: list[str], rows: list[dict], iterations: int) -> dict:
    coverage, missing = cov.union_coverage(points, rows)
    ok = coverage >= cov.COVERAGE_THRESHOLD
    status = "COVERED" if ok else "UNRESOLVED_GAP" if iterations >= cov.MAX_ITERATIONS else "GAP"
    msg = UNRESOLVED_MESSAGE if status == "UNRESOLVED_GAP" else None
    await repo.save_concept_coverage(concept["id"], round(coverage, 3), status, missing, iterations, msg)
    return {"concept_id": concept["id"], "coverage": coverage, "status": status, "missing": missing}


async def analyze_concept(course: str, item: dict, do_gaps: bool = True) -> dict:
    concept = item["concept"]
    resources = [r for r in item["resources"] if r]
    points = concept.get("required_points")
    if not points:
        points = await cov.required_points(course, concept)
        await repo.save_required_points(concept["id"], points)
    pvecs = await cov.embed_points(concept["name"], points)
    rows = await _analyze_all(concept, points, pvecs, resources)
    if rows:
        await repo.save_resource_analysis(concept["id"], rows)
    result = await _finish(concept, points, rows, iterations=0)
    if do_gaps and result["status"] == "GAP":
        result = await gap_loop(course, concept, points, pvecs, rows)
    return result


async def gap_loop(course: str, concept: dict, points: list[str], pvecs, rows: list[dict]) -> dict:
    """Search for what is missing, at most MAX_ITERATIONS times; then give up with UNRESOLVED_GAP."""
    cvec = (await embedding_service.embed([f"{concept['name']}. {concept.get('description', '')}"]))[0]
    known = {r["resource_id"] for r in rows}
    iterations = 0
    while iterations < cov.MAX_ITERATIONS:
        coverage, missing = cov.union_coverage(points, rows)
        if coverage >= cov.COVERAGE_THRESHOLD:
            break
        iterations += 1
        queries = cov.gap_queries(course, concept["name"], missing)
        found = [r for r in await rs.discover_queries(queries, youtube_queries=1 if iterations == 1 else 0) if r["id"] not in known]
        if not found:
            continue
        vecs = await embedding_service.embed([resource_matching._text_for_embedding(r) for r in found])
        await repo.upsert_resources([
            {**{k: v for k, v in r.items() if k != "published_at_dt"}, "embedding": v,
             "published_at": r.get("published_at") and str(r["published_at"]),
             "has_transcript": r.get("has_transcript", False)} for r, v in zip(found, vecs)])
        for r, v in zip(found, vecs):
            r["similarity"] = round(sum(a * b for a, b in zip(cvec, v)), 4)
            r["reasons"] = [f"Found by gap search (iteration {iterations}) for: {', '.join(missing[:2])}"]
        new_rows = await _analyze_all(concept, points, pvecs, found)
        # keep only resources that add at least one still-missing point
        useful = [n for n in new_rows if set(n["covered_points"]) & set(missing)]
        known |= {n["resource_id"] for n in new_rows}
        rows = sorted(rows + useful, key=lambda x: -x["rank_score"])[:KEEP_LINKS]
        for i, row in enumerate(rows):
            row["rank"] = i + 1
        if useful:
            await repo.save_resource_analysis(concept["id"], rows)
    return await _finish(concept, points, rows, iterations)


async def recompute_coverage(item: dict) -> dict | None:
    """Recompute concept-level coverage from stored per-resource analysis (no LLM, no network)."""
    concept = item["concept"]
    points = concept.get("required_points")
    linked = [r for r in item["resources"] if r and r.get("covered_points") is not None]
    if not points or not linked:
        return None
    rows = [{"covered_points": r["covered_points"]} for r in linked]
    return await _finish(concept, points, rows, concept.get("gap_iterations") or 0)
