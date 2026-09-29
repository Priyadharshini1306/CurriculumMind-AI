import time

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import decode_token
from app.repositories.mongo_repository import SessionRepository, UserRepository

bearer = HTTPBearer(auto_error=False)

# Checking the session and loading the user are two MongoDB round-trips; with a distant Atlas cluster that alone can
# take seconds per request. A verified session is therefore remembered briefly. Logging out evicts it immediately;
# a session revoked any other way is honoured within CACHE_TTL seconds.
CACHE_TTL = 30
_sessions: dict[str, tuple[float, dict]] = {}


def evict_session(session_id: str) -> None:
    _sessions.pop(session_id, None)


async def current_claims(cred: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    claims = decode_token(cred.credentials) if cred else None
    if not claims:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    sid, now = claims.get("sid", ""), time.monotonic()
    hit = _sessions.get(sid)
    if hit and hit[0] > now:
        return {**claims, "_user": hit[1]}
    if not sid or not await SessionRepository().exists(sid):
        _sessions.pop(sid, None)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    user = await UserRepository().by_id(claims["sub"])
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")
    if len(_sessions) > 2000:  # drop expired entries so the cache cannot grow without bound
        for k in [k for k, (exp, _) in _sessions.items() if exp <= now]:
            _sessions.pop(k, None)
    _sessions[sid] = (now + CACHE_TTL, user)
    return {**claims, "_user": user}


async def current_user(claims: dict = Depends(current_claims)) -> dict:
    return claims["_user"]
