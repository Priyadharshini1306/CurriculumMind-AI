"""Concept generation (per unit) and prerequisite/related-concept detection, with business validation of LLM output."""
import json
import logging

from app.schemas.concepts import (Concept, ConceptGraph, LLMRelationships, LLMUnitConcepts,
                                  RelType, Relationship)
from app.schemas.curriculum import Curriculum
from app.services import llm_service

log = logging.getLogger(__name__)

CONCEPT_SYSTEM = (
    "You are a curriculum expert. Break the given unit into atomic, teachable concepts (about 5-10). "
    "Each concept is a single learnable idea with a short human-readable name in Title Case with spaces (e.g. 'Variable Declaration', never camelCase), a one-sentence description, a difficulty "
    "from 1 (easy) to 5 (hard), and estimated learning minutes (realistic total study time for a beginner including hands-on practice: usually 60-240). Set 'topic' to the unit topic it belongs to. "
    "Set 'outcomes' to the course outcomes (copied verbatim from the list given) that the concept supports, "
    "or an empty list."
)
CONCEPT_HINT = (
    'Reply with JSON only, in this shape:\n'
    '{"concepts":[{"name":"Variable Declaration","description":"one short sentence","difficulty":2,'
    '"estimated_minutes":90,"topic":"...","outcomes":[]}]}'
)

REL_SYSTEM = (
    "You are a curriculum expert. Given 'new_concepts' and, for context, 'earlier_concepts' already placed before "
    "them in the course, list learning dependencies that involve at least one 'new_concepts' entry as the dependent "
    "or as one side of a related pair. "
    "type PREREQUISITE_OF: 'prerequisite' must be understood before 'dependent'; 'dependent' must be one of "
    "new_concepts. Only direct, necessary dependencies; do not list transitive ones (if A->B and B->C, do not add A->C). "
    "type RELATED_TO: closely related concepts with no ordering; at least one side must be in new_concepts. "
    "Use the exact concept names given. Give confidence 0-1 and a one-sentence evidence for each. "
    "If new_concepts has no real dependencies, return an empty list."
)
REL_HINT = (
    'Reply with JSON only, in this shape:\n'
    '{"relationships":[{"prerequisite":"Exact Name","dependent":"Exact Name","type":"PREREQUISITE_OF",'
    '"confidence":0.8,"evidence":"one short sentence"}]}'
)
# Prerequisites and related pairs are overwhelmingly local (within or just before the unit that introduces a
# concept). Detecting them unit-by-unit against a small rolling window of earlier context, rather than in one call
# over every concept in the course, keeps each LLM call's prompt+output size roughly constant no matter how long the
# course is -- a course with 10 units was previously sent as a single call the model could take many minutes (or
# time out) on.
CONTEXT_UNITS = 3


def _key(name: str) -> str:
    return " ".join(name.lower().split())


async def generate_unit_concepts(cur: Curriculum, unit_index: int) -> list[dict]:
    unit = cur.units[unit_index]
    payload = {
        "course": cur.course,
        "unit": unit.title,
        "topics": [{"title": t.title, "subtopics": t.subtopics} for t in unit.topics],
        "course_outcomes": cur.outcomes,
    }
    # generous headroom: gpt-oss is a reasoning model whose hidden "thinking" tokens count against this same cap and
    # vary widely (observed 250-1300+ on this prompt shape) -- too tight a cap truncates mid-thought, leaving no room
    # for the actual answer and getting rejected by Groq's own JSON validation before it even reaches us
    res = await llm_service.generate_json(CONCEPT_SYSTEM, json.dumps(payload), LLMUnitConcepts, temperature=0.3,
                                          schema_hint=CONCEPT_HINT, num_ctx=3072, num_predict=2800, retries=2)
    valid_outcomes = set(cur.outcomes)
    return [
        {**c.model_dump(), "unit": unit.title,
         "outcomes": [o for o in c.outcomes if o in valid_outcomes]}  # drop hallucinated outcomes
        for c in res.concepts
    ]


def assemble_concepts(per_unit: list[list[dict]]) -> list[Concept]:
    """Assign stable ids and drop duplicate concept names (first occurrence wins). `owner_unit` on each row of
    `per_unit` is not mutated; callers that need to know which unit first introduced each assembled concept use
    `group_by_unit` below, which replays the same dedup logic."""
    seen, out = set(), []
    for concepts in per_unit:
        for c in concepts:
            k = _key(c["name"])
            if k in seen:
                continue
            seen.add(k)
            out.append(Concept(**{**c, "id": f"c{len(out) + 1}"}))
    return out


