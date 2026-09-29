from pymongo import AsyncMongoClient

from app.core.config import get_settings

_client: AsyncMongoClient | None = None


def get_db():
    global _client
    s = get_settings()
    if _client is None:
        if not s.mongodb_uri:
            raise RuntimeError("MONGODB_URI is not configured")
        # The network drops idle sockets (WinError 121/10054) and reconnecting to Atlas is slow. A small warm pool plus the
        # keep-alive ping in main.py (well inside maxIdleTimeMS) means requests almost never pay for a new connection.
        _client = AsyncMongoClient(s.mongodb_uri, serverSelectionTimeoutMS=15000, connectTimeoutMS=10000, socketTimeoutMS=10000,
                                   maxIdleTimeMS=120000, minPoolSize=3)
    return _client[s.mongodb_db]


async def init_indexes() -> None:
    db = get_db()
    await db.users.create_index("email", unique=True)
    await db.sessions.create_index("expires_at", expireAfterSeconds=0)
    await db.uploads.create_index("user_id")
    await db.curriculum_drafts.create_index("user_id")
    await db.quiz_attempts.create_index([("user_id", 1), ("attempted_at", -1)])


async def close() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
