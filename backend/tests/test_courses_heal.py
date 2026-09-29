import asyncio
from datetime import timedelta

from app.api import courses as c
from app.repositories.mongo_repository import now


class FakeCollection:
    def __init__(self):
        self.updates = []

    async def update_one(self, flt, update):
        self.updates.append((flt, update))


class FakeDB:
    def __init__(self):
        self.curriculum_drafts = FakeCollection()


def _draft(**fields):
    return {"_id": "abc", "updated_at": now() - timedelta(minutes=fields.pop("age_minutes", 0)), **fields}


def test_fresh_busy_state_is_left_alone(monkeypatch):
    monkeypatch.setattr(c, "get_db", lambda: FakeDB())
    d = _draft(age_minutes=2, graph_status="GENERATING")
    out = asyncio.run(c._heal(d))
    assert out["graph_status"] == "GENERATING"


def test_stale_generating_with_no_graph_is_marked_failed(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(c, "get_db", lambda: db)
    d = _draft(age_minutes=40, graph_status="GENERATING")
    out = asyncio.run(c._heal(d))
    assert out["graph_status"] == "FAILED" and out["graph_error"]
    assert db.curriculum_drafts.updates  # persisted


def test_stale_generating_with_existing_graph_reverts_to_pending_review_not_failed(monkeypatch):
    monkeypatch.setattr(c, "get_db", lambda: FakeDB())
    d = _draft(age_minutes=40, graph_status="GENERATING", graph={"concepts": [], "relationships": []})
    out = asyncio.run(c._heal(d))
    assert out["graph_status"] == "PENDING_REVIEW" and out["graph_error"] is None


def test_stale_neo4j_save_is_marked_failed(monkeypatch):
    monkeypatch.setattr(c, "get_db", lambda: FakeDB())
    d = _draft(age_minutes=40, neo4j_status="SAVING")
    out = asyncio.run(c._heal(d))
    assert out["neo4j_status"] == "FAILED" and out["neo4j_error"]
