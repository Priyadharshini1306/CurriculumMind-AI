"""Neo4j graph schema: node labels, relationship types, constraints, vector indexes."""

EMBEDDING_DIM = 384  # all-MiniLM-L6-v2

NODE_LABELS = [
    "Course", "Unit", "Topic", "Concept", "Outcome", "Resource",
    "Learner", "Semester", "Week", "Quiz", "Question", "LearningPath",
]

RELATIONSHIPS = [
    "HAS_UNIT", "HAS_TOPIC", "HAS_CONCEPT", "HAS_OUTCOME", "PREREQUISITE_OF",
    "RELATED_TO", "PART_OF", "ALIGNS_WITH", "COVERS", "MASTERED", "LEARNING",
    "TESTS", "ATTEMPTED", "IN_SEMESTER", "IN_WEEK",
]

# Every node gets a unique `id`, except Learner which is keyed by the MongoDB user_id.
UNIQUE_KEYS = {label: "id" for label in NODE_LABELS}
UNIQUE_KEYS["Learner"] = "user_id"

VECTOR_INDEXES = {
    "concept_embedding": "Concept",
    "topic_embedding": "Topic",
    "resource_embedding": "Resource",
}

SCHEMA_STATEMENTS = [
    f"CREATE CONSTRAINT {label.lower()}_{key}_unique IF NOT EXISTS "
    f"FOR (n:{label}) REQUIRE n.{key} IS UNIQUE"
    for label, key in UNIQUE_KEYS.items()
] + [
    f"CREATE VECTOR INDEX {name} IF NOT EXISTS FOR (n:{label}) ON (n.embedding) "
    f"OPTIONS {{indexConfig: {{`vector.dimensions`: {EMBEDDING_DIM}, `vector.similarity_function`: 'cosine'}}}}"
    for name, label in VECTOR_INDEXES.items()
]
