import asyncio

import pytest
from pymongo.errors import AutoReconnect

from app.repositories import mongo_repository as m


def test_read_methods_are_wrapped_but_inserts_are_not():
    assert hasattr(m.SessionRepository.exists, "__wrapped__")
    assert hasattr(m.UserRepository.by_email, "__wrapped__")
    assert hasattr(m.QuizRepository.history, "__wrapped__")
    assert not hasattr(m.UserRepository.create, "__wrapped__")
    assert not hasattr(m.QuizRepository.add_attempt, "__wrapped__")


def test_transient_errors_are_retried(monkeypatch):
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise AutoReconnect("reset")
        return "ok"

    async def no_sleep(_):
        return None

    monkeypatch.setattr(m._asyncio, "sleep", no_sleep)
    assert asyncio.run(m._retrying(flaky)()) == "ok" and calls["n"] == 3


def test_gives_up_after_three_attempts(monkeypatch):
    async def always():
        raise AutoReconnect("down")

    async def no_sleep(_):
        return None

    monkeypatch.setattr(m._asyncio, "sleep", no_sleep)
    with pytest.raises(AutoReconnect):
        asyncio.run(m._retrying(always)())
