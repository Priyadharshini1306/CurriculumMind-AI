"""Knowledge-gap detection and adaptive path generation, from mastery + the prerequisite graph.

Gaps
  * WEAK concept           : attempted, mastery < WEAK_THRESHOLD.
  * PREREQUISITE_* concept : the *frontier* of a weak concept's unmastered prerequisites, i.e. the earliest
    unmastered ancestors whose own prerequisites are all mastered. That is what to study first.
    WEAK -> confirmed gap, DEVELOPING -> partly learned, UNVERIFIED -> never tested (check it).

Adaptive path
  Mastered concepts are skipped. The rest is re-ordered topologically with priority
  remediation (prerequisite gaps) -> weak concepts -> everything else in the original plan order, and re-bucketed
  into weeks by the learner's weekly study hours. Remediation/retry items get extra practice time and easier
  resources."""
import networkx as nx

from app.algorithms import sequencing as algo
from app.services import mastery_service as ms

PRACTICE_FACTOR = 1.25  # extra time budgeted for remediation and retries

REMEDIATE, RETRY, CONTINUE, LEARN, SKIP = "REMEDIATE", "RETRY", "CONTINUE", "LEARN", "SKIP"


def _graph(concepts: list[dict], edges: list[tuple[str, str]]) -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_nodes_from(c["id"] for c in concepts)
    g.add_edges_from((a, b) for a, b in edges if a in g and b in g and a != b)
    return g


def _status(mastery: dict, cid: str) -> str:
    return ms.classify(mastery.get(cid, {}).get("mastery_score"))


def analyze(concepts: list[dict], edges: list[tuple[str, str]], mastery: dict[str, dict]) -> list[dict]:
    """mastery: concept_id -> {mastery_score, attempt_count}. Returns gaps, most severe first."""
    g = _graph(concepts, edges)
    names = {c["id"]: c["name"] for c in concepts}
    gaps: dict[str, dict] = {}

    def add(cid: str, kind: str, because: str | None, severity: float) -> None:
        cur = gaps.setdefault(cid, {"concept_id": cid, "concept": names[cid], "kind": kind, "severity": 0.0,
                                    "because": [], "mastery": mastery.get(cid, {}).get("mastery_score")})
        if kind == "WEAK":
            cur["kind"] = "WEAK"  # a confirmed weakness outranks a prerequisite label
        cur["severity"] = round(max(cur["severity"], severity), 3)
        if because and because not in cur["because"]:
            cur["because"].append(because)

    weak = [c["id"] for c in concepts if _status(mastery, c["id"]) == "WEAK"]
    for w in weak:
        add(w, "WEAK", None, 1 - (mastery[w]["mastery_score"] or 0))
        unmastered = {a for a in nx.ancestors(g, w) if _status(mastery, a) != "MASTERED"}
        for a in unmastered:
            if nx.ancestors(g, a) & unmastered:  # has an unmastered prerequisite of its own: not the frontier
                continue
            st = _status(mastery, a)
            kind = {"WEAK": "PREREQUISITE_WEAK", "LEARNING": "PREREQUISITE_DEVELOPING"}.get(st, "PREREQUISITE_UNVERIFIED")
            sev = 1 - mastery[a]["mastery_score"] if a in mastery else 0.5
            add(a, kind, names[w], sev)
    return sorted(gaps.values(), key=lambda x: (-x["severity"], x["concept"]))


def _position(c: dict) -> tuple:
    return (c.get("semester") or 99, c.get("week") or 99, c["name"])


def _pick_resources(item_action: str, concept: dict, resources: list[dict]) -> list[dict]:
    if not resources:
        return []
    if item_action in (REMEDIATE, RETRY):
        easy = sorted(resources, key=lambda r: (r.get("difficulty") or 3, -(r.get("coverage") or 0)))
        out = []
        for r in easy[:2]:
            easier = (r.get("difficulty") or 3) < (concept.get("difficulty") or 3)
            out.append({**r, "why": "Easier explanation to rebuild the basics" if easier
                        else "A different explanation of the same concept"})
        return out
    return [{**r, "why": "Recommended for this concept"} for r in sorted(resources, key=lambda r: r.get("rank") or 99)[:2]]


def build_adaptive(concepts: list[dict], edges: list[tuple[str, str]], mastery: dict[str, dict],
                   gaps: list[dict], resources: dict[str, list[dict]], hours_per_week: float = 8) -> dict:
    g = _graph(concepts, edges)
    by_id = {c["id"]: c for c in concepts}
    remediate = {x["concept_id"] for x in gaps if x["kind"].startswith("PREREQUISITE")}
    weak = {x["concept_id"] for x in gaps if x["kind"] == "WEAK"}
    reasons = {x["concept_id"]: x for x in gaps}

    skipped = [c["id"] for c in concepts if _status(mastery, c["id"]) == "MASTERED"]
    keep = [c["id"] for c in concepts if c["id"] not in set(skipped)]
    sub = g.subgraph(keep).copy()

    def action(cid: str) -> str:
        if cid in weak:
            return RETRY
        if cid in remediate:
            return REMEDIATE
        return CONTINUE if _status(mastery, cid) == "LEARNING" else LEARN

    def priority(cid: str) -> int:
        return {REMEDIATE: 0, RETRY: 1}.get(action(cid), 2)

    order = list(nx.lexicographical_topological_sort(
        sub, key=lambda n: (priority(n), _position(by_id[n]), n)))

    items = []
    for cid in order:
        c, a = by_id[cid], action(cid)
        if a == REMEDIATE:
            reason = f"Prerequisite gap behind: {', '.join(reasons[cid]['because'])}"
        elif a == RETRY:
            reason = f"Weak (mastery {round((mastery[cid]['mastery_score'] or 0) * 100)}%): review, then retake the quiz"
        elif a == CONTINUE:
            reason = "In progress: keep practising until mastered"
        else:
            reason = "Next in your plan"
        items.append({"concept_id": cid, "concept": c["name"], "action": a, "reason": reason,
                      "mastery": mastery.get(cid, {}).get("mastery_score"),
                      "difficulty": c.get("difficulty"), "estimated_minutes": c.get("estimated_minutes"),
                      "unit": c.get("unit"),
                      "practice": {"type": "QUIZ", "target_mastery": ms.MASTERY_THRESHOLD}
                      if a in (REMEDIATE, RETRY, CONTINUE) else None,
                      "resources": _pick_resources(a, c, resources.get(cid, []))})

    seq = [algo.Item(i["concept_id"], i["concept"], i.get("difficulty") or 2,
                     int((i.get("estimated_minutes") or 60) * (PRACTICE_FACTOR if i["action"] in (REMEDIATE, RETRY) else 1)), 0)
           for i in items]
    slots = {cid: wk for cid, _sem, wk in algo.allocate(seq, hours_per_week, 10_000)}
    weeks: dict[int, list[dict]] = {}
    for it in items:
        it["week"] = slots[it["concept_id"]]
        weeks.setdefault(it["week"], []).append(it)

    return {
        "weeks": [{"week": w, "items": weeks[w]} for w in sorted(weeks)],
        "skipped": [{"concept_id": s, "concept": by_id[s]["name"], "reason": "Already mastered",
                     "mastery": mastery[s]["mastery_score"]} for s in skipped],
        "summary": {"remediate": sum(i["action"] == REMEDIATE for i in items),
                    "retry": sum(i["action"] == RETRY for i in items),
                    "continue": sum(i["action"] == CONTINUE for i in items),
                    "learn": sum(i["action"] == LEARN for i in items),
                    "skipped": len(skipped), "weeks": len(weeks)},
    }
