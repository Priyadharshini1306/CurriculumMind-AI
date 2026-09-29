from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import current_user
from app.repositories import neo4j_repository as graph
from app.repositories.mongo_repository import CatalogRepository
from app.services import adaptive_service

router = APIRouter(prefix="/api/adaptive-path", tags=["adaptive"])
catalog = CatalogRepository()


class GenerateRequest(BaseModel):
    curriculum_id: str
    hours_per_week: float | None = Field(default=None, ge=1, le=80)


@router.post("/generate")
async def generate(req: GenerateRequest, user: dict = Depends(current_user)):
    """Re-plan the remaining path from mastery, weak concepts and prerequisites (deterministic, no LLM)."""
    uid = str(user["_id"])
    try:
        followed = await graph.followed_courses(uid)
    except Exception as e:
        raise HTTPException(503, f"Neo4j unavailable: {e}")
    if not any(f["course_id"] == req.curriculum_id for f in followed):
        raise HTTPException(403, "Enroll in the course first")
    d = await catalog.get(req.curriculum_id)
    hours = req.hours_per_week or ((d or {}).get("plan") or {}).get("params", {}).get("hours_per_week", 8)
    try:
        return {"curriculum_id": req.curriculum_id, "hours_per_week": hours,
                **await adaptive_service.generate(uid, req.curriculum_id, hours)}
    except Exception as e:
        raise HTTPException(503, f"Neo4j unavailable: {e}")
