import asyncio

from app.services import analysis_service as an
from app.services import coverage_service as cov


def _stub(monkeypatch, found_per_call):
    calls = {"search": 0, "queries": [], "status": None}

    async def fake_embed(texts):
        return [[1.0, 0.0] for _ in texts]

    async def discover_queries(queries, youtube_queries=1):
        calls["search"] += 1
        calls["queries"].append(queries)
        return found_per_call(calls["search"])

    async def noop(*a, **k):
        return None

    async def save_cov(concept_id, coverage, status, missing, iterations, message):
        calls["status"] = (status, iterations, message, missing)

    monkeypatch.setattr(an.embedding_service, "embed", fake_embed)
    monkeypatch.setattr(an.rs, "discover_queries", discover_queries)
    monkeypatch.setattr(an.repo, "upsert_resources", noop)
    monkeypatch.setattr(an.repo, "save_resource_analysis", noop)
    monkeypatch.setattr(an.repo, "save_concept_coverage", save_cov)
    return calls


CONCEPT = {"id": "k1", "name": "HashMap", "description": "", "difficulty": 3, "estimated_minutes": 60}
POINTS = ["put and get", "collision handling", "load factor", "iteration"]


def _rows():
    return [{"resource_id": "r0", "covered_points": ["put and get"], "rank_score": 0.5, "coverage": 0.25}]


def test_gap_loop_is_bounded_and_ends_unresolved(monkeypatch):
    calls = _stub(monkeypatch, lambda n: [])  # searches never find anything
    res = asyncio.run(an.gap_loop("Java", CONCEPT, POINTS, [[1.0, 0.0]] * 4, _rows()))
    assert calls["search"] == cov.MAX_ITERATIONS == 3
    assert calls["queries"][0][0] == "Java HashMap collision handling detailed tutorial"
    status, iterations, message, missing = calls["status"]
    assert (status, iterations) == ("UNRESOLVED_GAP", 3)
    assert message == "No suitable resource found. Instructor/custom content required."
    assert "collision handling" in missing and res["status"] == "UNRESOLVED_GAP"


def test_gap_loop_stops_early_when_resolved(monkeypatch):
    async def analyze_all(concept, points, pvecs, resources):
        return [{"resource_id": r["id"], "covered_points": ["collision handling", "load factor"], "rank_score": 0.9,
                 "coverage": 0.5, "evidence": 0.6, "confidence": 0.5, "missing_points": [], "evidence_json": "[]",
                 "similarity": 0.8, "accepted": False, "reasons": []} for r in resources]

    calls = _stub(monkeypatch, lambda n: [{"id": f"new{n}", "title": "t", "url": "https://a.com/x", "source": "WEB",
                                           "description": "", "text": "", "published_at": None}])
    monkeypatch.setattr(an, "_analyze_all", analyze_all)
    res = asyncio.run(an.gap_loop("Java", CONCEPT, POINTS, [[1.0, 0.0]] * 4, _rows()))
    assert calls["search"] == 1 and res["status"] == "COVERED"  # 3 of 4 points -> 75% >= 60%
