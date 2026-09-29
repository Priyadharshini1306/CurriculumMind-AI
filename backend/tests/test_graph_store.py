from app.schemas.concepts import Concept, ConceptGraph, Relationship
from app.schemas.curriculum import Curriculum
from app.services.graph_store_service import build_payload


def test_payload_maps_topics_outcomes_and_relationships():
    cur = Curriculum.model_validate({
        "course": "Java", "version": "2026", "outcomes": ["Write OOP code"],
        "units": [{"title": "OOP", "topics": [{"title": "Classes", "subtopics": ["Fields"]}]},
                  {"title": "Empty Unit"}]})
    g = ConceptGraph(
        concepts=[Concept(id="c1", name="Class", unit="OOP", topic="classes", outcomes=["Write OOP code", "bogus"]),
                  Concept(id="c2", name="Object", unit="OOP", topic="unknown topic"),
                  Concept(id="c3", name="Thing", unit="Empty Unit")],
        relationships=[Relationship(source="c1", target="c2")])
    p = build_payload("cur1", "user1", cur, g)
    assert p["course"]["version"] == "2026" and p["course"]["owner_id"] == "user1"
    by_key = {c["key"]: c for c in p["concepts"]}
    assert by_key["c1"]["topic_id"] == "cur1:u0:t0"
    assert by_key["c2"]["topic_id"] == "cur1:u0:t0"          # unknown topic falls back to unit's first topic
    assert by_key["c3"]["topic_id"] == "cur1:u1:t0"          # synthetic General topic for topic-less unit
    assert p["aligns"] == [{"concept_id": "cur1:c1", "outcome_id": "cur1:o0"}]
    assert p["prereqs"][0]["source"] == "cur1:c1" and p["related"] == []
