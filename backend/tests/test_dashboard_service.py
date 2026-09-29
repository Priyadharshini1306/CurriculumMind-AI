from app.services import dashboard_service as ds


def test_unit_mastery_averages_only_attempted_concepts():
    rows = [{"unit": "OOP", "mastery_score": 0.9}, {"unit": "OOP", "mastery_score": None},
            {"unit": "OOP", "mastery_score": 0.5}, {"unit": "Basics", "mastery_score": None}]
    out = ds.unit_mastery(rows)
    assert [u["unit"] for u in out] == ["OOP", "Basics"]  # first-appearance order
    assert out[0] == {"unit": "OOP", "concepts": 3, "attempted": 2, "mastered": 1, "avg_mastery": 0.7}
    assert out[1]["avg_mastery"] is None and out[1]["attempted"] == 0


def test_plan_load_hours_and_overload_flag():
    cs = [{"id": "a", "name": "A", "difficulty": 2, "estimated_minutes": 120, "semester": 1, "week": 1},
          {"id": "b", "name": "B", "difficulty": 2, "estimated_minutes": 120, "semester": 1, "week": 1},
          {"id": "c", "name": "C", "difficulty": 2, "estimated_minutes": 60, "semester": 1, "week": 2},
          {"id": "x", "name": "unplaced", "semester": None, "week": None}]
    out = ds.plan_load(cs, capacity_hours=3)
    assert [(w["label"], w["hours"], w["overloaded"]) for w in out] == [("S1 W1", 4.0, True), ("S1 W2", 1.0, False)]


def test_coverage_summary():
    cs = [{"name": "A", "unit": "U1", "coverage": 1.0, "gap_status": "COVERED", "resource_count": 3, "outdated_count": 1},
          {"name": "B", "unit": "U1", "coverage": 0.4, "gap_status": "UNRESOLVED_GAP", "missing_points": ["x"],
           "gap_message": "No suitable resource found.", "resource_count": 2, "outdated_count": 0},
          {"name": "C", "unit": "U2", "coverage": None, "gap_status": None, "resource_count": 0}]
    s = ds.coverage_summary(cs)
    assert (s["covered"], s["unresolved"], s["not_analyzed"], s["total"]) == (1, 1, 1, 3)
    assert s["avg_coverage"] == 0.7 and s["by_unit"][0] == {"unit": "U1", "avg_coverage": 0.7, "concepts": 2}
    assert s["by_unit"][1]["avg_coverage"] is None
    assert s["unresolved_concepts"][0]["missing_points"] == ["x"]
    assert s["resources"] == {"total": 5, "outdated": 1, "concepts_without_resources": 1}


def test_outcome_alignment_flags_unmapped():
    cs = [{"name": "A", "outcomes": ["O1"]}, {"name": "B", "outcomes": ["O1", "O2"]}, {"name": "C", "outcomes": []}]
    a = ds.outcome_alignment(["O1", "O2", "O3"], cs)
    assert [(o["outcome"], o["concept_count"]) for o in a["outcomes"]] == [("O1", 2), ("O2", 1), ("O3", 0)]
    assert a["unaligned_outcomes"] == 1 and a["concepts_without_outcome"] == 1
