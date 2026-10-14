import asyncio
import logging
import socket

from neo4j import AsyncDriver, AsyncGraphDatabase
from neo4j.exceptions import AuthError, ServiceUnavailable, SessionExpired

from app.core.config import get_settings

log = logging.getLogger(__name__)
_driver = None  # AsyncDriver (Bolt) or HttpDriver (HTTPS), same interface for the repository


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
        return ("Cannot reach the Neo4j database. Check that the Aura instance is running (not paused or deleted) and "
                "that NEO4J_URI in the server environment matches it. If the instance is running, your network may "
                "block outbound port 7687: set NEO4J_TRANSPORT=http to use port 443 instead. "
                f"Then press Try again. ({type(e).__name__})")
    return f"{type(e).__name__}: {e}" if str(e) else type(e).__name__


async def ensure_reachable(timeout: float = 10) -> None:
    """Fail in seconds, with a clear message, instead of after minutes of retries inside a long job."""
    try:
        await asyncio.wait_for(get_driver().verify_connectivity(), timeout)
    except Exception as e:
        raise Neo4jUnavailable(explain(e)) from e


def _bolt_port_open(uri: str) -> bool:
    """Quick TCP check of the Bolt port, to choose a transport once at startup."""
    host_port = uri.split("://", 1)[1].split("/")[0]
    host, _, port = host_port.partition(":")
    try:
        socket.create_connection((host, int(port or 7687)), timeout=4).close()
        return True
    except OSError:
        return False


def get_driver():
    global _driver
    s = get_settings()
    if _driver is None:
        if not s.neo4j_uri:
            raise RuntimeError("NEO4J_URI is not configured")
        uri = s.neo4j_uri
        host = uri.split("://", 1)[1].split("/")[0].split(":")[0]
        tls = uri.split("://", 1)[0].endswith(("+s", "+ssc"))  # only TLS (Aura) URIs have an HTTPS twin
        mode = s.neo4j_transport.lower()
        if mode == "auto":
            mode = "bolt" if (not tls or _bolt_port_open(uri)) else "http"
            if mode == "http":
                log.warning("Neo4j Bolt port is not reachable from here; using HTTPS (port 443) instead")
        if mode == "http":
            from app.core.neo4j_http import HttpDriver
            _driver = HttpDriver(host, s.neo4j_username, s.neo4j_password, s.neo4j_database or None,
                                 verify=not s.neo4j_trust_self_signed)
            return _driver
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
