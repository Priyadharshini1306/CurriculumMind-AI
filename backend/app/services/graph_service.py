"""Prerequisite-graph validation and AI revision."""

from pydantic import BaseModel

from app.algorithms.cycle_detection import build_digraph, find_cycles, is_dag, redundant_edges
from app.schemas.concepts import Concept, ConceptGraph, GraphPatch, Relationship, RelType
from app.services import llm_service
from app.services.concept_service import dedupe_relationships

LOW_CONFIDENCE = 0.5
DIFFICULTY_JUMP = 2  # prerequisite is this much harder than its dependent -> suspicious


class Suspicious(BaseModel):
    source: str
    target: str
    reason: str


class ValidationReport(BaseModel):
    is_dag: bool
    cycles: list[list[str]]
    redundant_edges: list[tuple[str, str]]
    orphans: list[str]
    suspicious: list[Suspicious]
    errors: list[str]  # dangling references / duplicate ids: structural problems that block approval

    @property
    def blocking(self) -> bool:
        return (not self.is_dag) or bool(self.errors)


def _prereq_edges(graph: ConceptGraph) -> list[tuple[str, str]]:
    return [(r.source, r.target) for r in graph.relationships if r.type == RelType.PREREQUISITE_OF]


def validate(graph: ConceptGraph) -> ValidationReport:
    ids = [c.id for c in graph.concepts]
    idset = set(ids)
    errors = []
    if len(ids) != len(idset):
        errors.append("Duplicate concept ids")
    for r in graph.relationships:
        for end in (r.source, r.target):
            if end not in idset:
                errors.append(f"Relationship references unknown concept '{end}'")
        if r.source == r.target:
            errors.append(f"Self-relationship on '{r.source}'")
    valid_edges = [e for e in _prereq_edges(graph) if e[0] in idset and e[1] in idset and e[0] != e[1]]
    g = build_digraph(ids, valid_edges)

    connected = {r.source for r in graph.relationships} | {r.target for r in graph.relationships}
    by_id = {c.id: c for c in graph.concepts}
    suspicious = []
    for r in graph.relationships:
        if r.source not in by_id or r.target not in by_id:
            continue
        if r.confidence < LOW_CONFIDENCE:
            suspicious.append(Suspicious(source=r.source, target=r.target,
                                         reason=f"Low confidence ({r.confidence:.2f})"))
        elif r.type == RelType.PREREQUISITE_OF and \
                by_id[r.source].difficulty - by_id[r.target].difficulty >= DIFFICULTY_JUMP:
            suspicious.append(Suspicious(source=r.source, target=r.target,
                                         reason="Prerequisite is much harder than the concept that depends on it"))
    return ValidationReport(
        is_dag=is_dag(g), cycles=find_cycles(g), redundant_edges=redundant_edges(g),
        orphans=[i for i in ids if i not in connected], suspicious=suspicious, errors=sorted(set(errors)))


def sanitize(graph: ConceptGraph) -> ConceptGraph:
    """Business validation of LLM-revised graphs: unique ids, no dangling/self/duplicate relationships."""
    seen, concepts = set(), []
    for c in graph.concepts:
        if c.id and c.id not in seen:
            seen.add(c.id)
            concepts.append(c)
    rels, pairs = [], set()
    for r in graph.relationships:
        key = (r.source, r.target, r.type)
        if r.source in seen and r.target in seen and r.source != r.target and key not in pairs:
            pairs.add(key)
            rels.append(r)
    return ConceptGraph(concepts=concepts, relationships=rels)


