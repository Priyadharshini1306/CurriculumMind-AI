"""A learner's courses and where each one is in the pipeline (the UI is built around this)."""
import logging
from datetime import timezone
from pathlib import Path

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.api import concepts as concepts_api
from app.api import curriculum as curriculum_api
from app.api import graph as graph_api
from app.api import sequencing as sequencing_api
from app.api.deps import current_user
from app.core.mongo import get_db
from app.repositories import neo4j_repository as neo4j
from app.repositories.mongo_repository import now
from app.schemas.concepts import ConceptGraph
from app.schemas.curriculum import Curriculum
from app.schemas.sequencing import Plan
from app.services import curriculum_service
from app.services import dashboard_service as ds

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/courses", tags=["courses"])
KINDS = {"$in": ["UPLOAD", "GOAL_DRAFT"]}

STEPS = ["Syllabus", "Curriculum", "Concept map", "Study plan", "Set-up", "Learn"]
# A background job runs detached from any request, so if the server process restarts or crashes mid-job (a
# deploy, a crash) it can leave a course "busy" forever with nothing left running to ever finish it or mark it
# failed. STALE_SECONDS is generous headroom above how long the slowest real step (building a large concept map)
# actually takes, so a course past it is orphaned, not just slow.
STALE_SECONDS = 25 * 60


def _stale(d: dict) -> bool:
    ts = d.get("updated_at")
    if not ts:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (now() - ts).total_seconds() > STALE_SECONDS


async def _heal(d: dict) -> dict:
    """Recover a course stuck in an orphaned busy state: fall back to the last result that is still usable, or
    mark the step failed so the learner gets a normal retry button instead of a page that never moves."""
    updates: dict = {}
    if d.get("status") == "EXTRACTING" and _stale(d):
        updates["status"], updates["error"] = "FAILED", "This was taking too long and may have been interrupted."
    if d.get("graph_status") == "GENERATING" and _stale(d):
        if d.get("graph"):  # a revision was interrupted; the concept map from before it is still valid
            updates["graph_status"], updates["graph_error"] = "PENDING_REVIEW", None
        else:
            updates["graph_status"], updates["graph_error"] = "FAILED", "This was taking too long and may have been interrupted."
    if d.get("neo4j_status") == "SAVING" and _stale(d):
        updates["neo4j_status"], updates["neo4j_error"] = "FAILED", "This was taking too long and may have been interrupted."
    if d.get("plan_neo4j_status") == "SAVING" and _stale(d):
        updates["plan_neo4j_status"], updates["plan_neo4j_error"] = "FAILED", "This was taking too long and may have been interrupted."
    if not updates:
        return d
    await get_db().curriculum_drafts.update_one({"_id": d["_id"]}, {"$set": {**updates, "updated_at": now()}})
    return {**d, **updates}


def stage_of(d: dict) -> dict:
    """Where a course is: which step, whether the system is busy, what the learner should do next."""
    def s(step, key, label, detail=None, busy=False, action=None, retry=None, error=None):
        return {"step": step, "key": key, "label": label, "detail": detail, "busy": busy, "action": action,
                "retry": retry, "error": error, "ready": key == "ready"}

    if d.get("status") == "FAILED":
        return s(1, "extract_failed", "We couldn't read this syllabus", d.get("error"), retry="extract", error=d.get("error"))
    if d.get("status") == "EXTRACTING" or not d.get("curriculum"):
        return s(1, "extracting", "Reading your syllabus", "The AI is finding units, topics and outcomes. This usually takes 1-3 minutes.", busy=True)
    if d.get("status") == "PENDING_REVIEW":
        return s(2, "review_curriculum", "Check your curriculum", "Fix anything the AI got wrong, then approve.", action="curriculum")

    gs = d.get("graph_status")
    if gs in (None, "GENERATING"):
        return s(3, "building_concepts", "Building your concept map",
                 d.get("graph_progress") or "Finding concepts and how they depend on each other. This can take several minutes.", busy=True)
    if gs == "FAILED":
        return s(3, "concepts_failed", "The concept map could not be built", d.get("graph_error"), retry="concepts", error=d.get("graph_error"))
    if gs in ("PENDING_REVIEW", "REJECTED"):
        return s(3, "review_graph", "Check your concept map", "Make sure the prerequisites make sense, then approve.", action="graph")
    ns = d.get("neo4j_status")
    if ns == "FAILED":
        return s(3, "graph_save_failed", "The concept map could not be saved", d.get("neo4j_error"), retry="graph_save", error=d.get("neo4j_error"))
    if ns != "SAVED":
        return s(3, "saving_graph", "Saving your concept map", busy=True)

    ps = d.get("plan_status")
    if ps is None:
        return s(4, "planning", "Drafting your study plan", busy=True)
    if ps in ("PENDING_REVIEW", "REJECTED"):
        return s(4, "review_plan", "Set your study plan", "Choose your weekly hours and adjust the schedule, then approve.", action="plan")
    pns = d.get("plan_neo4j_status")
    if pns == "FAILED":
        return s(5, "plan_save_failed", "Your plan could not be saved", d.get("plan_neo4j_error"), retry="plan_save", error=d.get("plan_neo4j_error"))
    if pns != "SAVED":
        return s(5, "setting_up", "Setting up your course", busy=True)

    rs, an = d.get("resources_status"), d.get("analysis_status")
    if rs == "DONE" and an == "RUNNING":
        res = ("checking", d.get("analysis_progress"))
    elif rs == "DONE":
        res = ("done", None)
    elif rs == "FAILED":
        res = ("failed", d.get("resources_error"))
    else:
        res = ("finding", d.get("resources_progress"))
    out = s(6, "ready", "Your course is ready", "Start with this week's concepts.", action="learn")
    out["resources"] = {"state": res[0], "progress": res[1]}
    return out


