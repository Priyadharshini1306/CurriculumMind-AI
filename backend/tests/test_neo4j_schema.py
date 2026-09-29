from app.models.neo4j_models import NODE_LABELS, SCHEMA_STATEMENTS


def test_schema_covers_all_labels_and_vector_indexes():
    text = "\n".join(SCHEMA_STATEMENTS)
    for label in NODE_LABELS:
        assert f"(n:{label})" in text
    assert text.count("CREATE VECTOR INDEX") == 3
    assert "n.user_id IS UNIQUE" in text
