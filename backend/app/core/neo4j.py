from neo4j import AsyncDriver, AsyncGraphDatabase

from app.core.config import get_settings

_driver: AsyncDriver | None = None


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