def _stepper(stage: dict) -> list[dict]:
    cur = stage["step"]
    out = []
    for i, name in enumerate(STEPS, start=1):
        state = "done" if stage["ready"] or i < cur else "current" if i == cur else "todo"
        out.append({"n": i, "label": name, "state": state})
    return out


async def _titles(drafts: list[dict], uid: str) -> dict:
    up_ids = [ObjectId(d["source_ref"]) for d in drafts if d.get("source") == "UPLOAD" and d.get("source_ref")]
    goal_ids = [ObjectId(d["source_ref"]) for d in drafts if d.get("source") == "GOAL_DRAFT" and d.get("source_ref")]
    ups = {str(u["_id"]): u for u in await get_db().uploads.find({"_id": {"$in": up_ids}}, {"filename": 1}).to_list(200)} if up_ids else {}
    goals = {str(g["_id"]): g for g in await get_db().curriculum_drafts.find({"_id": {"$in": goal_ids}}, {"goal": 1}).to_list(200)} if goal_ids else {}
    out = {}
    for d in drafts:
        cur = d.get("curriculum") or {}
        ref = d.get("source_ref")
        fallback = (ups.get(ref) or {}).get("filename") or (goals.get(ref) or {}).get("goal", "")[:60] or "New course"
        out[str(d["_id"])] = cur.get("course") or fallback
    return out


def _brief(d: dict, title: str) -> dict:
    stage = stage_of(d)
    cur = d.get("curriculum") or {}
    return {"id": str(d["_id"]), "title": title, "version": cur.get("version"), "source": "goal" if d.get("source") == "GOAL_DRAFT" else "syllabus",
            "units": len(cur.get("units", [])), "created_at": d.get("created_at"), "stage": stage, "steps": _stepper(stage)}


async def _mine(user: dict, course_id: str) -> dict:
    try:
        oid = ObjectId(course_id)
    except Exception:
        raise HTTPException(404, "Course not found")
    d = await get_db().curriculum_drafts.find_one({"_id": oid, "user_id": str(user["_id"]), "source": KINDS})
    if not d:
        raise HTTPException(404, "Course not found")
    return await _heal(d)


@router.get("")
async def list_courses(user: dict = Depends(current_user)):
    docs = await get_db().curriculum_drafts.find({"user_id": str(user["_id"]), "source": KINDS}).sort("created_at", -1).to_list(100)
    docs = [await _heal(d) for d in docs]
    titles = await _titles(docs, str(user["_id"]))
    return [_brief(d, titles[str(d["_id"])]) for d in docs]


@router.get("/{course_id}")
async def get_course(course_id: str, user: dict = Depends(current_user)):
    d = await _mine(user, course_id)
    titles = await _titles([d], str(user["_id"]))
    return _brief(d, titles[str(d["_id"])])


