from app.schemas.concepts import LLMRelationship, LLMRelationships, RelType
from app.services import concept_service as cs


def _concepts():
    return cs.assemble_concepts([
        [{"name": "Java Basics", "unit": "U1"}, {"name": "java  basics", "unit": "U1"}],
        [{"name": "OOP", "unit": "U2"}, {"name": "Collections", "unit": "U3"}],
    ])


def test_assemble_dedupes_and_assigns_ids():
    cs_ = _concepts()
    assert [c.id for c in cs_] == ["c1", "c2", "c3"]


def test_relationship_validation_drops_bad_edges():
    res = LLMRelationships(relationships=[
        LLMRelationship(prerequisite="Java Basics", dependent="OOP"),
        LLMRelationship(prerequisite="java basics", dependent="OOP"),          # duplicate (dedup is a separate step)
        LLMRelationship(prerequisite="OOP", dependent="OOP"),                  # self loop
        LLMRelationship(prerequisite="Ghost", dependent="OOP"),                # unknown
        LLMRelationship(prerequisite="OOP", dependent="Collections", type=RelType.RELATED_TO),
    ])
    rels = cs.validate_relationships(res, _concepts())
    assert [(r.source, r.target, r.type.value) for r in rels] == [
        ("c1", "c2", "PREREQUISITE_OF"), ("c1", "c2", "PREREQUISITE_OF"), ("c2", "c3", "RELATED_TO")]


def test_dedupe_drops_repeats_and_symmetric_related_pairs():
    res = LLMRelationships(relationships=[
        LLMRelationship(prerequisite="Java Basics", dependent="OOP"),
        LLMRelationship(prerequisite="java basics", dependent="OOP"),
        LLMRelationship(prerequisite="OOP", dependent="Collections", type=RelType.RELATED_TO),
        LLMRelationship(prerequisite="Collections", dependent="OOP", type=RelType.RELATED_TO),  # same pair, reversed
    ])
    rels = cs.dedupe_relationships(cs.validate_relationships(res, _concepts()))
    assert [(r.source, r.target, r.type.value) for r in rels] == [
        ("c1", "c2", "PREREQUISITE_OF"), ("c2", "c3", "RELATED_TO")]


def test_group_by_unit_recovers_per_unit_ownership_despite_dedup():
    per_unit = [
        [{"name": "Java Basics", "unit": "U1"}, {"name": "java  basics", "unit": "U1"}],
        [{"name": "OOP", "unit": "U2"}, {"name": "Collections", "unit": "U3"}],
    ]
    concepts = cs.assemble_concepts(per_unit)
    groups = cs.group_by_unit(concepts, per_unit)
    assert [[c.name for c in g] for g in groups] == [["Java Basics"], ["OOP", "Collections"]]
