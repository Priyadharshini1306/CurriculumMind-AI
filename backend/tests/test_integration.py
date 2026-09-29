"""Integration tests against the live services configured in .env. Run with:  pytest -m integration"""
import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.main import app
from tests.conftest import purge_test_users

pytestmark = pytest.mark.integration


# ------------------------------------------------------------------ MongoDB
def _retry_network(fn, attempts=3):
    """Direct-driver checks tolerate the occasional connection reset of the network under test."""
    import time

    from pymongo.errors import AutoReconnect, NetworkTimeout
    for i in range(attempts):
        try:
            return fn()
        except (AutoReconnect, NetworkTimeout):
            if i == attempts - 1:
                raise
            time.sleep(2 * (i + 1))


def test_mongodb_roundtrip_and_app_indexes(mongo_db):
    def roundtrip():
        coll = mongo_db["integration_scratch"]
        doc_id = coll.insert_one({"probe": uuid.uuid4().hex}).inserted_id
        try:
            assert coll.find_one({"_id": doc_id}) is not None
        finally:
            coll.drop()

    _retry_network(roundtrip)
    with TestClient(app):  # startup creates the indexes
        pass
    info = _retry_network(lambda: mongo_db.users.index_information())
    assert any(v.get("unique") for v in info.values()), "users.email must be unique"


# ------------------------------------------------------------------ Neo4j
def test_neo4j_schema_constraints_and_vector_indexes(neo4j_driver):
    with neo4j_driver.session() as s:
        constraints = s.run("SHOW CONSTRAINTS YIELD name RETURN count(*) AS n").single()["n"]
        vectors = {r["name"]: r["state"] for r in s.run("SHOW VECTOR INDEXES YIELD name, state")}
    assert constraints >= 12
    assert vectors.keys() >= {"concept_embedding", "topic_embedding", "resource_embedding"}
    assert all(state == "ONLINE" for state in vectors.values())


def test_neo4j_vector_search_returns_nearest_node(neo4j_driver):
    import math
    import random
    rnd = random.Random(7)

    def vec():
        v = [rnd.gauss(0, 1) for _ in range(384)]
        n = math.sqrt(sum(x * x for x in v))
        return [x / n for x in v]

    target, other = vec(), vec()
    with neo4j_driver.session() as s:
        try:
            s.run("CREATE (:Concept {id:'it-probe-1', name:'probe one', embedding:$e})", e=target).consume()
            s.run("CREATE (:Concept {id:'it-probe-2', name:'probe two', embedding:$e})", e=other).consume()
            hits = s.run("CALL db.index.vector.queryNodes('concept_embedding', 3, $e) YIELD node, score "
                         "WHERE node.id STARTS WITH 'it-probe' RETURN node.id AS id, score ORDER BY score DESC", e=target).data()
        finally:
            s.run("MATCH (n:Concept) WHERE n.id STARTS WITH 'it-probe' DETACH DELETE n").consume()
    assert hits and hits[0]["id"] == "it-probe-1" and hits[0]["score"] > 0.99


# ------------------------------------------------------------------ Groq
class _Answer(BaseModel):
    answer: int


def test_groq_returns_validated_structured_json(settings):
    if not settings.groq_api_key:
        pytest.skip("GROQ_API_KEY not set")
    from app.services import llm_service
    res = asyncio.run(llm_service.generate_json("Answer with JSON.", "What is 2 + 2? Put the number in 'answer'.", _Answer,
                                                temperature=0))
    assert res.answer == 4


# ------------------------------------------------------------------ FastAPI (auth, RBAC, validation)
@pytest.fixture()
def api():
    emails = []
    with TestClient(app) as c:
        c.emails = emails
        yield c


def _register(c, role="LEARNER"):
    email = f"it{uuid.uuid4().hex[:8]}@example.com"
    c.emails.append(email)
    r = c.post("/api/auth/register", json={"name": "IT User", "email": email, "password": "password123", "role": role})
    assert r.status_code == 201, r.text
    return email, {"Authorization": "Bearer " + r.json()["access_token"]}, r.json()["user"]["id"]


