import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.api.deps import current_user
from app.core.mongo import get_db
from app.repositories.mongo_repository import DraftRepository, now
from app.schemas.concepts import ConceptGraph, GenerateRequest
from app.schemas.curriculum import Curriculum
from app.services import concept_service
from app.services.llm_service import LLMError

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/concepts", tags=["concepts"])
drafts = DraftRepository()


async def _set(draft_id, **fields) -> None:
    await get_db().curriculum_drafts.update_one({"_id": draft_id}, {"$set": {**fields, "updated_at": now()}})


async def _run(draft_id, cur: Curriculum) -> None:
    async def progress(msg: str) -> None:
        await _set(draft_id, graph_progress=msg)
    try:
        graph = await concept_service.build_graph(cur, progress)
        await _set(draft_id, graph=graph.model_dump(mode="json"), graph_status="PENDING_REVIEW",
                   graph_error=None, graph_progress=None)
    except LLMError as e:
        await _set(draft_id, graph_status="FAILED", graph_error=str(e))
    except Exception as e:
        log.exception("concept generation failed")
        await _set(draft_id, graph_status="FAILED", graph_error=f"Unexpected error: {e}")


@router.post("/generate", status_code=202)
async def generate(req: GenerateRequest, bg: BackgroundTasks, user: dict = Depends(current_user)):
    d = await drafts.get(req.curriculum_id, str(user["_id"]))
    if not d:
        raise HTTPException(404, "Curriculum not found")
    if d["status"] != "APPROVED":
        raise HTTPException(409, "Curriculum must be approved (Verification #1) before concept generation")
    if d.get("graph_status") == "GENERATING":
        raise HTTPException(409, "Concept generation already running")
    await _set(d["_id"], graph_status="GENERATING", graph_error=None, graph_progress="Starting")
    bg.add_task(_run, d["_id"], Curriculum.model_validate(d["curriculum"]))
    return {"curriculum_id": req.curriculum_id, "graph_status": "GENERATING"}


@router.get("/{curriculum_id}")
async def get_concepts(curriculum_id: str, user: dict = Depends(current_user)):
    d = await drafts.get(curriculum_id, str(user["_id"]))
    if not d:
        raise HTTPException(404, "Curriculum not found")
    graph = ConceptGraph.model_validate(d["graph"]) if d.get("graph") else None
    return {"curriculum_id": curriculum_id, "graph_status": d.get("graph_status"),
            "progress": d.get("graph_progress"), "error": d.get("graph_error"), "graph": graph}
