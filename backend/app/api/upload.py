import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile

from app.api.deps import current_user
from app.core.config import get_settings
from app.api import curriculum as curriculum_api
from app.repositories.mongo_repository import DraftRepository, GoalRepository, UploadRepository
from app.schemas.upload import GoalOut, GoalRequest, UploadDetail, UploadOut
from app.services import curriculum_service
from app.services import document_service as docs

router = APIRouter(prefix="/api", tags=["input"])
uploads = UploadRepository()
goals = GoalRepository()
drafts = DraftRepository()
log = logging.getLogger(__name__)
UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"


def _out(d: dict) -> dict:
    return {**d, "id": str(d["_id"]), "text_chars": len(d.get("text") or "")}


async def _process(upload_id, path: Path, user_id: str) -> None:
    try:
        text = await asyncio.to_thread(docs.extract_text, path)
    except docs.DocumentError as e:
        await uploads.finish(upload_id, None, str(e))
        return
    except Exception as e:  # never leave an upload stuck in PROCESSING
        await uploads.finish(upload_id, None, f"Unexpected error: {e}")
        return
    await uploads.finish(upload_id, text, None)
    try:  # the syllabus is readable: continue straight on to reading its curriculum (no extra click)
        draft = await drafts.create(user_id, "UPLOAD", str(upload_id))
        await uploads.set_curriculum(upload_id, str(draft["_id"]))
        await curriculum_api._run(draft["_id"], lambda: curriculum_service.from_syllabus(text))
    except Exception:
        log.exception("could not start curriculum extraction for upload %s", upload_id)


@router.post("/upload", response_model=UploadOut, status_code=202)
async def upload(bg: BackgroundTasks, file: UploadFile = File(...), user: dict = Depends(current_user)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in docs.ALLOWED:
        raise HTTPException(415, f"Unsupported file type. Allowed: {', '.join(sorted(docs.ALLOWED))}")
    limit = get_settings().max_upload_mb * 1024 * 1024
    dest_dir = UPLOAD_DIR / str(user["_id"])
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{uuid.uuid4().hex}{ext}"
    size, head = 0, b""
    try:
        with dest.open("wb") as f:
            while chunk := await file.read(1024 * 1024):
                if not head:
                    head = chunk[:16]
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, f"File exceeds {get_settings().max_upload_mb} MB limit")
                f.write(chunk)
        if size == 0:
            raise HTTPException(400, "File is empty")
        if not docs.validate_signature(ext, head):
            raise HTTPException(400, f"File content does not match its {ext} extension")
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    doc = await uploads.create(str(user["_id"]), Path(file.filename).name, docs.ALLOWED[ext], size, str(dest))
    bg.add_task(_process, doc["_id"], dest, str(user["_id"]))
    return _out(doc)


@router.get("/upload", response_model=list[UploadOut])
async def list_uploads(user: dict = Depends(current_user)):
    return [_out(d) for d in await uploads.list(str(user["_id"]))]


@router.get("/upload/{upload_id}", response_model=UploadDetail)
async def get_upload(upload_id: str, user: dict = Depends(current_user)):
    doc = await uploads.get(upload_id, str(user["_id"]))
    if not doc:
        raise HTTPException(404, "Upload not found")
    return _out(doc)


@router.post("/goal", response_model=GoalOut, status_code=201)
async def submit_goal(req: GoalRequest, bg: BackgroundTasks, user: dict = Depends(current_user)):
    """Save the goal and start drafting a curriculum for it straight away."""
    uid = str(user["_id"])
    doc = await goals.create(uid, req.model_dump())
    draft = await drafts.create(uid, "GOAL_DRAFT", str(doc["_id"]))
    bg.add_task(curriculum_api._run, draft["_id"], lambda: curriculum_service.from_goal(doc))
    return {**doc, "id": str(doc["_id"]), "curriculum_id": str(draft["_id"])}
