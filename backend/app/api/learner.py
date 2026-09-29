from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import current_user
from app.repositories import neo4j_repository as graph
from app.services import adaptive_service
from app.services import mastery_service as ms

router = APIRouter(prefix="/api/learner", tags=["learner"])


def _check_access(user: dict, user_id: str) -> None:
    if user_id != str(user["_id"]):
        raise HTTPException(403, "You can only view your own data")


async def _resolve_course(user_id: str, curriculum_id: str | None) -> str:
    try:
        followed = await graph.followed_courses(user_id)
    except Exception as e:
        raise HTTPException(503, f"Neo4j unavailable: {e}")
    if curriculum_id:
        if not any(f["course_id"] == curriculum_id for f in followed):
            raise HTTPException(404, "Not enrolled in that course")
        return curriculum_id
    if not followed:
        raise HTTPException(404, "Not enrolled in any course yet")
    return followed[0]["course_id"]


@router.get("/{user_id}/mastery")
async def mastery(user_id: str, curriculum_id: str | None = None, user: dict = Depends(current_user)):
    """Concept-level mastery stored in Neo4j (Learner -[:MASTERED]-> Concept) for one enrolled course."""
    _check_access(user, user_id)
    course_id = await _resolve_course(user_id, curriculum_id)
    try:
        rows = await graph.mastery_for_course(user_id, course_id)
    except Exception as e:
        raise HTTPException(503, f"Neo4j unavailable: {e}")
    concepts = [{**r, "status": ms.classify(r["mastery_score"])} for r in rows]
    started = [c for c in concepts if c["mastery_score"] is not None]
    return {
        "user_id": user_id, "curriculum_id": course_id, "concepts": concepts,
        "summary": {
            "total": len(concepts), "started": len(started),
            "mastered": sum(c["status"] == "MASTERED" for c in concepts),
            "weak": sum(c["status"] == "WEAK" for c in concepts),
            "average_mastery": round(sum(c["mastery_score"] for c in started) / len(started), 3) if started else None,
        },
    }


@router.get("/{user_id}/gaps")
async def gaps(user_id: str, curriculum_id: str | None = None, user: dict = Depends(current_user)):
    """Knowledge gaps: weak concepts and the prerequisite concepts to fix first (recomputed from current mastery)."""
    _check_access(user, user_id)
    course_id = await _resolve_course(user_id, curriculum_id)
    try:
        found = await adaptive_service.detect_and_store_gaps(user_id, course_id)
    except Exception as e:
        raise HTTPException(503, f"Neo4j unavailable: {e}")
    return {"user_id": user_id, "curriculum_id": course_id, "gaps": found,
            "summary": {"weak": sum(g["kind"] == "WEAK" for g in found),
                        "prerequisite_gaps": sum(g["kind"].startswith("PREREQUISITE") for g in found)}}
