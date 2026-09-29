import networkx as nx
import pytest

from app.algorithms import sequencing as algo
from app.schemas.concepts import Concept, ConceptGraph, Relationship
from app.schemas.curriculum import Curriculum
from app.schemas.sequencing import Assignment, Plan, PlanParams
from app.services import sequencing_service as svc


def item(i, minutes=60, difficulty=2, unit=0):
    return algo.Item(i, i, difficulty, minutes, unit)


def test_topological_sequence_respects_prereqs_and_units():
    seq = algo.topological_sequence([item("c", unit=1), item("b", unit=0), item("a", unit=0)], [("a", "b"), ("b", "c")])
    assert [i.id for i in seq] == ["a", "b", "c"]


def test_cycle_raises():
    with pytest.raises(nx.NetworkXUnfeasible):
        algo.topological_sequence([item("a"), item("b")], [("a", "b"), ("b", "a")])


def test_week_and_semester_packing():
    seq = [item(str(i), minutes=60, difficulty=2) for i in range(6)]  # 60 min each, 2 h/week -> 2 per week
    rows = algo.allocate(seq, hours_per_week=2, weeks_per_semester=2)
    assert rows == [("0", 1, 1), ("1", 1, 1), ("2", 1, 2), ("3", 1, 2), ("4", 2, 1), ("5", 2, 1)]


def test_oversized_concept_gets_its_own_week():
    rows = algo.allocate([item("a", minutes=600), item("b", minutes=30)], hours_per_week=2, weeks_per_semester=10)
    assert rows == [("a", 1, 1), ("b", 1, 2)]


def test_difficulty_increases_effort():
    assert algo.effort_minutes(item("x", 60, difficulty=5)) > algo.effort_minutes(item("x", 60, difficulty=1))


def _graph():
    return ConceptGraph(
        concepts=[Concept(id="a", name="A", unit="U1", estimated_minutes=60, outcomes=["O1"]),
                  Concept(id="b", name="B", unit="U1", estimated_minutes=60, outcomes=["O2"])],
        relationships=[Relationship(source="a", target="b")])


def test_generate_then_validate_clean():
    cur = Curriculum.model_validate({"course": "X", "units": [{"title": "U1"}]})
    plan = svc.generate(cur, _graph(), PlanParams(hours_per_week=1, weeks_per_semester=4))
    r = svc.validate(plan, _graph())
    assert not r.blocking and not r.overloaded_weeks and r.semesters == 1
    assert [a.concept_id for a in plan.assignments] == ["a", "b"]


def test_validation_flags_prereq_violation_and_bad_ids():
    plan = Plan(assignments=[Assignment(concept_id="a", semester=2, week=1), Assignment(concept_id="b", semester=1, week=3),
                             Assignment(concept_id="ghost", semester=1, week=1), Assignment(concept_id="b", semester=1, week=4)])
    r = svc.validate(plan, _graph())
    assert r.blocking and r.violations and r.unknown == ["ghost"] and r.duplicates == ["b"]


def test_unassigned_and_uncovered_outcomes_are_warnings_only():
    r = svc.validate(Plan(assignments=[Assignment(concept_id="a", semester=1, week=1)]), _graph())
    assert not r.blocking and r.unassigned == ["b"] and r.uncovered_outcomes == ["O2"]


def test_overload_detected():
    plan = Plan(params=PlanParams(hours_per_week=1), assignments=[
        Assignment(concept_id="a", semester=1, week=1), Assignment(concept_id="b", semester=1, week=1)])
    assert svc.validate(plan, _graph()).overloaded_weeks[0].hours > 1
