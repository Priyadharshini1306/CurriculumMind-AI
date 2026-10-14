import asyncio

from neo4j import AsyncDriver, AsyncGraphDatabase
from neo4j.exceptions import AuthError, ServiceUnavailable, SessionExpired

from app.core.config import get_settings

_driver: AsyncDriver | None = None


class Neo4jUnavailable(Exception):
    """Neo4j can't be used right now; the message says why and what to do about it."""


def explain(e: BaseException) -> str:
    """A readable reason for a Neo4j failure. Bare exceptions such as TimeoutError have an empty message, which used to
    surface to users as just "Neo4j save failed: "."""
    if isinstance(e, Neo4jUnavailable):
        return str(e)
    if isinstance(e, AuthError):
        return ("Neo4j rejected the login. Check NEO4J_USERNAME and NEO4J_PASSWORD in the server environment "
                "(the Aura password is only shown once, when the instance is created).")
    if isinstance(e, (ServiceUnavailable, SessionExpired, TimeoutError, ConnectionError, OSError)):
        return ("Cannot reach the Neo4j database. If you use Neo4j Aura Free, the instance is probably paused or "
                "deleted: open console.neo4j.io and resume it, and check that NEO4J_URI in the server environment "
                f"matches it. Then press Try again. ({type(e).__name__})")
    return f"{type(e).__name__}: {e}" if str(e) else type(e).__name__


async def ensure_reachable(timeout: float = 10) -> None:
    """Fail in seconds, with a clear message, instead of after minutes of retries inside a long job."""
    try:
        await asyncio.wait_for(get_driver().verify_connectivity(), timeout)
    except Exception as e:
        raise Neo4jUnavailable(explain(e)) from e


def get_driver() -> AsyncDriver:
    global _driver
    s = get_settings()
    if _driver is None:
        if not s.neo4j_uri:
            raise RuntimeError("NEO4J_URI is not configured")
        uri = s.neo4j_uri
        if s.neo4j_trust_self_signed:
            uri = uri.replace("neo4j+s://", "neo4j+ssc://").replace("bolt+s://", "bolt+ssc://")
        _driver = AsyncGraphDatabase.driver(
            uri, auth=(s.neo4j_username, s.neo4j_password),
            # Aura connections are dropped by NAT/idle timeouts: verify pooled connections before reuse
            # and recycle them often so a stale socket is never handed to a query.
            liveness_check_timeout=10, max_connection_lifetime=180, keep_alive=True,
            connection_acquisition_timeout=60, max_transaction_retry_time=30)
    return _driver


async def close() -> None:
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None
