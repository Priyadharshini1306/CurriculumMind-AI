from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError

from app.core.mongo import get_db


def now() -> datetime:
    return datetime.now(timezone.utc)


def _oid(value: str) -> ObjectId | None:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None


class UserRepository:
    async def create(self, name: str, email: str, password_hash: str, role: str) -> dict | None:
        doc = {"name": name, "email": email.lower(), "password_hash": password_hash,
               "role": role, "created_at": now(), "updated_at": now()}
        try:
            res = await get_db().users.insert_one(doc)
        except DuplicateKeyError:
            return None
        doc["_id"] = res.inserted_id
        return doc

    async def by_email(self, email: str) -> dict | None:
        return await get_db().users.find_one({"email": email.lower()})

    async def by_id(self, user_id: str) -> dict | None:
        oid = _oid(user_id)
        return await get_db().users.find_one({"_id": oid}) if oid else None


class SessionRepository:
    async def create(self, user_id: str, expires_at: datetime) -> str:
        res = await get_db().sessions.insert_one(
            {"user_id": user_id, "created_at": now(), "expires_at": expires_at})
        return str(res.inserted_id)

    async def exists(self, session_id: str) -> bool:
        oid = _oid(session_id)
        return bool(oid and await get_db().sessions.find_one({"_id": oid}))

    async def delete(self, session_id: str) -> None:
        oid = _oid(session_id)
        if oid:
            await get_db().sessions.delete_one({"_id": oid})


class UploadRepository:
    async def create(self, user_id: str, filename: str, file_type: str, size: int, path: str) -> dict:
        doc = {"user_id": user_id, "filename": filename, "file_type": file_type, "size_bytes": size,
               "path": path, "status": "PROCESSING", "error": None, "text": None,
               "uploaded_at": now()}
        doc["_id"] = (await get_db().uploads.insert_one(doc)).inserted_id
        return doc

    async def finish(self, upload_id, text, error) -> None:
        await get_db().uploads.update_one({"_id": upload_id}, {"$set": {
            "status": "FAILED" if error else "PROCESSED", "error": error, "text": text}})

    async def set_curriculum(self, upload_id, curriculum_id: str) -> None:
        await get_db().uploads.update_one({"_id": upload_id}, {"$set": {"curriculum_id": curriculum_id}})

    async def get(self, upload_id: str, user_id: str) -> dict | None:
        oid = _oid(upload_id)
        return await get_db().uploads.find_one({"_id": oid, "user_id": user_id}) if oid else None

    async def list(self, user_id: str) -> list[dict]:
        cur = get_db().uploads.find({"user_id": user_id}, {"text": 0}).sort("uploaded_at", -1).limit(100)
        return await cur.to_list(100)


class GoalRepository:
    """Learning goals live in curriculum_drafts (source=GOAL) until extraction turns them into a draft."""
    async def create(self, user_id: str, data: dict) -> dict:
        doc = {"user_id": user_id, "source": "GOAL", "status": "GOAL_RECEIVED", **data, "created_at": now()}
        doc["_id"] = (await get_db().curriculum_drafts.insert_one(doc)).inserted_id
        return doc

    async def get(self, goal_id: str, user_id: str) -> dict | None:
        oid = _oid(goal_id)
        return await get_db().curriculum_drafts.find_one(
            {"_id": oid, "user_id": user_id, "source": "GOAL"}) if oid else None


