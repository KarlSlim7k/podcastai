import aiofiles
import asyncio
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.schemas import ProjectOut, MessageResponse
from app.models.project import ProjectStatus
from app.services.project_service import project_service
from app.services.audio_extractor import audio_extractor
from app.utils.file_validator import validate_upload_file
from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/projects", tags=["upload"])


async def _process_audio_background(project_id: int, file_path: Path, is_audio: bool):  # pragma: no cover
    from app.database import AsyncSessionLocal, db_retry

    async def _set_status(status: ProjectStatus, error: str | None = None):
        async with AsyncSessionLocal() as db:
            await project_service.update_status(db, project_id, status, error)
            await db.commit()

    try:
        await db_retry(lambda: _set_status(ProjectStatus.EXTRACTING_AUDIO))

        duration = await audio_extractor.get_duration(file_path)

        # Always extract/convert to 16kHz mono WAV for Whisper.
        # For video files this strips the video track; for audio files
        # this re-encodes to the format Whisper expects.
        audio_path = settings.uploads_dir / str(project_id) / "audio.wav"
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        await audio_extractor.extract_audio(file_path, audio_path)

        async def _save_audio_info():
            async with AsyncSessionLocal() as db2:
                project = await project_service.get_simple(db2, project_id)
                project.audio_file = str(audio_path)
                project.audio_duration = duration
                project.status = ProjectStatus.COMPLETED
                await db2.commit()

        await db_retry(_save_audio_info)

        logger.info("audio_processed", project_id=project_id, duration=duration)

    except Exception as e:
        logger.error("audio_processing_failed", project_id=project_id, error=str(e))
        try:
            await db_retry(lambda: _set_status(ProjectStatus.ERROR, str(e)))
        except Exception as inner:
            logger.error("audio_processing_error_update_failed",
                         project_id=project_id, error=str(inner))


@router.post("/{project_id}/upload", response_model=ProjectOut)
async def upload_file(
    project_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    resp_db: AsyncSession = Depends(get_db, use_cache=False),
):
    project = await project_service.get(db, project_id)

    safe_name, file_size = await validate_upload_file(file)

    upload_dir = settings.uploads_dir / str(project_id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = upload_dir / f"{timestamp}_{safe_name}"

    async with aiofiles.open(file_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            await f.write(chunk)

    project.original_file = str(file_path)
    project.original_filename = file.filename
    project.original_file_size = file_size
    project.original_mime_type = file.content_type
    project.status = ProjectStatus.UPLOADING

    await db.flush()
    # CRITICAL: commit before adding the background task.
    # FastAPI runs BackgroundTasks BEFORE dependency cleanup (get_db commit).
    # If we don't commit here, the background task's new session will hit
    # "database is locked" because our transaction is still open.
    await db.commit()

    is_audio = audio_extractor.is_audio_file(safe_name)
    background_tasks.add_task(_process_audio_background, project_id, file_path, is_audio)

    # Use a FRESH session for the response read (a second `Depends(get_db)`
    # instance, not the same `db`). The request's `db` session must NOT
    # start a new transaction (e.g. via selectinload) before the background
    # task fires — otherwise the background task's write hits "database is
    # locked" because our read transaction is still open. `use_cache=False`
    # forces FastAPI to instantiate a distinct session (still honoring the
    # test DB override) instead of reusing `db`.
    return await project_service.get(resp_db, project_id)
