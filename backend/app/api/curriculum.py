import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.api import concepts as concepts_api
from app.api.deps import current_user
from app.core.mongo import get_db
from app.repositories.mongo_repository import (DraftRepository, FeedbackRepository, GoalRepository,
                                               UploadRepository)
from app.schemas.curriculum import Curriculum, DraftOut, ExtractRequest, ReviseRequest, VerifyRequest
from app.services import curriculum_service as svc
from app.services.llm_service import LLMError

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/curriculum", tags=["curriculum"])
drafts, feedback, uploads, goals = DraftRepository(), FeedbackRepository(), UploadRepository(), GoalRepository()
VERIFICATION_STAGE = 1


def _out(d: dict) -> dict:
    return {**d, "id": str(d["_id"])}


async def _get_or_404(draft_id: str, user: dict) -> dict:
    d = await drafts.get(draft_id, str(user["_id"]))
    if not d:
        raise HTTPException(404, "Curriculum draft not found")
    return d


def _with_default_version(c: Curriculum) -> Curriculum:
    if not c.version:
        c.version = str(datetime.now(timezone.utc).year)
    return c


async def _run(draft_id, coro_factory, revision: int | None = None) -> None:
    try:
        curriculum = _with_default_version(await coro_factory())
        await drafts.set_curriculum(draft_id, curriculum.model_dump(), "PENDING_REVIEW", revision)
    except LLMError as e:
        await drafts.fail(draft_id, str(e))
    except Exception as e:  # keep the draft from being stuck in EXTRACTING
        log.exception("curriculum job failed")
        await drafts.fail(draft_id, f"Unexpected error: {e}")


@router.post("/extract", response_model=DraftOut, status_code=202)
async def extract(req: ExtractRequest, bg: BackgroundTasks, user: dict = Depends(current_user)):
    uid = str(user["_id"])
    if bool(req.upload_id) == bool(req.goal_id):
        raise HTTPException(422, "Provide exactly one of upload_id or goal_id")
    if req.upload_id:
        up = await uploads.get(req.upload_id, uid)
        if not up:
            raise HTTPException(404, "Upload not found")
        if up["status"] != "PROCESSED" or not up.get("text"):
            raise HTTPException(409, "Upload has not been processed successfully")
        draft = await drafts.create(uid, "UPLOAD", req.upload_id)
        text = up["text"]
        bg.add_task(_run, draft["_id"], lambda: svc.from_syllabus(text))
    else:
        goal = await goals.get(req.goal_id, uid)
        if not goal:
            raise HTTPException(404, "Goal not found")
        draft = await drafts.create(uid, "GOAL_DRAFT", req.goal_id)
        bg.add_task(_run, draft["_id"], lambda: svc.from_goal(goal))
    return _out(draft)


@router.get("", response_model=list[DraftOut])
async def list_drafts(user: dict = Depends(current_user)):
    return [_out(d) for d in await drafts.list(str(user["_id"]))]


@router.get("/{curriculum_id}", response_model=DraftOut)
async def get_draft(curriculum_id: str, user: dict = Depends(current_user)):
    return _out(await _get_or_404(curriculum_id, user))


@router.post("/revise", response_model=DraftOut, status_code=202)
async def revise(req: ReviseRequest, bg: BackgroundTasks, user: dict = Depends(current_user)):
    d = await _get_or_404(req.curriculum_id, user)
    if d["status"] != "PENDING_REVIEW":
        raise HTTPException(409, f"Draft is {d['status']}; only drafts pending review can be revised")
    current = req.curriculum or Curriculum.model_validate(d["curriculum"])
    await feedback.add(str(user["_id"]), req.curriculum_id, VERIFICATION_STAGE, "FEEDBACK", req.feedback)
    await get_db().curriculum_drafts.update_one(
        {"_id": d["_id"]}, {"$set": {"status": "EXTRACTING"}, "$push": {"history": d["curriculum"]}})
    bg.add_task(_run, d["_id"], lambda: svc.revise(current, req.feedback), d["revision"] + 1)
    d["status"] = "EXTRACTING"
    return _out(d)


@router.post("/verify", response_model=DraftOut)
async def verify(req: VerifyRequest, bg: BackgroundTasks, user: dict = Depends(current_user)):
    """Human Verification #1: approve the (possibly edited) curriculum. Nothing proceeds until this succeeds."""
    d = await _get_or_404(req.curriculum_id, user)
    if d["status"] != "PENDING_REVIEW":
        raise HTTPException(409, f"Draft is {d['status']}; only drafts pending review can be approved")
    await drafts.set_curriculum(d["_id"], req.curriculum.model_dump(), "APPROVED")
    await feedback.add(str(user["_id"]), req.curriculum_id, VERIFICATION_STAGE, "APPROVE")
    # approved: start building the concept map right away (the next human gate is the graph review)
    await get_db().curriculum_drafts.update_one({"_id": d["_id"]}, {"$set": {
        "graph_status": "GENERATING", "graph_error": None, "graph_progress": "Starting", "graph": None}})
    bg.add_task(concepts_api._run, d["_id"], req.curriculum)
    return _out(await _get_or_404(req.curriculum_id, user))