class DraftRepository:
    async def create(self, user_id: str, source: str, ref_id: str) -> dict:
        doc = {"user_id": user_id, "source": source, "source_ref": ref_id, "status": "EXTRACTING",
               "error": None, "revision": 0, "curriculum": None, "history": [], "created_at": now()}
        doc["_id"] = (await get_db().curriculum_drafts.insert_one(doc)).inserted_id
        return doc

    async def get(self, draft_id: str, user_id: str) -> dict | None:
        oid = _oid(draft_id)
        if not oid:
            return None
        return await get_db().curriculum_drafts.find_one(
            {"_id": oid, "user_id": user_id, "source": {"$in": ["UPLOAD", "GOAL_DRAFT"]}})

    async def list(self, user_id: str) -> list[dict]:
        cur = get_db().curriculum_drafts.find(
            {"user_id": user_id, "source": {"$in": ["UPLOAD", "GOAL_DRAFT"]}}).sort("created_at", -1).limit(100)
        return await cur.to_list(100)

    async def set_curriculum(self, draft_id, curriculum: dict, status: str, revision: int | None = None) -> None:
        fields = {"curriculum": curriculum, "status": status, "error": None, "updated_at": now()}
        if revision is not None:
            fields["revision"] = revision
        await get_db().curriculum_drafts.update_one({"_id": draft_id}, {"$set": fields})

    async def fail(self, draft_id, error: str) -> None:
        await get_db().curriculum_drafts.update_one(
            {"_id": draft_id}, {"$set": {"status": "FAILED", "error": error, "updated_at": now()}})


class FeedbackRepository:
    async def add(self, user_id: str, draft_id: str, stage: int, action: str, feedback: str | None = None) -> None:
        await get_db().verification_feedback.insert_one(
            {"user_id": user_id, "draft_id": draft_id, "stage": stage, "action": action,
             "feedback": feedback, "created_at": now()})


class CatalogRepository:
    """Curricula that can be followed: the owner's own approved ones plus ones published by instructors."""
    READY = {"source": {"$in": ["UPLOAD", "GOAL_DRAFT"]}, "plan_status": "APPROVED", "plan_neo4j_status": "SAVED"}

    async def get(self, curriculum_id: str) -> dict | None:
        oid = _oid(curriculum_id)
        return await get_db().curriculum_drafts.find_one({"_id": oid, **self.READY}) if oid else None

    async def mine(self, user_id: str) -> list[dict]:
        cur = get_db().curriculum_drafts.find({**self.READY, "user_id": user_id}, {"curriculum": 1, "published": 1})
        return await cur.to_list(100)



class QuizRepository:
    """Quiz generation jobs and the learner quiz-attempt history (questions themselves live in Neo4j)."""
    async def add_attempt(self, doc: dict) -> str:
        return str((await get_db().quiz_attempts.insert_one({**doc, "attempted_at": now()})).inserted_id)

    async def history(self, user_id: str, curriculum_id: str | None = None, limit: int = 100) -> list[dict]:
        q = {"user_id": user_id, **({"curriculum_id": curriculum_id} if curriculum_id else {})}
        cur = get_db().quiz_attempts.find(q, {"results": 0}).sort("attempted_at", -1).limit(limit)
        return await cur.to_list(limit)



# ------------------------------------------------------------------ resilience
# Atlas connections are sometimes reset by the network. pymongo retries a failed read/write once; on top of that,
# read-only repository methods are retried a few more times on connection-level errors. Inserts are deliberately
# excluded (a lost response could duplicate them); pymongo's own retryable-writes logic covers those safely.
import asyncio as _asyncio
import functools as _functools
import inspect as _inspect
import logging as _logging

from pymongo.errors import AutoReconnect as _AutoReconnect
from pymongo.errors import NetworkTimeout as _NetworkTimeout
from pymongo.errors import ServerSelectionTimeoutError as _SelectionTimeout

_log = _logging.getLogger(__name__)
_READ_PREFIXES = ("get", "by_", "exists", "list", "mine", "history")
_TRANSIENT = (_AutoReconnect, _NetworkTimeout, _SelectionTimeout)


def _retrying(fn):
    @_functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        for attempt in range(3):
            try:
                return await fn(*args, **kwargs)
            except _TRANSIENT as e:
                if attempt == 2:
                    raise
                _log.warning("mongo %s failed (%s); retrying", fn.__name__, type(e).__name__)
                await _asyncio.sleep(1.0 * (attempt + 1))
    return wrapper


for _cls in (UserRepository, SessionRepository, UploadRepository, GoalRepository, DraftRepository,
             CatalogRepository, QuizRepository):
    for _name, _fn in list(vars(_cls).items()):
        if _inspect.iscoroutinefunction(_fn) and _name.startswith(_READ_PREFIXES):
            setattr(_cls, _name, _retrying(_fn))
