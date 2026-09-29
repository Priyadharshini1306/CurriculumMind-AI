import asyncio

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import current_user
from app.repositories import neo4j_repository as graph
from app.repositories.mongo_repository import CatalogRepository, QuizRepository
from app.services import adaptive_service, dashboard_service as ds
from app.services import gap_service, learning_path_service as lp
from app.services import mastery_service as ms

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])
catalog, quizzes = CatalogRepository(), QuizRepository()


async def _neo(coro):
    try:
        return await coro
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(503, f"Neo4j unavailable: {e}")


async def _course_for(user_id: str, curriculum_id: str | None) -> str:
    followed = await _neo(graph.followed_courses(user_id))
    if curriculum_id:
        if not any(f["course_id"] == curriculum_id for f in followed):
            raise HTTPException(404, "Not enrolled in that course")
        return curriculum_id
    if not followed:
        raise HTTPException(404, "Not enrolled in any course yet")
    return followed[0]["course_id"]


@router.get("/learner/{user_id}")
async def learner_dashboard(user_id: str, curriculum_id: str | None = None, user: dict = Depends(current_user)):
    if user_id != str(user["_id"]):
        raise HTTPException(403, "You can only view your own dashboard")
    course_id = await _course_for(user_id, curriculum_id)
    d = await catalog.get(course_id)
    hours = ((d or {}).get("plan") or {}).get("params", {}).get("hours_per_week", 8)

    # Sequential on purpose: one warm database connection is reused, whereas parallel queries each open a new one,
    # which is much slower on a high-latency link.
    rows = await _neo(graph.path_rows(course_id, user_id))
    mastery_rows = await _neo(graph.mastery_for_course(user_id, course_id))
    adaptive = await _neo(adaptive_service.preview(user_id, course_id, hours))
    history = await quizzes.history(user_id, course_id, 50)
    path = lp.assemble(rows)

    current_items = []
    if path["current"]:
        cur_ids = set(path["current"]["concept_ids"])
        for s in path["semesters"]:
            for w in s["weeks"]:
                for c in w["concepts"]:
                    if c["id"] in cur_ids and len(current_items) < 6:
                        current_items.append({"concept_id": c["id"], "concept": c["name"], "status": c["status"],
                                              "mastery": c["mastery"], "resource": (c["resources"] or [None])[0]})
    names = {r["concept_id"]: r["concept"] for r in mastery_rows}
    trend = [{"n": i + 1, "percent": h["percent"], "concept_id": h["concept_id"], "attempted_at": h["attempted_at"]}
             for i, h in enumerate(reversed(history))]
    weak = [g for g in adaptive["gaps"]]
    return {
        "user_id": user_id, "curriculum_id": course_id,
        "position": path["current"] and {"semester": path["current"]["semester"], "week": path["current"]["week"]},
        "progress": path["progress"],
        "mastery": {
            "by_unit": ds.unit_mastery(mastery_rows),
            "counts": {s: sum(ms.classify(r["mastery_score"]) == s for r in mastery_rows)
                       for s in ("MASTERED", "LEARNING", "WEAK", "NOT_STARTED")},
        },
        "this_week": current_items,
        "weak_concepts": weak,
        "adaptive": {"summary": adaptive["summary"],
                     "next": [i for w in adaptive["weeks"][:1] for i in w["items"]][:5]},
        "quiz_trend": trend,
        "recent_attempts": [{"concept_id": h["concept_id"], "concept": names.get(h["concept_id"], h["concept_id"]),
                             "score": h["score"], "total": h["total"],
                             "percent": h["percent"], "attempted_at": h["attempted_at"]} for h in history[:5]],
    }
