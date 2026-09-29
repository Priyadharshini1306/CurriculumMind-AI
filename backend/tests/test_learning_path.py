from app.services import learning_path_service as lp


def row(sem, week, cid, mastery=None, gap=None):
    return {"semester": sem, "week": week, "mastery": mastery, "resources": [],
            "concept": {"id": cid, "name": cid, "gap_status": gap}}


def test_status_thresholds():
    assert lp.concept_status(None) == "NOT_STARTED"
    assert lp.concept_status(0.5) == "LEARNING"
    assert lp.concept_status(0.8) == "MASTERED"


def test_structure_current_position_and_progress():
    rows = [row(1, 1, "a", 0.9), row(1, 1, "b", 0.85), row(1, 2, "c", 0.4), row(1, 2, "d"),
            row(2, 1, "e", gap="UNRESOLVED_GAP")]
    p = lp.assemble(rows)
    assert [s["semester"] for s in p["semesters"]] == [1, 2]
    assert p["semesters"][0]["weeks"][0]["completed"] is True
    assert p["current"] == {"semester": 1, "week": 2, "concept_ids": ["c", "d"]}
    assert p["progress"] == {"concepts_total": 5, "mastered": 2, "percent": 40, "unresolved_gaps": 1}


def test_fully_mastered_path_has_no_current_week():
    p = lp.assemble([row(1, 1, "a", 1.0)])
    assert p["current"] is None and p["progress"]["percent"] == 100


def test_empty_path():
    p = lp.assemble([])
    assert p["semesters"] == [] and p["progress"]["percent"] == 0
