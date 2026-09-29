import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from app.api.deps import current_user
from app.repositories import neo4j_repository as graph
from app.repositories.mongo_repository import CatalogRepository, QuizRepository
from app.schemas.quiz import GenerateRequest, Question, QuizPublic, SubmitRequest
from app.services import adaptive_service, mastery_service, quiz_service
from app.services.llm_service import LLMError

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/quiz", tags=["quiz"])
quizzes, catalog = QuizRepository(), CatalogRepository()

SECONDS_PER_QUIZ = 75  # rough figure for a local CPU model, only used for the progress message

# Generation runs inside this server process, so what is being generated (and what failed) can be tracked in memory.
_INFLIGHT: set[str] = set()
_FAILED: dict[str, str] = {}


def quiz_id_for(concept_id: str) -> str:
    return f"quiz:{concept_id}"


async def _neo(coro):
    try:
        return await coro
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(503, f"Neo4j unavailable: {e}")


async def _require_access(user: dict, course_id: str) -> dict:
    """You can take quizzes for your own finished courses."""
    d = await catalog.get(course_id)
    if not d or d["user_id"] != str(user["_id"]):
        raise HTTPException(404, "Course not found")
    return d


async def _generate_job(course_id: str, course_name: str, concept_ids: list[str], n: int) -> None:
    try:
        contexts = await graph.concept_context(course_id, concept_ids)
        for c in contexts:
            try:
                qs = await quiz_service.generate_questions(course_name, c, n)
                await graph.save_quiz(quiz_id_for(c["id"]), c["id"], course_id,
                                      [{**q.model_dump(mode="json"), "order": i} for i, q in enumerate(qs)])
                _FAILED.pop(c["id"], None)
            except LLMError as e:
                _FAILED[c["id"]] = f"The AI could not write a good quiz for this concept ({str(e)[:120]}). Try again."
            except Exception as e:  # one failed concept must not lose the others
                log.exception("quiz generation failed for %s", c["name"])
                _FAILED[c["id"]] = f"Something went wrong while writing this quiz ({str(e)[:120]}). Try again."
            finally:
                _INFLIGHT.discard(c["id"])
    except Exception as e:
        log.exception("quiz job failed")
        for cid in concept_ids:
            _FAILED.setdefault(cid, f"Could not start quiz generation ({str(e)[:120]}).")
    finally:
        _INFLIGHT.difference_update(concept_ids)


@router.post("/generate", status_code=202)
async def generate(req: GenerateRequest, bg: BackgroundTasks, user: dict = Depends(current_user)):
    """Start writing quizzes in the background for concepts that have none yet. Safe to call repeatedly."""
    d = await _require_access(user, req.curriculum_id)
    existing = {} if req.regenerate else await _neo(graph.existing_quizzes(req.concept_ids))
    todo = [c for c in dict.fromkeys(req.concept_ids) if c not in existing and c not in _INFLIGHT]
    for c in todo:
        _INFLIGHT.add(c)
        _FAILED.pop(c, None)
    if todo:
        bg.add_task(_generate_job, req.curriculum_id, d["curriculum"]["course"], todo, req.num_questions)
    return {"queued": todo, "ready": [c for c in req.concept_ids if c in existing],
            "generating": [c for c in req.concept_ids if c in _INFLIGHT]}


@router.get("/status")
async def status(curriculum_id: str, concept_ids: list[str] = Query(...), user: dict = Depends(current_user)):
    """Per concept: READY (with quiz_id), GENERATING, FAILED (with a message) or NONE."""
    await _require_access(user, curriculum_id)
    existing = await _neo(graph.existing_quizzes(concept_ids))
    out, generating = {}, 0
    for c in concept_ids:
        if c in _INFLIGHT:
            out[c] = {"status": "GENERATING"}
            generating += 1
        elif c in existing:
            out[c] = {"status": "READY", "quiz_id": existing[c]}
        elif c in _FAILED:
            out[c] = {"status": "FAILED", "error": _FAILED[c]}
        else:
            out[c] = {"status": "NONE"}
    return {"concepts": out, "eta_seconds": generating * SECONDS_PER_QUIZ}


@router.get("/history")
async def history(curriculum_id: str | None = None, user: dict = Depends(current_user)):
    rows = await quizzes.history(str(user["_id"]), curriculum_id)
    return [{"id": str(r["_id"]), "quiz_id": r["quiz_id"], "concept_id": r["concept_id"], "score": r["score"],
             "total": r["total"], "percent": r["percent"], "attempted_at": r["attempted_at"]} for r in rows]


@router.post("/submit")
async def submit(req: SubmitRequest, user: dict = Depends(current_user)):
    quiz = await _neo(graph.get_quiz(req.quiz_id))
    if not quiz or not quiz["questions"]:
        raise HTTPException(404, "Quiz not found")
    await _require_access(user, quiz["course_id"])
    questions = [Question.model_validate(q | {"question": q["text"]}) for q in quiz["questions"]]
    known = {q.id for q in questions}
    if not set(req.answers) <= known:
        raise HTTPException(422, "Answers reference unknown questions")
    graded = quiz_service.grade(questions, req.answers)
    uid = str(user["_id"])
    # mastery: difficulty-weighted quiz score blended into the learner's running mastery for this concept
    previous = await _neo(graph.get_mastery(uid, quiz["concept_id"]))
    mastery = mastery_service.apply_attempt(previous, [r.points for r in graded["results"]],
                                            [q.difficulty for q in questions])
    await _neo(graph.save_mastery(uid, quiz["concept_id"], mastery))
    attempt_id = await quizzes.add_attempt({
        "user_id": uid, "quiz_id": req.quiz_id, "concept_id": quiz["concept_id"], "curriculum_id": quiz["course_id"],
        "score": graded["score"], "total": graded["total"], "percent": graded["percent"],
        "mastery_after": mastery["mastery_score"],
        "results": [r.model_dump() for r in graded["results"]]})
    try:
        await adaptive_service.detect_and_store_gaps(uid, quiz["course_id"])  # quiz -> mastery -> knowledge gaps
    except Exception as e:  # gaps are derived data and are recomputed on demand
        log.warning("could not update knowledge gaps: %s", e)
    try:
        await graph.record_attempt(uid, req.quiz_id, graded["score"], graded["total"])
    except Exception as e:  # the MongoDB history is the record of truth; the graph link can be rebuilt
        log.warning("could not record ATTEMPTED link: %s", e)
    return {"attempt_id": attempt_id, "quiz_id": req.quiz_id, "concept": quiz["concept"], **graded,
            "mastery": {**mastery, "previous": previous and previous["mastery_score"]}}


@router.get("/{quiz_id:path}")
async def get_quiz(quiz_id: str, user: dict = Depends(current_user)) -> QuizPublic:
    quiz = await _neo(graph.get_quiz(quiz_id))
    if not quiz or not quiz["questions"]:
        raise HTTPException(404, "Quiz not found")
    await _require_access(user, quiz["course_id"])
    qs = [Question.model_validate(q | {"question": q["text"]}) for q in quiz["questions"]]
    return QuizPublic(quiz_id=quiz["quiz_id"], concept_id=quiz["concept_id"], concept=quiz["concept"],
                      questions=[quiz_service.public(q) for q in qs])
