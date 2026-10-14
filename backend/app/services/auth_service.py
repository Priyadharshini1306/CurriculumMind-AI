import asyncio
import logging
from datetime import timedelta

from fastapi import HTTPException, status

from app.core.config import get_settings
from app.core.security import create_token, hash_password, verify_password
from app.repositories import neo4j_repository as graph
from app.repositories.mongo_repository import SessionRepository, UserRepository, now
from app.schemas.auth import Role, LoginRequest, RegisterRequest, TokenResponse, UserOut

log = logging.getLogger(__name__)
users = UserRepository()
sessions = SessionRepository()
_background: set[asyncio.Task] = set()  # keeps fire-and-forget tasks alive until they finish


def to_user_out(doc: dict) -> UserOut:
    return UserOut(id=str(doc["_id"]), name=doc["name"], email=doc["email"], role=Role.LEARNER)


async def _issue(doc: dict) -> TokenResponse:
    ttl = timedelta(minutes=get_settings().jwt_expire_minutes)
    sid = await sessions.create(str(doc["_id"]), now() + ttl)
    return TokenResponse(access_token=create_token(str(doc["_id"]), Role.LEARNER.value, sid), user=to_user_out(doc))


async def _ensure_learner(user_id: str) -> None:
    try:
        await graph.ensure_learner(user_id)
    except Exception as e:  # Neo4j may be down or paused; enrolling MERGEs the Learner node later anyway
        log.warning("Could not create Learner node: %s", e)


async def register(req: RegisterRequest) -> TokenResponse:
    # bcrypt is deliberately slow CPU work: run it in a thread so it doesn't freeze every other request
    pw_hash = await asyncio.to_thread(hash_password, req.password)
    doc = await users.create(req.name, req.email, pw_hash, Role.LEARNER.value)
    if doc is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    # Signing up must not wait on Neo4j (a paused/slow instance made it hang for minutes): create the Learner node
    # in the background.
    task = asyncio.create_task(_ensure_learner(str(doc["_id"])))
    _background.add(task)
    task.add_done_callback(_background.discard)
    return await _issue(doc)


async def login(req: LoginRequest) -> TokenResponse:
    doc = await users.by_email(req.email)
    if not doc or not await asyncio.to_thread(verify_password, req.password, doc["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return await _issue(doc)