def _brief(c: Concept) -> dict:
    return {"name": c.name, "unit": c.unit, "description": c.description}


async def _relationships_for_unit(new_concepts: list[Concept], earlier_concepts: list[Concept]) -> LLMRelationships:
    payload = {"new_concepts": [_brief(c) for c in new_concepts],
               "earlier_concepts": [_brief(c) for c in earlier_concepts]}
    # bound the output cap by how many pairs are actually possible, so a small unit doesn't pay for a large one;
    # floor is high enough to survive gpt-oss's variable reasoning-token overhead (see generate_unit_concepts)
    cap = min(2800, 1200 + 40 * len(new_concepts) * max(1, len(earlier_concepts) + len(new_concepts)))
    return await llm_service.generate_json(
        REL_SYSTEM, json.dumps(payload), LLMRelationships, temperature=0.2,
        schema_hint=REL_HINT, num_ctx=4096, num_predict=cap, retries=2)


def group_by_unit(concepts: list[Concept], per_unit: list[list[dict]]) -> list[list[Concept]]:
    """`assemble_concepts` drops a concept whose name already appeared in an earlier unit, so a unit's contribution
    to the assembled list can be shorter than its raw generation. Replay the same first-occurrence dedup, keyed by
    name, to recover which assembled Concept each unit actually introduced."""
    by_name = {_key(c.name): c for c in concepts}
    seen, out = set(), []
    for unit_concepts in per_unit:
        group = []
        for c in unit_concepts:
            k = _key(c["name"])
            if k in seen:
                continue
            seen.add(k)
            if k in by_name:
                group.append(by_name[k])
        out.append(group)
    return out


async def detect_relationships(concepts: list[Concept], per_unit: list[list[dict]] | None = None,
                               on_progress=None) -> list[Relationship]:
    """Detect dependencies unit by unit, giving the model only the new unit's concepts plus a rolling window of
    concepts from earlier units as context -- see CONTEXT_UNITS. Every concept is "new" in exactly one batch, so
    results never need cross-batch de-duplication beyond the usual per-pair check."""
    groups = group_by_unit(concepts, per_unit) if per_unit is not None else [concepts]
    out: list[Relationship] = []
    earlier: list[Concept] = []
    for i, new_concepts in enumerate(groups):
        if not new_concepts:
            continue
        context = earlier[-CONTEXT_UNITS * 10:]  # generous concept cap per window, independent of course length
        if on_progress:
            await on_progress(f"Finding prerequisites for unit {i + 1}/{len(groups)}")
        res = await _relationships_for_unit(new_concepts, context)
        out.extend(validate_relationships(res, concepts))
        earlier.extend(new_concepts)
    return dedupe_relationships(out)


def validate_relationships(res: LLMRelationships, concepts: list[Concept]) -> list[Relationship]:
    """Business validation: unknown names and self-loops are discarded."""
    by_name = {_key(c.name): c.id for c in concepts}
    out = []
    for r in res.relationships:
        s, t = by_name.get(_key(r.prerequisite)), by_name.get(_key(r.dependent))
        if not s or not t or s == t:
            continue
        out.append(Relationship(source=s, target=t, type=r.type, confidence=r.confidence, evidence=r.evidence))
    return out


def dedupe_relationships(rels: list[Relationship]) -> list[Relationship]:
    out, seen = [], set()
    for r in rels:
        pair = (r.source, r.target, r.type) if r.type == RelType.PREREQUISITE_OF else (*sorted((r.source, r.target)), r.type)
        if pair in seen:
            continue
        seen.add(pair)
        out.append(r)
    return out


async def build_graph(cur: Curriculum, on_progress=None) -> ConceptGraph:
    per_unit = []
    for i in range(len(cur.units)):
        per_unit.append(await generate_unit_concepts(cur, i))
        if on_progress:
            await on_progress(f"Concepts for unit {i + 1}/{len(cur.units)}")
    concepts = assemble_concepts(per_unit)
    relationships = await detect_relationships(concepts, per_unit, on_progress)
    return ConceptGraph(concepts=concepts, relationships=relationships)