@router.post("/{course_id}/retry", status_code=202)
async def retry(course_id: str, bg: BackgroundTasks, user: dict = Depends(current_user)):
    """Re-run the step that failed for this course."""
    d = await _mine(user, course_id)
    stage, uid, db = stage_of(d), str(user["_id"]), get_db()
    kind = stage["retry"]
    if not kind:
        raise HTTPException(409, "Nothing to retry for this course")
    if kind == "extract":
        await db.curriculum_drafts.update_one({"_id": d["_id"]}, {"$set": {"status": "EXTRACTING", "error": None}})
        if d["source"] == "UPLOAD":
            up = await db.uploads.find_one({"_id": ObjectId(d["source_ref"])})
            text = (up or {}).get("text")
            if not text:
                raise HTTPException(409, "The uploaded text is no longer available; please upload the file again")
            bg.add_task(curriculum_api._run, d["_id"], lambda: curriculum_service.from_syllabus(text))
        else:
            goal = await db.curriculum_drafts.find_one({"_id": ObjectId(d["source_ref"])})
            bg.add_task(curriculum_api._run, d["_id"], lambda: curriculum_service.from_goal(goal or {}))
    elif kind == "concepts":
        await db.curriculum_drafts.update_one({"_id": d["_id"]}, {"$set": {"graph_status": "GENERATING", "graph_error": None, "graph_progress": "Starting"}})
        bg.add_task(concepts_api._run, d["_id"], Curriculum.model_validate(d["curriculum"]))
    elif kind == "graph_save":
        await db.curriculum_drafts.update_one({"_id": d["_id"]}, {"$set": {"neo4j_status": "SAVING", "neo4j_error": None}})
        bg.add_task(graph_api._save_job, d["_id"], course_id, uid, Curriculum.model_validate(d["curriculum"]), ConceptGraph.model_validate(d["graph"]))
    elif kind == "plan_save":
        await db.curriculum_drafts.update_one({"_id": d["_id"]}, {"$set": {"plan_neo4j_status": "SAVING", "plan_neo4j_error": None}})
        bg.add_task(sequencing_api._save_job, d["_id"], course_id, uid, Plan.model_validate(d["plan"]), (d.get("curriculum") or {}).get("course", ""))
    return {"course_id": course_id, "retrying": kind}


@router.delete("/{course_id}", status_code=204)
async def delete_course(course_id: str, user: dict = Depends(current_user)):
    """Remove a course everywhere: draft, upload, knowledge graph, quiz history."""
    d = await _mine(user, course_id)
    uid, db = str(user["_id"]), get_db()
    try:
        await neo4j.delete_course(course_id, uid)
    except Exception as e:
        raise HTTPException(503, f"Could not remove the course graph right now: {e}")
    if d["source"] == "UPLOAD" and d.get("source_ref"):
        up = await db.uploads.find_one({"_id": ObjectId(d["source_ref"]), "user_id": uid})
        if up:
            Path(up.get("path", "")).unlink(missing_ok=True)
            await db.uploads.delete_one({"_id": up["_id"]})
    elif d["source"] == "GOAL_DRAFT" and d.get("source_ref"):
        await db.curriculum_drafts.delete_one({"_id": ObjectId(d["source_ref"]), "user_id": uid})
    await db.quiz_attempts.delete_many({"user_id": uid, "curriculum_id": course_id})
    await db.verification_feedback.delete_many({"user_id": uid, "draft_id": course_id})
    await db.curriculum_drafts.delete_one({"_id": d["_id"]})


@router.get("/{course_id}/overview")
async def overview(course_id: str, user: dict = Depends(current_user)):
    """How the course is laid out: study hours per week, how well resources cover each unit, outcome alignment."""
    d = await _mine(user, course_id)
    if stage_of(d)["step"] < 5:
        raise HTTPException(409, "The course is not set up yet")
    try:
        concepts = await neo4j.dashboard_concepts(course_id)
        outcomes = await neo4j.course_outcomes(course_id)
    except Exception as e:
        raise HTTPException(503, f"Neo4j unavailable: {e}")
    hours = ((d.get("plan") or {}).get("params") or {}).get("hours_per_week", 8)
    cur = d.get("curriculum") or {}
    return {"course": cur.get("course"), "hours_per_week": hours,
            "plan": ds.plan_load(concepts, hours), "coverage": ds.coverage_summary(concepts),
            "outcomes": ds.outcome_alignment(outcomes, concepts),
            "counts": {"units": len(cur.get("units", [])), "concepts": len(concepts),
                       "prerequisites": len([r for r in (d.get("graph") or {}).get("relationships", []) if r.get("type") == "PREREQUISITE_OF"])}}
