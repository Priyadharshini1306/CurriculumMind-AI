"""Build and validate semester plans from the approved concept graph."""
from collections import Counter, defaultdict

from app.algorithms import sequencing as algo
from app.schemas.concepts import ConceptGraph, RelType
from app.schemas.curriculum import Curriculum
from app.schemas.sequencing import Assignment, OverloadedWeek, Plan, PlanParams, PlanReport, Violation


def _items(cur: Curriculum, graph: ConceptGraph) -> list[algo.Item]:
    unit_index = {u.title.lower(): i for i, u in enumerate(cur.units)}
    return [algo.Item(c.id, c.name, c.difficulty, c.estimated_minutes, unit_index.get(c.unit.lower(), len(cur.units)))
            for c in graph.concepts]


def _prereqs(graph: ConceptGraph) -> list[tuple[str, str]]:
    return [(r.source, r.target) for r in graph.relationships if r.type == RelType.PREREQUISITE_OF]


def generate(cur: Curriculum, graph: ConceptGraph, params: PlanParams) -> Plan:
    seq = algo.topological_sequence(_items(cur, graph), _prereqs(graph))
    rows = algo.allocate(seq, params.hours_per_week, params.weeks_per_semester)
    return Plan(params=params, assignments=[Assignment(concept_id=c, semester=s, week=w) for c, s, w in rows])


def validate(plan: Plan, graph: ConceptGraph) -> PlanReport:
    ids = {c.id: c for c in graph.concepts}
    counts = Counter(a.concept_id for a in plan.assignments)
    slot = {a.concept_id: (a.semester, a.week) for a in plan.assignments if a.concept_id in ids}
    wps = plan.params.weeks_per_semester

    violations = []
    for pre, dep in _prereqs(graph):
        if pre in slot and dep in slot and slot[pre] > slot[dep]:
            violations.append(Violation(
                prerequisite=pre, concept=dep,
                reason=f"{ids[pre].name} (S{slot[pre][0]} W{slot[pre][1]}) is scheduled after "
                       f"{ids[dep].name} (S{slot[dep][0]} W{slot[dep][1]})"))

    minutes = defaultdict(float)
    for a in plan.assignments:
        if a.concept_id in ids:
            c = ids[a.concept_id]
            minutes[(a.semester, a.week)] += algo.effort_minutes(
                algo.Item(c.id, c.name, c.difficulty, c.estimated_minutes, 0))
    cap = plan.params.hours_per_week
    overloaded = [OverloadedWeek(semester=s, week=w, hours=round(m / 60, 1), capacity_hours=cap)
                  for (s, w), m in sorted(minutes.items()) if m / 60 > cap + 1e-9]

    scheduled = {a.concept_id for a in plan.assignments}
    covered = {o for c in graph.concepts if c.id in scheduled for o in c.outcomes}
    all_outcomes = {o for c in graph.concepts for o in c.outcomes}
    return PlanReport(
        violations=violations, overloaded_weeks=overloaded,
        unassigned=[i for i in ids if i not in scheduled],
        unknown=sorted({c for c in counts if c not in ids}),
        duplicates=sorted(c for c, n in counts.items() if n > 1),
        uncovered_outcomes=sorted(all_outcomes - covered),
        total_hours=round(sum(minutes.values()) / 60, 1),
        semesters=max((a.semester for a in plan.assignments), default=0))


def structure(plan: Plan) -> list[dict]:
    """Semester -> week -> concept ids, for display and storage."""
    tree: dict[int, dict[int, list[str]]] = defaultdict(lambda: defaultdict(list))
    for a in plan.assignments:
        tree[a.semester][a.week].append(a.concept_id)
    return [{"semester": s, "weeks": [{"week": w, "concepts": tree[s][w]} for w in sorted(tree[s])]}
            for s in sorted(tree)]
