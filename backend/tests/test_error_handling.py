"""The API must turn dependency failures into clean JSON errors, never stack traces."""
import os

os.environ.setdefault("JWT_SECRET", "x" * 40)

import pytest
from fastapi.testclient import TestClient
from neo4j.exceptions import ServiceUnavailable
from pymongo.errors import AutoReconnect

from app.main import app
from app.services.embedding_service import EmbeddingError
from app.services.llm_service import LLMError


def _raiser(exc):
    async def handler():
        raise exc
    return handler


@pytest.fixture(scope="module")
def client():
    for path, exc in [("/_t/mongo", AutoReconnect("down")), ("/_t/neo4j", ServiceUnavailable("down")),
                      ("/_t/llm", LLMError("invalid JSON after 2 attempts")), ("/_t/embed", EmbeddingError("no model")),
                      ("/_t/boom", RuntimeError("secret internals"))]:
        app.add_api_route(path, _raiser(exc), methods=["GET"])
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("path,status,needle", [
    ("/_t/mongo", 503, "MongoDB"), ("/_t/neo4j", 503, "Neo4j"), ("/_t/llm", 502, "AI model"),
    ("/_t/embed", 503, "embedding"), ("/_t/boom", 500, "Internal server error")])
def test_dependency_failures_become_clean_json(client, path, status, needle):
    r = client.get(path)
    assert r.status_code == status and needle in r.json()["detail"]
    assert "secret internals" not in r.text and "Traceback" not in r.text


def test_protected_routes_reject_missing_and_bad_tokens(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer nonsense"}).status_code == 401
    assert client.post("/api/upload", files={"file": ("a.txt", b"x")}).status_code == 401
