import asyncio
import json

import httpx
import pytest
from neo4j.exceptions import AuthError, ClientError, ServiceUnavailable

from app.core.neo4j_http import HttpDriver


def _driver(handler, database="db1"):
    d = HttpDriver("example.test", "u", "p", database)
    d._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), auth=("u", "p"))
    return d


def _rows(fields, values):
    return httpx.Response(202, json={"data": {"fields": fields, "values": values}})


def test_run_returns_records():
    seen = []

    def handler(req):
        seen.append((req.url.path, json.loads(req.content)))
        return _rows(["id", "n"], [["a", 1], ["b", 2]])

    async def go():
        async with _driver(handler).session() as s:
            res = await s.run("MATCH (n) WHERE n.x=$x RETURN n", x=5)
            return await res.data(), (await (await s.run("RETURN 1")).single())["id"]

    data, first = asyncio.run(go())
    assert data == [{"id": "a", "n": 1}, {"id": "b", "n": 2}] and first == "a"
    assert seen[0] == ("/db/db1/query/v2", {"statement": "MATCH (n) WHERE n.x=$x RETURN n", "parameters": {"x": 5}})


def test_single_is_none_for_no_rows():
    async def go():
        async with _driver(lambda r: _rows(["x"], [])).session() as s:
            return await (await s.run("MATCH (n) RETURN n")).single()

    assert asyncio.run(go()) is None


def test_execute_write_uses_one_transaction_and_commits():
    calls = []

    def handler(req):
        calls.append((req.method, req.url.path))
        if req.url.path.endswith("/tx"):
            return httpx.Response(202, json={"transaction": {"id": "T1"}})
        return _rows([], [])

    async def work(tx):
        await tx.run("CREATE (:A)")
        await tx.run("CREATE (:B)")

    asyncio.run(_run_write(_driver(handler), work))
    assert [p for _, p in calls] == ["/db/db1/query/v2/tx", "/db/db1/query/v2/tx/T1", "/db/db1/query/v2/tx/T1",
                                     "/db/db1/query/v2/tx/T1/commit"]


def test_execute_write_rolls_back_on_error():
    calls = []

    def handler(req):
        calls.append(req.method)
        return httpx.Response(202, json={"transaction": {"id": "T1"}}) if req.url.path.endswith("/tx") else _rows([], [])

    async def work(tx):
        raise ValueError("boom")

    with pytest.raises(ValueError):
        asyncio.run(_run_write(_driver(handler), work))
    assert calls[-1] == "DELETE"


async def _run_write(driver, work):
    async with driver.session() as s:
        await s.execute_write(work)


@pytest.mark.parametrize("response,exc", [
    (httpx.Response(401), AuthError),
    (httpx.Response(503), ServiceUnavailable),
    (httpx.Response(400, json={"errors": [{"message": "bad cypher"}]}), ClientError),
])
def test_http_errors_map_to_driver_exceptions(response, exc):
    async def go():
        async with _driver(lambda r: response).session() as s:
            await s.run("RETURN 1")

    with pytest.raises(exc):
        asyncio.run(go())


def test_database_name_is_discovered_when_not_configured():
    def handler(req):
        if req.url.path == "/db/system/query/v2":
            return _rows(["name"], [["2f53e513"], ["system"]])
        assert req.url.path == "/db/2f53e513/query/v2"
        return _rows(["ok"], [[1]])

    async def go():
        async with _driver(handler, database=None).session() as s:
            return (await (await s.run("RETURN 1 AS ok")).single())["ok"]

    assert asyncio.run(go()) == 1
