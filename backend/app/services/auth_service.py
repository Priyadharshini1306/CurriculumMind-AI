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


def to_user_out(doc: dict) -> UserOut:
    return UserOut(id=str(doc["_id"]), name=doc["name"], email=doc["email"], role=Role.LEARNER)


async def _issue(doc: dict) -> TokenResponse:
    ttl = timedelta(minutes=get_settings().jwt_expire_minutes)
    sid = await sessions.create(str(doc["_id"]), now() + ttl)
    return TokenResponse(access_token=create_token(str(doc["_id"]), Role.LEARNER.value, sid), user=to_user_out(doc))


async def register(req: RegisterRequest) -> TokenResponse:
    doc = await users.create(req.name, req.email, hash_password(req.password), Role.LEARNER.value)
    if doc is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    try:
        await graph.ensure_learner(str(doc["_id"]))
    except Exception as e:  # Neo4j may be down; the Learner node is re-created lazily later
        log.warning("Could not create Learner node: %s", e)
    return await _issue(doc)


async def login(req: LoginRequest) -> TokenResponse:
    doc = await users.by_email(req.email)
    if not doc or not verify_password(req.password, doc["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return await _issue(doc)
