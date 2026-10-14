import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import current_user
from app.core import neo4j
from app.core.mongo import get_db
from app.repositories.mongo_repository import DraftRepository, FeedbackRepository, now
from app.repositories import neo4j_repository
from app.schemas.concepts import ConceptGraph
from app.schemas.curriculum import Curriculum
from app.schemas.sequencing import PlanParams
from app.services import graph_service, graph_store_service, sequencing_service
from app.services.embedding_service import EmbeddingError
from app.services.llm_service import LLMError

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/graph", tags=["graph"])
drafts, feedback = DraftRepository(), FeedbackRepository()
STAGE = 2


class GraphBody(BaseModel):
    curriculum_id: str
    graph: ConceptGraph | None = None  # human-edited graph; the stored graph is used if omitted


class ReviseBody(GraphBody):
    feedback: str = Field(min_length=3, max_length=3000)


class RejectBody(GraphBody):
    feedback: str = Field(default="", max_length=3000)


async def _draft(curriculum_id: str, user: dict) -> dict:
    d = await drafts.get(curriculum_id, str(user["_id"]))
    if not d:
        raise HTTPException(404, "Curriculum not found")
    return d


def _payload(d: dict, graph: ConceptGraph | None) -> dict:
    return {"curriculum_id": str(d["_id"]), "graph_status": d.get("graph_status"),
            "error": d.get("graph_error"), "progress": d.get("graph_progress"), "graph": graph,
            "neo4j_status": d.get("neo4j_status"), "neo4j_error": d.get("neo4j_error"),
            "neo4j_summary": d.get("neo4j_summary"),
            "validation": graph_service.validate(graph) if graph else None}


def _graph_or_409(d: dict, body_graph: ConceptGraph | None) -> ConceptGraph:
    if body_graph is not None:
        return body_graph
    if not d.get("graph"):
        raise HTTPException(409, "No concept graph has been generated yet")
    return ConceptGraph.model_validate(d["graph"])


async def _set(draft_id, **fields) -> None:
    await get_db().curriculum_drafts.update_one({"_id": draft_id}, {"$set": {**fields, "updated_at": now()}})


@router.get("/{curriculum_id}")
async def get_graph(curriculum_id: str, user: dict = Depends(current_user)):
    d = await _draft(curriculum_id, user)
    return _payload(d, ConceptGraph.model_validate(d["graph"]) if d.get("graph") else None)


@router.post("/validate")
async def validate(body: GraphBody, user: dict = Depends(current_user)):
    d = await _draft(body.curriculum_id, user)
    return graph_service.validate(_graph_or_409(d, body.graph))


async def _revise_job(draft_id, graph: ConceptGraph, fb: str) -> None:
    try:
        revised = await graph_service.revise(graph, fb, graph_service.validate(graph))
        await _set(draft_id, graph=revised.model_dump(mode="json"), graph_status="PENDING_REVIEW",
                   graph_error=None, graph_progress=None)
    except LLMError as e:
        await _set(draft_id, graph_status="FAILED", graph_error=str(e))
    except Exception as e:
        log.exception("graph revision failed")
        await _set(draft_id, graph_status="FAILED", graph_error=f"Unexpected error: {e}")


@router.post("/revise", status_code=202)
async def revise(body: ReviseBody, bg: BackgroundTasks, user: dict = Depends(current_user)):
    d = await _draft(body.curriculum_id, user)
    if d.get("graph_status") not in ("PENDING_REVIEW", "FAILED"):
        raise HTTPException(409, f"Graph is {d.get('graph_status')}; cannot revise")
    graph = _graph_or_409(d, body.graph)
    await feedback.add(str(user["_id"]), body.curriculum_id, STAGE, "FEEDBACK", body.feedback)
    await get_db().curriculum_drafts.update_one(
        {"_id": d["_id"]}, {"$set": {"graph_status": "GENERATING", "graph_progress": "Revising graph"},
                            "$push": {"graph_history": d.get("graph")}})
    bg.add_task(_revise_job, d["_id"], graph, body.feedback)
    return {"curriculum_id": body.curriculum_id, "graph_status": "GENERATING"}