def test_health_reports_both_databases(api):
    assert api.get("/api/health").json() == {"api": "ok", "mongodb": "ok", "neo4j": "ok"}


def test_auth_lifecycle_rbac_and_throttling(api, mongo_db):
    try:
        email, h, uid = _register(api)
        assert api.post("/api/auth/register", json={"name": "x", "email": email, "password": "password123"}).status_code == 409
        assert api.get("/api/auth/me", headers=h).json()["email"] == email
        assert "password_hash" not in api.get("/api/auth/me", headers=h).text
        stored = mongo_db.users.find_one({"email": email})
        assert stored["password_hash"] != "password123" and stored["password_hash"].startswith("$2")  # bcrypt, never plain

        # roles: learners cannot reach instructor features
        assert api.get(f"/api/dashboard/instructor/{'0' * 24}", headers=h).status_code == 403
        assert api.post("/api/learning-path/publish", json={"curriculum_id": "0" * 24}, headers=h).status_code == 403
        assert api.get(f"/api/dashboard/learner/{'1' * 24}", headers=h).status_code == 403  # someone else's data

        # login, then brute-force throttling
        assert api.post("/api/auth/login", json={"email": email, "password": "password123"}).status_code == 200
        codes = [api.post("/api/auth/login", json={"email": email, "password": "wrong-password"}).status_code for _ in range(6)]
        assert codes[:5] == [401] * 5 and codes[5] == 429

        # logout revokes the session server-side
        assert api.post("/api/auth/logout", headers=h).status_code == 204
        assert api.get("/api/auth/me", headers=h).status_code == 401
    finally:
        purge_test_users(mongo_db, api.emails)


def test_upload_and_goal_validation(api, mongo_db):
    try:
        _, h, _ = _register(api)
        assert api.post("/api/upload", files={"file": ("a.exe", b"MZ")}, headers=h).status_code == 415
        assert api.post("/api/upload", files={"file": ("a.pdf", b"not really a pdf")}, headers=h).status_code == 400
        assert api.post("/api/upload", files={"file": ("a.txt", b"")}, headers=h).status_code == 400
        assert api.post("/api/goal", json={"goal": "x"}, headers=h).status_code == 422
        r = api.post("/api/upload", files={"file": ("s.txt", b"Unit 1: Basics")}, headers=h)
        assert r.status_code == 202 and r.json()["status"] in ("PROCESSING", "PROCESSED")
        assert api.get(f"/api/upload/{r.json()['id']}", headers=h).json()["status"] == "PROCESSED"
    finally:
        purge_test_users(mongo_db, api.emails)


# ------------------------------------------------------------------ resource search
def test_youtube_search_returns_videos(settings):
    if not settings.youtube_api_key:
        pytest.skip("YOUTUBE_API_KEY not configured")
    from app.services import resource_service as rs
    res = asyncio.run(rs.search_youtube("java hashmap tutorial", 2))
    if not res:
        pytest.skip("YouTube returned nothing (quota exhausted or network problem)")
    assert res[0]["source"] == "YOUTUBE" and res[0]["url"].startswith("https://www.youtube.com/watch?v=")
    assert res[0]["duration_minutes"] is None or res[0]["duration_minutes"] > 0


def test_web_search_and_page_extraction(settings):
    from app.services import resource_service as rs
    res = asyncio.run(rs.search_web("java hashmap tutorial", 3))
    if not res:
        pytest.skip("DuckDuckGo returned nothing (rate-limited or offline)")
    assert all(r["source"] == "WEB" and r["url"].startswith("http") for r in res)
    enriched = asyncio.run(rs.enrich(res[0], want_transcript=False))
    assert enriched["id"] and "difficulty" in enriched and isinstance(enriched["warnings"], list)  # never raises


def test_broken_url_is_survivable():
    from app.services import resource_service as rs
    r = asyncio.run(rs.enrich({"title": "Broken", "url": "https://does-not-exist.invalid/x", "source": "WEB",
                               "description": "fallback description"}, want_transcript=False))
    assert "Page could not be fetched" in r["warnings"] or "No readable content extracted" in r["warnings"]
    assert r["text"] == "fallback description"  # falls back to the search snippet instead of crashing
