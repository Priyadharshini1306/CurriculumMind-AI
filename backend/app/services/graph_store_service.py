"""Persist an approved curriculum + concept graph to Neo4j, with embeddings for vector search."""
import logging
import time

from app.repositories import neo4j_repository as repo
from app.schemas.concepts import ConceptGraph
from app.schemas.curriculum import Curriculum
from app.services import embedding_service

log = logging.getLogger(__name__)


def _norm(s: str) -> str:
    return " ".join((s or "").lower().split())


def build_payload(curriculum_id: str, owner_id: str, cur: Curriculum, graph: ConceptGraph) -> dict:
    """Pure function: turn the approved documents into node/relationship rows (ids namespaced per curriculum
    so several curriculum versions can coexist without colliding)."""
    ns = curriculum_id
    units, topics, outcomes, topic_lookup = [], [], [], {}
    for ui, u in enumerate(cur.units):
        uid = f"{ns}:u{ui}"
        units.append({"id": uid, "title": u.title, "order": ui, "hours": u.hours, "weeks": u.weeks})
        for ti, t in enumerate(u.topics):
            tid = f"{uid}:t{ti}"
            topics.append({"id": tid, "unit_id": uid, "title": t.title, "order": ti,
                           "subtopics": t.subtopics, "text": " ".join([t.title, *t.subtopics])})
            topic_lookup[(_norm(u.title), _norm(t.title))] = tid
        if not u.topics:  # concepts of a topic-less unit hang off a synthetic "General" topic
            tid = f"{uid}:t0"
            topics.append({"id": tid, "unit_id": uid, "title": "General", "order": 0, "subtopics": [], "text": u.title})
            topic_lookup[(_norm(u.title), "general")] = tid
    unit_first_topic = {}
    for t in topics:
        unit_first_topic.setdefault(t["unit_id"], t["id"])
    for oi, o in enumerate(cur.outcomes):
        outcomes.append({"id": f"{ns}:o{oi}", "text": o})
    outcome_by_text = {o["text"]: o["id"] for o in outcomes}
    unit_id_by_title = {_norm(u["title"]): u["id"] for u in units}

    concepts, aligns = [], []
    for c in graph.concepts:
        uid = unit_id_by_title.get(_norm(c.unit))
        tid = topic_lookup.get((_norm(c.unit), _norm(c.topic))) or unit_first_topic.get(uid)
        cid = f"{ns}:{c.id}"
        concepts.append({"id": cid, "key": c.id, "name": c.name, "description": c.description,
                         "difficulty": c.difficulty, "estimated_minutes": c.estimated_minutes,
                         "unit": c.unit, "topic_id": tid, "text": f"{c.name}. {c.description}".strip()})
        aligns += [{"concept_id": cid, "outcome_id": outcome_by_text[o]} for o in c.outcomes if o in outcome_by_text]
    rels = [{"source": f"{ns}:{r.source}", "target": f"{ns}:{r.target}", "confidence": r.confidence,
             "evidence": r.evidence, "type": r.type.value} for r in graph.relationships]
    return {"course": {"id": ns, "owner_id": owner_id, "name": cur.course, "code": cur.course_code,
                       "version": cur.version, "credit_hours": cur.credit_hours, "semester": cur.semester},
            "units": units, "topics": topics, "outcomes": outcomes, "concepts": concepts,
            "aligns": aligns, "prereqs": [r for r in rels if r["type"] == "PREREQUISITE_OF"],
            "related": [r for r in rels if r["type"] == "RELATED_TO"]}


async def save(curriculum_id: str, owner_id: str, cur: Curriculum, graph: ConceptGraph) -> dict:
    p = build_payload(curriculum_id, owner_id, cur, graph)
    t0 = time.perf_counter()
    rows = p["concepts"] + p["topics"]
    vecs = await embedding_service.embed([r["text"] for r in rows])  # one batch for everything
    for r, v in zip(rows, vecs):
        r["embedding"] = v
    t1 = time.perf_counter()
    await repo.save_curriculum_graph(p)
    log.info("graph save %s: embedded %d texts in %.1fs, wrote to Neo4j in %.1fs",
             curriculum_id, len(rows), t1 - t0, time.perf_counter() - t1)
    return {"concepts": len(p["concepts"]), "topics": len(p["topics"]), "units": len(p["units"]),
            "prerequisites": len(p["prereqs"]), "related": len(p["related"])}
