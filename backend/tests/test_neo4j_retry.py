import asyncio

import pytest
from neo4j.exceptions import ServiceUnavailable

from app.repositories import neo4j_repository as repo


def test_functions_are_wrapped_and_record_attempt_is_not():
    assert hasattr(repo.get_mastery, "__wrapped__")
    assert not hasattr(repo.record_attempt, "__wrapped__")


def test_retries_transient_failures_then_succeeds(monkeypatch):
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ServiceUnavailable("defunct connection")
        return "ok"

    async def no_sleep(_):
        return None

    monkeypatch.setattr(repo._asyncio, "sleep", no_sleep)
    assert asyncio.run(repo._with_retry(flaky)()) == "ok" and calls["n"] == 3


def test_gives_up_after_max_attempts(monkeypatch):
    async def always():
        raise ServiceUnavailable("down")

    async def no_sleep(_):
        return None

    monkeypatch.setattr(repo._asyncio, "sleep", no_sleep)
    with pytest.raises(ServiceUnavailable):
        asyncio.run(repo._with_retry(always)())
