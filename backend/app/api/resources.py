import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import current_user
from app.core.mongo import get_db
from app.repositories import neo4j_repository as repo
from app.repositories.mongo_repository import DraftRepository, now
from app.services import analysis_service, resource_matching

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/resources", tags=["resources"])
drafts = DraftRepository()
PARALLEL_CONCEPTS = 3


class SearchRequest(BaseModel):
    curriculum_id: str
    concept_ids: list[str] | None = None


async def _set(draft_id, **fields) -> None:
    """Status write that survives brief Atlas connection drops (long jobs must not die on a progress update)."""
    for attempt in range(5):
        try:
            await get_db().curriculum_drafts.update_one({"_id": draft_id}, {"$set": {**fields, "updated_at": now()}})
            return
        except Exception as e:
            if attempt == 4:
                raise
            log.warning("status write failed (attempt %d): %s", attempt + 1, e)
            await asyncio.sleep(2 * (attempt + 1))


async def _job(draft_id, curriculum_id: str, owner_id: str, course: str, concept_ids: list[str] | None) -> None:
    try:
        concepts = await repo.course_concepts(curriculum_id, owner_id, concept_ids)
        if not concepts:
            await _set(draft_id, resources_status="FAILED", resources_error="No stored concepts found in Neo4j")
            return
        done, failed, sem = 0, [], asyncio.Semaphore(PARALLEL_CONCEPTS)

        async def one(c):
            nonlocal done
            async with sem:
                try:
                    await resource_matching.match_concept(course, c)
                except Exception as e:  # one concept failing must not stop the rest
                    log.exception("resource matching failed for %s", c["name"])
                    failed.append({"concept": c["name"], "error": str(e)[:200]})
                done += 1
                await _set(draft_id, resources_progress=f"{done}/{len(concepts)} concepts")

        await asyncio.gather(*(one(c) for c in concepts))
        await _set(draft_id, resources_status="DONE", resources_error=None, resources_failed=failed,
                   resources_progress=f"{len(concepts) - len(failed)}/{len(concepts)} concepts")
    except Exception as e:
        log.exception("resource job failed")
        await _set(draft_id, resources_status="FAILED", resources_error=str(e)[:300])


@router.post("/search", status_code=202)
async def search(req: SearchRequest, bg: BackgroundTasks, user: dict = Depends(current_user)):
    """Discover resources for every concept of an approved, stored curriculum and rank them via Neo4j vector search."""
    d = await drafts.get(req.curriculum_id, str(user["_id"]))
    if not d:
        raise HTTPException(404, "Curriculum not found")
    if d.get("plan_status") != "APPROVED":
        raise HTTPException(409, "The semester plan must be approved (Verification #3) before resource discovery")
    if d.get("neo4j_status") != "SAVED":
        raise HTTPException(409, "The knowledge graph has not been stored in Neo4j yet")
    if d.get("resources_status") == "RUNNING":
        raise HTTPException(409, "Resource discovery already running")
    await _set(d["_id"], resources_status="RUNNING", resources_error=None, resources_progress="0")
    bg.add_task(_job, d["_id"], req.curriculum_id, str(user["_id"]), d["curriculum"]["course"], req.concept_ids)
    return {"curriculum_id": req.curriculum_id, "resources_status": "RUNNING"}


async def _analysis_job(draft_id, curriculum_id: str, owner_id: str, course: str, stage: str,
                        concept_ids: list[str] | None) -> None:
    """stage: analyze (points + coverage, then gap loop) | gaps (gap loop only) | coverage (recompute, offline)."""
    try:
        items = await repo.analysis_inputs(curriculum_id, owner_id, concept_ids)
        if stage == "gaps":
            items = [i for i in items if i["concept"].get("gap_status") == "GAP"]
        done, failed, sem = 0, [], asyncio.Semaphore(2)

        async def one(item):
            nonlocal done
            async with sem:
                try:
                    if stage == "coverage":
                        await analysis_service.recompute_coverage(item)
                    else:  # analyze, or gaps: re-analysis is cheap (required points are cached) and keeps rows complete
                        await analysis_service.analyze_concept(course, item, do_gaps=True)
                except Exception as e:
                    log.exception("analysis failed for %s", item["concept"]["name"])
                    failed.append({"concept": item["concept"]["name"], "error": str(e)[:200]})
                done += 1
                await _set(draft_id, analysis_progress=f"{done}/{len(items)} concepts")

        await asyncio.gather(*(one(i) for i in items))
        await _set(draft_id, analysis_status="DONE", analysis_error=None, analysis_failed=failed,
                   analysis_progress=f"{len(items) - len(failed)}/{len(items)} concepts")
    except Exception as e:
        log.exception("analysis job failed")
        await _set(draft_id, analysis_status="FAILED", analysis_error=str(e)[:300])


async def _start_analysis(req: SearchRequest, bg: BackgroundTasks, user: dict, stage: str):
    d = await drafts.get(req.curriculum_id, str(user["_id"]))
    if not d:
        raise HTTPException(404, "Curriculum not found")
    if d.get("resources_status") != "DONE":
        raise HTTPException(409, "Discover resources before analysing them")
    if d.get("analysis_status") == "RUNNING":
        raise HTTPException(409, "Analysis already running")
    await _set(d["_id"], analysis_status="RUNNING", analysis_error=None, analysis_progress="0", analysis_stage=stage)
    bg.add_task(_analysis_job, d["_id"], req.curriculum_id, str(user["_id"]), d["curriculum"]["course"],
                stage, req.concept_ids)
    return {"curriculum_id": req.curriculum_id, "analysis_status": "RUNNING", "stage": stage}


@router.post("/analyze", status_code=202)
async def analyze(req: SearchRequest, bg: BackgroundTasks, user: dict = Depends(current_user)):
    """Extract required subtopics, compute coverage/evidence per resource, then run the bounded gap loop."""
    return await _start_analysis(req, bg, user, "analyze")


@router.post("/coverage", status_code=202)
async def coverage(req: SearchRequest, bg: BackgroundTasks, user: dict = Depends(current_user)):
    """Recompute concept-level coverage from stored analysis (offline; no search)."""
    return await _start_analysis(req, bg, user, "coverage")


@router.post("/gaps/search", status_code=202)
async def gaps_search(req: SearchRequest, bg: BackgroundTasks, user: dict = Depends(current_user)):
    """Targeted search for concepts still below the coverage threshold (max 3 iterations each)."""
    return await _start_analysis(req, bg, user, "gaps")


@router.get("/{curriculum_id}")
async def get_resources(curriculum_id: str, user: dict = Depends(current_user)):
    d = await drafts.get(curriculum_id, str(user["_id"]))
    if not d:
        raise HTTPException(404, "Curriculum not found")
    items = []
    if d.get("resources_status") in ("RUNNING", "DONE"):  # noqa
        try:
            items = await repo.resources_for_course(curriculum_id, str(user["_id"]))
        except Exception as e:
            raise HTTPException(503, f"Neo4j unavailable: {e}")
    return {"curriculum_id": curriculum_id, "status": d.get("resources_status"), "progress": d.get("resources_progress"),
            "error": d.get("resources_error"), "failed": d.get("resources_failed", []), "concepts": items,
            "analysis": {"status": d.get("analysis_status"), "progress": d.get("analysis_progress"),
                         "error": d.get("analysis_error"), "failed": d.get("analysis_failed", []),
                         "stage": d.get("analysis_stage")}}
