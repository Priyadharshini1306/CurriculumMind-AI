import pytest
from pydantic import ValidationError

from app.services import coverage_service as cv


def vec(*xs):
    n = sum(x * x for x in xs) ** 0.5
    return [x / n for x in xs]


def test_coverage_formula_eight_of_ten():
    points = [f"topic{i}" for i in range(10)]
    # each point i is a one-hot direction; chunk i matches point i for the first 8 only
    pv = [[1.0 if j == i else 0.0 for j in range(10)] for i in range(10)]
    chunks = [f"discusses topic{i} in depth" for i in range(8)]
    cvecs = pv[:8]
    r = cv.evaluate(points, pv, chunks, cvecs, has_full_text=True)
    assert r["coverage"] == 0.8 and len(r["covered_points"]) == 8 and r["missing_points"] == ["topic8", "topic9"]
    assert r["confidence"] == r["evidence"] == 1.0 and r["evidence_list"][0]["snippet"].startswith("discusses topic0")


def test_semantic_match_needs_term_support():
    r = cv.evaluate(["collision handling"], [vec(1, 0)], ["something about maps and buckets"], [vec(1, 0)], True)
    assert r["coverage"] == 0.0  # similar vector, but no shared term -> not covered
    r = cv.evaluate(["collision handling"], [vec(1, 0)], ["how collision resolution works"], [vec(1, 0)], True)
    assert r["coverage"] == 1.0


def test_low_similarity_not_covered_and_confidence_penalised_without_full_text():
    r = cv.evaluate(["hashing"], [vec(1, 0)], ["hashing basics"], [vec(0, 1)], False)
    assert r["coverage"] == 0.0
    r = cv.evaluate(["hashing"], [vec(1, 0)], ["hashing basics"], [vec(1, 0)], False)
    assert r["confidence"] == pytest.approx(0.6)


def test_union_coverage_and_gap_queries():
    pts = ["a", "b", "c", "d"]
    cov, missing = cv.union_coverage(pts, [{"covered_points": ["a"]}, {"covered_points": ["a", "c"]}])
    assert cov == 0.5 and missing == ["b", "d"]
    q = cv.gap_queries("Java", "HashMap", ["collision handling"])
    assert q == ["Java HashMap collision handling detailed tutorial"]


def test_chunking_overlaps_and_covers_whole_text():
    text = " ".join(f"w{i}" for i in range(200))
    chunks = cv.chunk_text(text)
    assert len(chunks) > 2 and chunks[-1].endswith("w199") and cv.chunk_text("") == []


def test_required_points_validation():
    assert cv.RequiredPoints(points=["a b", "  c d ", "e f", "A B"]).points == ["a b", "c d", "e f"]
    with pytest.raises(ValidationError):
        cv.RequiredPoints(points=["only one"])


def test_final_rank_rewards_coverage():
    concept = {"difficulty": 3, "estimated_minutes": 60}
    r = {"url": "https://x.com/a", "source": "WEB", "difficulty": 3, "duration_minutes": 20, "published_at": None, "warnings": []}
    assert cv.final_rank(0.7, 1.0, 0.6, r, concept) > cv.final_rank(0.7, 0.2, 0.6, r, concept)