REVISE_SYSTEM = (
    "You revise a curriculum concept graph to satisfy human feedback. Reply with only a PATCH describing what "
    "changes -- most concepts and relationships in a large graph are unaffected by any one piece of feedback, so "
    "never restate anything that isn't changing. "
    "upsert_concepts: full concept fields for each concept you are adding or modifying. To modify an existing "
    "concept, use its 'id' exactly as given in the graph. To add a new concept, invent a short temporary id such as "
    "'new1', 'new2' (unique within this response only). "
    "remove_concept_ids: ids of concepts to delete outright (their relationships are removed automatically). "
    "add_relationships / remove_relationships: only the specific edges that change; for PREREQUISITE_OF, source is "
    "the prerequisite of target. You may reference a new concept's temporary id here. remove_relationships must "
    "match an edge that already exists in the graph. "
    "The prerequisite graph must stay acyclic. If the feedback needs no change, return an empty patch."
)
PATCH_HINT = (
    'Reply with JSON only, in this shape (omit any list that is empty):\n'
    '{"upsert_concepts":[{"id":"c7","name":"...","description":"one short sentence","difficulty":2,'
    '"estimated_minutes":90,"unit":"...","topic":"...","outcomes":[]}],'
    '"remove_concept_ids":["c12"],'
    '"add_relationships":[{"source":"c3","target":"c7","type":"PREREQUISITE_OF","confidence":0.8,"evidence":"..."}],'
    '"remove_relationships":[{"source":"c9","target":"c2","type":"PREREQUISITE_OF"}]}'
)


def apply_patch(graph: ConceptGraph, patch: GraphPatch) -> ConceptGraph:
    """Apply an AI-proposed patch to an existing graph. Unknown/self-referencing relationships and duplicate ids
    are dropped the same way `sanitize` drops them from a full LLM-generated graph."""
    by_id = {c.id: c for c in graph.concepts}
    concepts = list(graph.concepts)
    id_map: dict[str, str] = {}  # the model's temporary ids -> the real ids we assign new concepts
    next_n = len(concepts) + 1
    for pc in patch.upsert_concepts:
        fields = pc.model_dump(exclude={"id"})
        if pc.id in by_id:
            idx = next(i for i, c in enumerate(concepts) if c.id == pc.id)
            concepts[idx] = Concept(**{**fields, "id": pc.id})
        else:
            real_id = f"c{next_n}"
            next_n += 1
            if pc.id:
                id_map[pc.id] = real_id
            concepts.append(Concept(**{**fields, "id": real_id}))
    concepts = [c for c in concepts if c.id not in set(patch.remove_concept_ids)]
    kept_ids = {c.id for c in concepts}

    def resolve(cid: str) -> str:
        return id_map.get(cid, cid)

    removed_edges = {(resolve(r.source), resolve(r.target), r.type) for r in patch.remove_relationships}
    relationships = [r for r in graph.relationships
                     if r.source in kept_ids and r.target in kept_ids
                     and (r.source, r.target, r.type) not in removed_edges]
    for r in patch.add_relationships:
        s, t = resolve(r.source), resolve(r.target)
        if s in kept_ids and t in kept_ids and s != t:
            relationships.append(Relationship(source=s, target=t, type=r.type,
                                               confidence=r.confidence, evidence=r.evidence))
    return sanitize(ConceptGraph(concepts=concepts, relationships=dedupe_relationships(relationships)))


async def revise(graph: ConceptGraph, feedback: str, report: ValidationReport) -> ConceptGraph:
    # only what the model needs to reference and edit: concepts as id/name/unit/topic, edges as [source,target,type]
    # (descriptions, minutes, confidence and evidence are kept on the server and only matter for what it changes)
    slim = {"concepts": [{"id": c.id, "name": c.name, "unit": c.unit, "topic": c.topic} for c in graph.concepts],
            "relationships": [[r.source, r.target, r.type.value] for r in graph.relationships]}
    problems = {k: v for k, v in {"cycles": report.cycles, "redundant_edges": report.redundant_edges,
                                  "orphans": report.orphans}.items() if v}
    user = llm_service.compact({"graph": slim, "feedback": feedback, "known_problems": problems})
    # the prompt still carries the whole graph as context (the model needs it to reference concepts correctly), but
    # the *output* is now just the delta, which is what was making a revision on a large graph slow to the point of
    # timing out: the model no longer has to regenerate every unchanged concept and relationship verbatim.
    size = len(graph.concepts) + len(graph.relationships)
    num_ctx = min(16384, max(4096, 1500 + size * 60))
    # generous headroom: gpt-oss's hidden reasoning tokens count against this cap and vary widely, so too tight a
    # cap truncates mid-thought and Groq's own JSON validation rejects the empty result before it reaches us
    patch = await llm_service.generate_json(REVISE_SYSTEM, user, GraphPatch, temperature=0.2,
                                            schema_hint=PATCH_HINT, num_ctx=num_ctx, num_predict=2800, retries=2)
    return apply_patch(graph, patch)
