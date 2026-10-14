"""Neo4j over HTTPS (the Query API, port 443) with just enough of the async-driver interface for this app.

Bolt (port 7687) is blocked or filtered on many networks (offices, colleges, some ISPs, antivirus), while HTTPS on 443
always gets through. Aura serves the same database on both, so when Bolt isn't reachable the app talks to it this way.
Only what the repository uses is implemented: `driver.session()`, `session.run`, `session.execute_write`,
`tx.run`, and `result.single()/data()/values()`."""
import httpx
from neo4j.exceptions import AuthError, ClientError, ServiceUnavailable


class HttpRecord(dict):
    """A result row: indexable by column name, like the driver's Record."""


class HttpResult:
    def __init__(self, fields: list[str], rows: list[list]):
        self._fields, self._rows = fields, rows

    async def single(self):
        return HttpRecord(zip(self._fields, self._rows[0])) if self._rows else None

    async def data(self) -> list[dict]:
        return [dict(zip(self._fields, r)) for r in self._rows]

    async def values(self) -> list[list]:
        return self._rows

    async def consume(self):
        return None


class HttpTransaction:
    """An explicit transaction (begin / run... / commit) so a multi-statement write stays atomic."""

    def __init__(self, driver: "HttpDriver"):
        self._d = driver
        self._id: str | None = None
        self._headers: dict[str, str] = {}

    async def begin(self) -> None:
        r = await self._d._post("/tx", {}, {})
        self._id = r.json()["transaction"]["id"]
        affinity = r.headers.get("neo4j-cluster-affinity")
        if affinity:
            self._headers = {"neo4j-cluster-affinity": affinity}

    async def run(self, query: str, parameters: dict | None = None, **kwargs) -> HttpResult:
        r = await self._d._post(f"/tx/{self._id}", {"statement": query, "parameters": {**(parameters or {}), **kwargs}},
                                self._headers)
        return _result(r)

    async def commit(self) -> None:
        await self._d._post(f"/tx/{self._id}/commit", {}, self._headers)

    async def rollback(self) -> None:
        try:
            await self._d._request("DELETE", f"/tx/{self._id}", None, self._headers)
        except Exception:  # best effort: an abandoned transaction expires on its own
            pass


class HttpSession:
    def __init__(self, driver: "HttpDriver"):
        self._d = driver

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def close(self) -> None:
        return None

    async def run(self, query: str, parameters: dict | None = None, **kwargs) -> HttpResult:
        r = await self._d._post("", {"statement": query, "parameters": {**(parameters or {}), **kwargs}}, {})
        return _result(r)

    async def execute_write(self, fn, *args, **kwargs):
        tx = HttpTransaction(self._d)
        await tx.begin()
        try:
            out = await fn(tx, *args, **kwargs)
            await tx.commit()
            return out
        except BaseException:
            await tx.rollback()
            raise

    execute_read = execute_write


def _result(r: httpx.Response) -> HttpResult:
    data = r.json()["data"]
    return HttpResult(data["fields"], data["values"])


class HttpDriver:
    def __init__(self, host: str, username: str, password: str, database: str | None = None, verify: bool = True):
        self._base = f"https://{host}"
        self._database = database
        self._client = httpx.AsyncClient(auth=(username, password), verify=verify, timeout=httpx.Timeout(60, connect=10),
                                         headers={"Accept": "application/json", "Content-Type": "application/json"})

    def session(self, **_ignored) -> HttpSession:
        return HttpSession(self)

    async def verify_connectivity(self) -> None:
        await HttpSession(self).run("RETURN 1 AS ok")

    async def close(self) -> None:
        await self._client.aclose()

    async def _db(self) -> str:
        """Aura instances created before 2024 name their database after the instance id, not "neo4j"."""
        if self._database:
            return self._database
        r = await self._request("POST", "", {"statement": "SHOW DATABASES YIELD name RETURN name"}, {}, db="system")
        names = [row[0] for row in r.json()["data"]["values"] if row[0] != "system"]
        self._database = "neo4j" if "neo4j" in names else (names[0] if names else "neo4j")
        return self._database

    async def _post(self, suffix: str, body: dict, headers: dict) -> httpx.Response:
        return await self._request("POST", suffix, body, headers)

    async def _request(self, method: str, suffix: str, body: dict | None, headers: dict, db: str | None = None):
        db = db or await self._db()
        try:
            r = await self._client.request(method, f"{self._base}/db/{db}/query/v2{suffix}", json=body, headers=headers)
        except httpx.HTTPError as e:  # connect/read timeouts, TLS and DNS failures: all "can't reach it"
            raise ServiceUnavailable(f"{type(e).__name__}: {e}") from e
        if r.status_code < 300:
            return r
        if r.status_code in (401, 403):
            raise AuthError("Neo4j rejected the username/password")
        if r.status_code in (429, 502, 503, 504) or r.status_code >= 500:
            raise ServiceUnavailable(f"Neo4j answered HTTP {r.status_code}")
        try:
            msg = "; ".join(e.get("message", "") for e in r.json().get("errors", []))
        except ValueError:
            msg = r.text[:200]
        raise ClientError(msg or f"Neo4j answered HTTP {r.status_code}")