@router.post("/reject")
async def reject(body: RejectBody, user: dict = Depends(current_user)):
    d = await _draft(body.curriculum_id, user)
    if d.get("graph_status") != "PENDING_REVIEW":
        raise HTTPException(409, "Graph is not pending review")
    await feedback.add(str(user["_id"]), body.curriculum_id, STAGE, "REJECT", body.feedback or None)
    await _set(d["_id"], graph_status="REJECTED")
    return {"curriculum_id": body.curriculum_id, "graph_status": "REJECTED"}


@router.post("/verify")
async def verify(body: GraphBody, bg: BackgroundTasks, user: dict = Depends(current_user)):
    """Human Verification #2. Approval is refused while the graph has cycles or dangling references."""
    d = await _draft(body.curriculum_id, user)
    if d.get("graph_status") != "PENDING_REVIEW":
        raise HTTPException(409, f"Graph is {d.get('graph_status')}; only a graph pending review can be approved")
    graph = _graph_or_409(d, body.graph)
    report = graph_service.validate(graph)
    if report.blocking:
        raise HTTPException(422, {"message": "Graph is invalid and cannot be approved",
                                  "validation": report.model_dump()})
    await _set(d["_id"], graph=graph.model_dump(mode="json"), graph_status="APPROVED")
    await feedback.add(str(user["_id"]), body.curriculum_id, STAGE, "APPROVE")
    await _set(d["_id"], neo4j_status="SAVING", neo4j_error=None)
    bg.add_task(_save_job, d["_id"], body.curriculum_id, str(user["_id"]),
                Curriculum.model_validate(d["curriculum"]), graph)
    return _payload(await _draft(body.curriculum_id, user), graph)


async def _save_job(draft_id, curriculum_id: str, owner_id: str, cur: Curriculum, graph: ConceptGraph) -> None:
    """Store the approved graph in Neo4j. Failures are recorded (and retryable), never raised."""
    try:
        await neo4j.ensure_reachable()  # fail in seconds with a clear reason, not after minutes of retries
        summary = await graph_store_service.save(curriculum_id, owner_id, cur, graph)
        await _set(draft_id, neo4j_status="SAVED", neo4j_error=None, neo4j_summary=summary)
        # graph stored: draft the study plan immediately (fast, deterministic); the learner reviews it next
        plan = sequencing_service.generate(cur, graph, PlanParams())
        await _set(draft_id, plan=plan.model_dump(), plan_status="PENDING_REVIEW")
    except EmbeddingError as e:
        await _set(draft_id, neo4j_status="FAILED", neo4j_error=str(e))
    except Exception as e:
        log.exception("neo4j save failed")
        await _set(draft_id, neo4j_status="FAILED", neo4j_error=neo4j.explain(e))


@router.post("/save", status_code=202)
async def retry_save(body: GraphBody, bg: BackgroundTasks, user: dict = Depends(current_user)):
    d = await _draft(body.curriculum_id, user)
    if d.get("graph_status") != "APPROVED":
        raise HTTPException(409, "Graph must be approved before it is stored")
    if d.get("neo4j_status") == "SAVING":
        raise HTTPException(409, "Save already running")
    await _set(d["_id"], neo4j_status="SAVING", neo4j_error=None)
    bg.add_task(_save_job, d["_id"], body.curriculum_id, str(user["_id"]),
                Curriculum.model_validate(d["curriculum"]), ConceptGraph.model_validate(d["graph"]))
    return {"curriculum_id": body.curriculum_id, "neo4j_status": "SAVING"}


@router.get("/{curriculum_id}/knowledge")
async def knowledge(curriculum_id: str, user: dict = Depends(current_user)):
    """The stored knowledge graph, read back from Neo4j (concepts, prerequisites, outcomes, resources)."""
    await _draft(curriculum_id, user)
    try:
        kg = await neo4j_repository.get_knowledge_graph(curriculum_id, str(user["_id"]))
    except Exception as e:
        raise HTTPException(503, f"Neo4j unavailable: {e}")
    if kg is None:
        raise HTTPException(404, "Knowledge graph has not been stored in Neo4j yet")
    return kg
