from app.services import gap_service as gs

NAMES = ["Java Basics", "OOP", "Collections", "Spring", "Spring Boot", "SQL"]
IDS = ["basics", "oop", "coll", "spring", "boot", "sql"]


def concepts():
    return [{"id": i, "name": n, "difficulty": 2 + k % 3, "estimated_minutes": 60, "semester": 1, "week": 1 + k}
            for k, (i, n) in enumerate(zip(IDS, NAMES))]


EDGES = [("basics", "oop"), ("oop", "coll"), ("coll", "spring"), ("spring", "boot")]  # sql is independent


def m(score, attempts=1):
    return {"mastery_score": score, "attempt_count": attempts}


def test_weak_concept_traces_to_frontier_prerequisite():
    # Spring Boot weak; basics mastered; OOP untested -> OOP is the frontier, Collections/Spring are behind it
    mastery = {"boot": m(0.2), "basics": m(0.95, 2)}
    gaps = gs.analyze(concepts(), EDGES, mastery)
    kinds = {g["concept_id"]: g["kind"] for g in gaps}
    assert kinds == {"boot": "WEAK", "oop": "PREREQUISITE_UNVERIFIED"}
    assert next(g for g in gaps if g["concept_id"] == "oop")["because"] == ["Spring Boot"]


def test_weak_prerequisite_is_confirmed_gap_and_stops_the_walk():
    mastery = {"boot": m(0.2), "spring": m(0.3), "coll": m(0.9, 2), "oop": m(0.9, 2), "basics": m(0.9, 2)}
    kinds = {g["concept_id"]: g["kind"] for g in gs.analyze(concepts(), EDGES, mastery)}
    assert kinds == {"boot": "WEAK", "spring": "WEAK"}  # spring is weak itself; its own prereqs are mastered


def test_no_weak_concepts_means_no_gaps():
    assert gs.analyze(concepts(), EDGES, {"basics": m(0.9), "oop": m(0.6)}) == []


def test_severity_orders_gaps():
    mastery = {"boot": m(0.1), "sql": m(0.4)}
    gaps = gs.analyze(concepts(), EDGES, mastery)
    assert [g["concept_id"] for g in gaps if g["kind"] == "WEAK"] == ["boot", "sql"]


def test_adaptive_path_skips_mastered_and_remediates_before_weak():
    mastery = {"boot": m(0.2), "basics": m(0.95, 3)}
    gaps = gs.analyze(concepts(), EDGES, mastery)
    res = {"oop": [{"id": "r1", "title": "Hard", "difficulty": 4, "coverage": 0.9, "rank": 1},
                   {"id": "r2", "title": "Gentle", "difficulty": 1, "coverage": 0.7, "rank": 2}]}
    p = gs.build_adaptive(concepts(), EDGES, mastery, gaps, res, hours_per_week=4)
    order = [i["concept_id"] for w in p["weeks"] for i in w["items"]]
    assert "basics" not in order and [s["concept_id"] for s in p["skipped"]] == ["basics"]
    assert order.index("oop") < order.index("coll") < order.index("spring") < order.index("boot")  # prerequisites first
    actions = {i["concept_id"]: i["action"] for w in p["weeks"] for i in w["items"]}
    assert actions["oop"] == gs.REMEDIATE and actions["boot"] == gs.RETRY and actions["sql"] == gs.LEARN
    oop = next(i for w in p["weeks"] for i in w["items"] if i["concept_id"] == "oop")
    assert oop["resources"][0]["id"] == "r2" and "Easier" in oop["resources"][0]["why"]  # easiest first
    assert oop["practice"]["type"] == "QUIZ"


def test_order_respects_prerequisites_even_with_priorities():
    mastery = {"boot": m(0.2)}
    p = gs.build_adaptive(concepts(), EDGES, mastery, gs.analyze(concepts(), EDGES, mastery), {}, 8)
    order = [i["concept_id"] for w in p["weeks"] for i in w["items"]]
    for a, b in EDGES:
        assert order.index(a) < order.index(b)


def test_weeks_respect_workload():
    p = gs.build_adaptive(concepts(), EDGES, {}, [], {}, hours_per_week=2)  # ~1 concept (60-90 min) per week
    assert all(sum((i["estimated_minutes"] or 0) for i in w["items"]) <= 150 for w in p["weeks"])
    assert p["summary"]["skipped"] == 0 and p["summary"]["learn"] == 6


def test_everything_mastered_yields_empty_path():
    mastery = {i: m(0.95, 3) for i in IDS}
    p = gs.build_adaptive(concepts(), EDGES, mastery, [], {}, 8)
    assert p["weeks"] == [] and p["summary"]["skipped"] == 6
