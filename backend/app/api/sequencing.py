import logging

import networkx as nx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.api import resources as resources_api
from app.api.deps import current_user
from app.core.mongo import get_db
from app.repositories import neo4j_repository
from app.repositories.mongo_repository import DraftRepository, FeedbackRepository, now
from app.schemas.concepts import ConceptGraph
from app.schemas.curriculum import Curriculum
from app.schemas.sequencing import GenerateRequest, Plan, RejectRequest, VerifyRequest
from app.services import sequencing_service as svc

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sequencing", tags=["sequencing"])
drafts, feedback = DraftRepository(), FeedbackRepository()
STAGE = 3


async def _draft(curriculum_id: str, user: dict) -> dict:
    d = await drafts.get(curriculum_id, str(user["_id"]))
    if not d:
        raise HTTPException(404, "Curriculum not found")
    return d


def _require_graph(d: dict) -> tuple[Curriculum, ConceptGraph]:
    if d.get("graph_status") != "APPROVED" or not d.get("graph"):
        raise HTTPException(409, "The concept graph must be approved (Verification #2) before sequencing")
    return Curriculum.model_validate(d["curriculum"]), ConceptGraph.model_validate(d["graph"])


async def _set(draft_id, **fields) -> None:
    await get_db().curriculum_drafts.update_one({"_id": draft_id}, {"$set": {**fields, "updated_at": now()}})


def _payload(d: dict, graph: ConceptGraph | None) -> dict:
    plan = Plan.model_validate(d["plan"]) if d.get("plan") else None
    return {"curriculum_id": str(d["_id"]), "plan_status": d.get("plan_status"), "plan": plan,
            "structure": svc.structure(plan) if plan else None,
            "validation": svc.validate(plan, graph) if plan and graph else None,
            "concepts": [{"id": c.id, "name": c.name, "unit": c.unit, "difficulty": c.difficulty,
                          "estimated_minutes": c.estimated_minutes} for c in graph.concepts] if graph else [],
            "neo4j_status": d.get("plan_neo4j_status"), "neo4j_error": d.get("plan_neo4j_error")}


@router.post("/generate")
async def generate(req: GenerateRequest, user: dict = Depends(current_user)):
    """Steps 1-4: topological sort, difficulty-weighted effort, semester and week allocation."""
    d = await _draft(req.curriculum_id, user)
    cur, graph = _require_graph(d)
    if d.get("plan_status") == "APPROVED":
        raise HTTPException(409, "Plan already approved")
    try:
        plan = svc.generate(cur, graph, req.params)
    except nx.NetworkXUnfeasible:
        raise HTTPException(422, "The prerequisite graph contains a cycle; cannot sequence")
    if req.feedback:  # rejected/feedback flow: the reviewer changed constraints and asked for a re-sequence
        await feedback.add(str(user["_id"]), req.curriculum_id, STAGE, "FEEDBACK", req.feedback)
    await _set(d["_id"], plan=plan.model_dump(), plan_status="PENDING_REVIEW")
    return _payload(await _draft(req.curriculum_id, user), graph)


@router.get("/{curriculum_id}")
async def get_plan(curriculum_id: str, user: dict = Depends(current_user)):
    d = await _draft(curriculum_id, user)
    graph = ConceptGraph.model_validate(d["graph"]) if d.get("graph") else None
    return _payload(d, graph)


@router.post("/validate")
async def validate(req: VerifyRequest, user: dict = Depends(current_user)):
    d = await _draft(req.curriculum_id, user)
    _, graph = _require_graph(d)
    plan = req.plan or (Plan.model_validate(d["plan"]) if d.get("plan") else None)
    if plan is None:
        raise HTTPException(409, "No plan generated yet")
    return svc.validate(plan, graph)


async def _save_job(draft_id, curriculum_id: str, owner_id: str, plan: Plan, course: str = "") -> None:
    """Store the approved plan, enroll the learner, then find and check study resources (all automatic)."""
    try:
        await neo4j_repository.save_sequence(curriculum_id, owner_id, svc.structure(plan))
        await neo4j_repository.enroll(owner_id, curriculum_id)
        await _set(draft_id, plan_neo4j_status="SAVED", plan_neo4j_error=None)
    except Exception as e:
        log.exception("sequence save failed")
        await _set(draft_id, plan_neo4j_status="FAILED", plan_neo4j_error=str(e))
        return
    try:
        await resources_api._set(draft_id, resources_status="RUNNING", resources_error=None, resources_progress="0")
        await resources_api._job(draft_id, curriculum_id, owner_id, course, None)
        d = await get_db().curriculum_drafts.find_one({"_id": draft_id}, {"resources_status": 1})
        if d and d.get("resources_status") == "DONE":
            await resources_api._set(draft_id, analysis_status="RUNNING", analysis_error=None,
                                     analysis_progress="0", analysis_stage="analyze")
            await resources_api._analysis_job(draft_id, curriculum_id, owner_id, course, "analyze", None)
    except Exception:  # resources are a bonus: the learner can already study the plan
        log.exception("automatic resource step failed")


@router.post("/verify")
async def verify(req: VerifyRequest, bg: BackgroundTasks, user: dict = Depends(current_user)):
    """Human Verification #3. Prerequisite-order violations block approval; overloads only warn."""
    d = await _draft(req.curriculum_id, user)
    _, graph = _require_graph(d)
    if d.get("plan_status") != "PENDING_REVIEW":
        raise HTTPException(409, f"Plan is {d.get('plan_status')}; only a plan pending review can be approved")
    plan = req.plan or Plan.model_validate(d["plan"])
    report = svc.validate(plan, graph)
    if report.blocking:
        raise HTTPException(422, {"message": "Plan is invalid and cannot be approved", "validation": report.model_dump()})
    await _set(d["_id"], plan=plan.model_dump(), plan_status="APPROVED", plan_neo4j_status="SAVING", plan_neo4j_error=None)
    await feedback.add(str(user["_id"]), req.curriculum_id, STAGE, "APPROVE")
    bg.add_task(_save_job, d["_id"], req.curriculum_id, str(user["_id"]), plan,
                (d.get("curriculum") or {}).get("course", ""))
    return _payload(await _draft(req.curriculum_id, user), graph)


@router.post("/reject")
async def reject(req: RejectRequest, user: dict = Depends(current_user)):
    d = await _draft(req.curriculum_id, user)
    if d.get("plan_status") != "PENDING_REVIEW":
        raise HTTPException(409, "Plan is not pending review")
    await feedback.add(str(user["_id"]), req.curriculum_id, STAGE, "REJECT", req.feedback or None)
    await _set(d["_id"], plan_status="REJECTED")
    return {"curriculum_id": req.curriculum_id, "plan_status": "REJECTED"}
