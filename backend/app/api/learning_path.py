from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import current_user
from app.repositories import neo4j_repository as graph
from app.repositories.mongo_repository import CatalogRepository
from app.services import learning_path_service as svc

router = APIRouter(prefix="/api/learning-path", tags=["learning-path"])
catalog = CatalogRepository()


class CurriculumRef(BaseModel):
    curriculum_id: str


async def _neo(coro):
    try:
        return await coro
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(503, f"Neo4j unavailable: {e}")


@router.post("/enroll", status_code=201)
async def enroll(ref: CurriculumRef, user: dict = Depends(current_user)):
    """Follow one of your own finished courses (this also happens automatically when the study plan is approved)."""
    d = await catalog.get(ref.curriculum_id)
    uid = str(user["_id"])
    if not d or d["user_id"] != uid:
        raise HTTPException(404, "Course not found")
    if not await _neo(graph.enroll(uid, ref.curriculum_id)):
        raise HTTPException(409, "The course has not been stored in the knowledge graph yet")
    return {"curriculum_id": ref.curriculum_id, "enrolled": True}


@router.get("/{user_id}")
async def get_path(user_id: str, curriculum_id: str | None = None, user: dict = Depends(current_user)):
    """Semester -> week -> concept -> recommended resources, with your mastery and current position."""
    if user_id != str(user["_id"]):
        raise HTTPException(403, "You can only view your own learning path")
    followed = await _neo(graph.followed_courses(user_id))
    if not followed:
        raise HTTPException(404, "Not enrolled in any course yet")
    chosen = next((f for f in followed if f["course_id"] == curriculum_id), None) if curriculum_id else followed[0]
    if not chosen:
        raise HTTPException(404, "Not enrolled in that course")
    cid = chosen["course_id"]
    path = svc.assemble(await _neo(graph.path_rows(cid, user_id)))
    if path["current"]:  # keep LEARNING links in sync with the current week
        await _neo(graph.set_learning(user_id, cid, path["current"]["concept_ids"], svc.MASTERY_THRESHOLD))
    return {"course": chosen, "user_id": user_id, **path}
