import asyncio

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.api import deps
from app.core.security import create_token


def cred(sid="s1"):
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=create_token("u1", "LEARNER", sid))


@pytest.fixture()
def counted(monkeypatch):
    calls = {"session": 0, "user": 0, "alive": True}

    class Sessions:
        async def exists(self, sid):
            calls["session"] += 1
            return calls["alive"]

    class Users:
        async def by_id(self, uid):
            calls["user"] += 1
            return {"_id": uid, "name": "U", "email": "u@example.com"}

    monkeypatch.setattr(deps, "SessionRepository", Sessions)
    monkeypatch.setattr(deps, "UserRepository", Users)
    deps._sessions.clear()
    return calls


def test_verified_session_is_cached_so_database_is_hit_once(counted):
    for _ in range(5):
        claims = asyncio.run(deps.current_claims(cred()))
    assert counted == {"session": 1, "user": 1, "alive": True}
    assert claims["_user"]["email"] == "u@example.com"


def test_logout_evicts_the_cache_immediately(counted):
    asyncio.run(deps.current_claims(cred()))
    deps.evict_session("s1")
    counted["alive"] = False  # the session was revoked in the database
    with pytest.raises(HTTPException) as e:
        asyncio.run(deps.current_claims(cred()))
    assert e.value.status_code == 401


def test_cache_expires(counted, monkeypatch):
    asyncio.run(deps.current_claims(cred()))
    entry = deps._sessions["s1"]
    deps._sessions["s1"] = (0.0, entry[1])  # already expired
    asyncio.run(deps.current_claims(cred()))
    assert counted["session"] == 2


def test_bad_token_never_touches_the_database(counted):
    with pytest.raises(HTTPException):
        asyncio.run(deps.current_claims(HTTPAuthorizationCredentials(scheme="Bearer", credentials="garbage")))
    assert counted["session"] == 0
