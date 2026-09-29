from app.algorithms.cycle_detection import build_digraph, find_cycles, is_dag, redundant_edges
from app.algorithms.topological_sort import depth_levels, topological_order
from app.schemas.concepts import (Concept, ConceptGraph, GraphPatch, GraphPatchConcept,
                                  GraphPatchRelationship, Relationship, RelType)
from app.services import graph_service as gs


def graph(edges, ids=("a", "b", "c", "d"), **kw):
    return ConceptGraph(
        concepts=[Concept(id=i, name=i) for i in ids],
        relationships=[Relationship(source=s, target=t, **kw) for s, t in edges])


def test_cycle_detection():
    g = build_digraph(["a", "b", "c"], [("a", "b"), ("b", "c"), ("c", "a")])
    assert not is_dag(g)
    assert sorted(find_cycles(g)[0]) == ["a", "b", "c"]


def test_redundant_edge():
    g = build_digraph(["a", "b", "c"], [("a", "b"), ("b", "c"), ("a", "c")])
    assert redundant_edges(g) == [("a", "c")]


def test_topological_order_and_depth():
    g = build_digraph(["a", "b", "c"], [("a", "b"), ("b", "c")])
    assert topological_order(g) == ["a", "b", "c"]
    assert depth_levels(g) == {"a": 0, "b": 1, "c": 2}


def test_validate_reports_everything():
    r = gs.validate(graph([("a", "b"), ("b", "c"), ("c", "a")]))
    assert not r.is_dag and r.blocking and r.orphans == ["d"]
    r = gs.validate(graph([("a", "b"), ("b", "c"), ("a", "c")], ids=("a", "b", "c")))
    assert r.is_dag and not r.blocking and r.redundant_edges == [("a", "c")] and r.orphans == []


def test_dangling_reference_blocks():
    r = gs.validate(graph([("a", "zzz")]))
    assert r.blocking and r.errors


def test_low_confidence_flagged():
    r = gs.validate(graph([("a", "b")], confidence=0.3))
    assert r.suspicious and "Low confidence" in r.suspicious[0].reason


def test_sanitize_drops_bad_relationships():
    g = graph([("a", "b"), ("a", "b"), ("a", "x"), ("b", "b")])
    assert len(gs.sanitize(g).relationships) == 1


def test_apply_patch_modifies_in_place_without_touching_the_rest():
    g = graph([("a", "b")])
    patch = GraphPatch(upsert_concepts=[GraphPatchConcept(id="b", name="B renamed", difficulty=4)])
    out = gs.apply_patch(g, patch)
    assert {c.id: c.name for c in out.concepts} == {"a": "a", "b": "B renamed", "c": "c", "d": "d"}
    assert next(c for c in out.concepts if c.id == "b").difficulty == 4
    assert [(r.source, r.target) for r in out.relationships] == [("a", "b")]


def test_apply_patch_adds_a_new_concept_and_remaps_temp_ids_in_relationships():
    g = graph([("a", "b")])
    patch = GraphPatch(
        upsert_concepts=[GraphPatchConcept(id="new1", name="Fresh Concept")],
        add_relationships=[GraphPatchRelationship(source="b", target="new1")])
    out = gs.apply_patch(g, patch)
    new = next(c for c in out.concepts if c.name == "Fresh Concept")
    assert new.id not in {"a", "b", "c", "d"}
    assert any(r.source == "b" and r.target == new.id for r in out.relationships)


def test_apply_patch_removes_concepts_and_their_relationships():
    g = graph([("a", "b"), ("b", "c")])
    patch = GraphPatch(remove_concept_ids=["b"])
    out = gs.apply_patch(g, patch)
    assert {c.id for c in out.concepts} == {"a", "c", "d"}
    assert out.relationships == []


def test_apply_patch_removes_a_specific_relationship_only():
    g = graph([("a", "b"), ("b", "c")])
    patch = GraphPatch(remove_relationships=[GraphPatchRelationship(source="a", target="b")])
    out = gs.apply_patch(g, patch)
    assert [(r.source, r.target) for r in out.relationships] == [("b", "c")]
