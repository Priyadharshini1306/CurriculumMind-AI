"""Shared fixtures. Integration tests use *synchronous* drivers for direct database checks so they never share an event
loop with the app's cached async clients, and they skip (not fail) when a service is not reachable."""
import os
import re

import pytest

from app.core.config import get_settings

# Unit tests need a JWT secret but must never depend on the developer's real one.
os.environ.setdefault("JWT_SECRET", "unit-test-secret-" + "x" * 32)


@pytest.fixture(scope="session")
def settings():
    return get_settings()


@pytest.fixture(scope="session")
def mongo_db(settings):
    if not settings.mongodb_uri:
        pytest.skip("MONGODB_URI not configured")
    import pymongo
    client = pymongo.MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=20000, connectTimeoutMS=10000)
    last = None
    for _ in range(3):  # the network under test resets connections now and then
        try:
            client.admin.command("ping")
            break
        except Exception as e:
            last = e
    else:
        pytest.skip(f"MongoDB unreachable: {last}")
    yield client[settings.mongodb_db]
    client.close()


@pytest.fixture(scope="session")
def neo4j_driver(settings):
    if not settings.neo4j_uri:
        pytest.skip("NEO4J_URI not configured")
    from neo4j import GraphDatabase
    uri = settings.neo4j_uri
    if settings.neo4j_trust_self_signed:
        uri = uri.replace("neo4j+s://", "neo4j+ssc://")
    driver = GraphDatabase.driver(uri, auth=(settings.neo4j_username, settings.neo4j_password),
                                  liveness_check_timeout=10, max_connection_lifetime=180, keep_alive=True)
    try:
        driver.verify_connectivity()
    except Exception as e:
        pytest.skip(f"Neo4j unreachable: {e}")
    yield driver
    driver.close()


TEST_EMAIL = re.compile(r"^(it|e2e)[0-9a-f]{8}@example\.com$")


def purge_test_users(db, emails: list[str]) -> list[str]:
    """Delete test users and everything they own in MongoDB. Only touches accounts this suite created."""
    users = list(db.users.find({"email": {"$in": [e for e in emails if TEST_EMAIL.match(e)]}}, {"_id": 1}))
    ids = [str(u["_id"]) for u in users]
    for coll in ("sessions", "uploads", "curriculum_drafts", "verification_feedback", "quiz_attempts", "quiz_jobs"):
        db[coll].delete_many({"user_id": {"$in": ids}})
    db.users.delete_many({"_id": {"$in": [u["_id"] for u in users]}})
    return ids
