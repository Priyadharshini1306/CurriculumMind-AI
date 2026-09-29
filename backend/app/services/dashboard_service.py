"""Pure aggregation for the learner and instructor dashboards (no I/O, unit-tested)."""
from collections import defaultdict

from app.algorithms import sequencing as algo
from app.services import mastery_service as ms


def _ordered_units(rows: list[dict]) -> list[str]:
    seen, out = set(), []
    for r in rows:
        u = r.get("unit") or "Other"
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def unit_mastery(rows: list[dict]) -> list[dict]:
    """rows: concepts with mastery_score (None = not attempted). Average mastery per unit, attempted concepts only."""
    by_unit: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_unit[r.get("unit") or "Other"].append(r)
    out = []
    for u in _ordered_units(rows):
        rs = by_unit[u]
        att = [r["mastery_score"] for r in rs if r["mastery_score"] is not None]
        out.append({"unit": u, "concepts": len(rs), "attempted": len(att),
                    "mastered": sum(ms.is_mastered(a) for a in att),
                    "avg_mastery": round(sum(att) / len(att), 3) if att else None})
    return out


def plan_load(concepts: list[dict], capacity_hours: float) -> list[dict]:
    """Study hours per (semester, week) of the approved plan, using the difficulty-weighted effort estimate."""
    minutes: dict[tuple, float] = defaultdict(float)
    counts: dict[tuple, int] = defaultdict(int)
    for c in concepts:
        if c.get("semester") is None or c.get("week") is None:
            continue
        key = (c["semester"], c["week"])
        minutes[key] += algo.effort_minutes(algo.Item(c["id"], c["name"], c.get("difficulty") or 2,
                                                       c.get("estimated_minutes") or 60, 0))
        counts[key] += 1
    return [{"semester": s, "week": w, "label": f"S{s} W{w}", "hours": round(m / 60, 1), "concepts": counts[(s, w)],
             "capacity_hours": capacity_hours, "overloaded": m / 60 > capacity_hours + 1e-9}
            for (s, w), m in sorted(minutes.items())]


def coverage_summary(concepts: list[dict]) -> dict:
    """concepts: rows with coverage, gap_status, missing_points, gap_message, resource_count, outdated_count, unit."""
    status = defaultdict(int)
    for c in concepts:
        status[c.get("gap_status") or "NOT_ANALYZED"] += 1
    by_unit: dict[str, list[float]] = defaultdict(list)
    for c in concepts:
        if c.get("coverage") is not None:
            by_unit[c.get("unit") or "Other"].append(c["coverage"])
    analysed = [c["coverage"] for c in concepts if c.get("coverage") is not None]
    return {
        "covered": status["COVERED"], "unresolved": status["UNRESOLVED_GAP"],
        "pending": status["GAP"], "not_analyzed": status["NOT_ANALYZED"], "total": len(concepts),
        "avg_coverage": round(sum(analysed) / len(analysed), 3) if analysed else None,
        "by_unit": [{"unit": u, "avg_coverage": round(sum(by_unit[u]) / len(by_unit[u]), 3) if by_unit.get(u) else None,
                     "concepts": sum(1 for c in concepts if (c.get("unit") or "Other") == u)}
                    for u in _ordered_units(concepts)],
        "unresolved_concepts": [{"concept": c["name"], "unit": c.get("unit"), "coverage": c.get("coverage"),
                                 "missing_points": c.get("missing_points") or [], "message": c.get("gap_message")}
                                for c in concepts if c.get("gap_status") == "UNRESOLVED_GAP"],
        "resources": {"total": sum(c.get("resource_count") or 0 for c in concepts),
                      "outdated": sum(c.get("outdated_count") or 0 for c in concepts),
                      "concepts_without_resources": sum(1 for c in concepts if not c.get("resource_count"))},
    }


def outcome_alignment(outcomes: list[str], concepts: list[dict]) -> dict:
    """Which concepts support each course outcome; outcomes with no concept are flagged."""
    by_outcome: dict[str, list[str]] = {o: [] for o in outcomes}
    for c in concepts:
        for o in c.get("outcomes") or []:
            by_outcome.setdefault(o, []).append(c["name"])
    rows = [{"outcome": o, "concept_count": len(names), "concepts": sorted(names), "aligned": bool(names)}
            for o, names in by_outcome.items()]
    return {"outcomes": rows, "unaligned_outcomes": sum(not r["aligned"] for r in rows),
            "concepts_without_outcome": sum(1 for c in concepts if not c.get("outcomes"))}
