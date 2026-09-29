"""Assemble the semester -> week -> concept -> resources learning path and the learner's position in it."""

from app.services.mastery_service import MASTERY_THRESHOLD, classify  # single source of truth for "mastered"


def concept_status(mastery: float | None) -> str:
    return classify(mastery)


def assemble(rows: list[dict]) -> dict:
    """rows: flat, ordered by semester/week (see neo4j_repository.path_rows)."""
    semesters: dict[int, dict[int, list[dict]]] = {}
    for r in rows:
        c = r["concept"]
        item = {**c, "mastery": r["mastery"], "status": concept_status(r["mastery"]), "resources": r["resources"]}
        semesters.setdefault(r["semester"], {}).setdefault(r["week"], []).append(item)

    tree, current = [], None
    for s in sorted(semesters):
        weeks = []
        for w in sorted(semesters[s]):
            concepts = semesters[s][w]
            done = all(c["status"] == "MASTERED" for c in concepts)
            weeks.append({"week": w, "concepts": concepts, "completed": done})
            if current is None and not done:
                current = {"semester": s, "week": w, "concept_ids": [c["id"] for c in concepts if c["status"] != "MASTERED"]}
        tree.append({"semester": s, "weeks": weeks,
                     "completed": all(w["completed"] for w in weeks)})

    flat = [c for sem in tree for w in sem["weeks"] for c in w["concepts"]]
    mastered = sum(1 for c in flat if c["status"] == "MASTERED")
    return {
        "semesters": tree,
        "current": current,
        "progress": {"concepts_total": len(flat), "mastered": mastered,
                     "percent": round(100 * mastered / len(flat)) if flat else 0,
                     "unresolved_gaps": sum(1 for c in flat if c.get("gap_status") == "UNRESOLVED_GAP")},
    }
