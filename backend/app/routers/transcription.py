import asyncio
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.schemas import (
    TranscriptionRequest, TranscriptionOut, TranscriptionProgress,
    MessageResponse, SearchResponse, SearchHit,
)
from app.models.project import Project, ProjectStatus, Transcription, TranscriptionStatus, Clip
from app.services.project_service import project_service
from app.services.transcription_service import transcription_service
from app.utils.security import validate_model_name
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/projects", tags=["transcription"])


async def _run_transcription(  # pragma: no cover
    project_id: int,
    audio_path: str,
    model: str,
    language: str | None,
    beam_size: int,
):
    from app.database import AsyncSessionLocal, db_retry

    async def _set_status(status: ProjectStatus, error: str | None = None):
        async with AsyncSessionLocal() as db:
            await project_service.update_status(db, project_id, status, error)
            await db.commit()

    async def _do_transcribe():
        async with AsyncSessionLocal() as db2:
            await transcription_service.transcribe(
                db2,
                project_id,
                Path(audio_path),
                model_name=model,
                language=language,
                beam_size=beam_size,
            )
            await db2.commit()

    try:
        await db_retry(lambda: _set_status(ProjectStatus.TRANSCRIBING))
        await db_retry(_do_transcribe)
        await db_retry(lambda: _set_status(ProjectStatus.COMPLETED))

    except Exception as e:
        logger.error("transcription_background_failed", project_id=project_id, error=str(e))
        try:
            await db_retry(lambda: _set_status(ProjectStatus.ERROR, str(e)))
        except Exception as inner:
            logger.error("transcription_error_update_failed",
                         project_id=project_id, error=str(inner))


@router.post("/{project_id}/transcribe", response_model=MessageResponse)
async def start_transcription(
    project_id: int,
    request: TranscriptionRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    project = await project_service.get(db, project_id)

    if not project.audio_file or not Path(project.audio_file).exists():
        raise HTTPException(
            status_code=400,
            detail="No audio file available. Please upload a file first.",
        )

    if project.status == ProjectStatus.TRANSCRIBING:
        raise HTTPException(status_code=409, detail="Transcription already in progress")

    # CRITICAL: commit before adding the background task to avoid
    # "database is locked" errors in the background task's session.
    await db.commit()

    background_tasks.add_task(
        _run_transcription,
        project_id,
        project.audio_file,
        request.model,
        request.language,
        request.beam_size,
    )

    return MessageResponse(
        message="Transcription started",
        detail=f"Using model '{request.model}' with beam_size={request.beam_size}",
    )


@router.post("/{project_id}/transcription/reset", response_model=MessageResponse)
async def reset_transcription(project_id: int, db: AsyncSession = Depends(get_db)):
    """Reset a stuck transcription state.

    If a project is stuck in 'transcribing' (e.g. after a server crash),
    this endpoint resets it to 'error' so the user can re-transcribe.
    """
    project = await project_service.get(db, project_id)

    if project.status not in (ProjectStatus.TRANSCRIBING, ProjectStatus.ERROR):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot reset: project status is '{project.status}'",
        )

    # Clear in-memory progress
    transcription_service.update_progress(project_id, {
        "status": "idle", "progress": 0, "current_step": "",
    })

    await project_service.update_status(db, project_id, ProjectStatus.COMPLETED if project.audio_file else ProjectStatus.CREATED)
    await db.commit()

    return MessageResponse(message="Transcription state reset", detail="You can now re-transcribe")


@router.get("/{project_id}/transcription/progress", response_model=TranscriptionProgress)
async def get_transcription_progress(project_id: int, db: AsyncSession = Depends(get_db)):
    progress = transcription_service.get_progress(project_id)
    # If in-memory progress is idle but the project is actually transcribing
    # in the DB (e.g. after a server restart), return a stale-state indicator
    # so the frontend can show a reset option.
    if progress.get("status") == "idle":
        result = await db.execute(
            select(Project).where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if project and project.status == ProjectStatus.TRANSCRIBING:
            progress = {
                "status": "stale",
                "progress": 0,
                "current_step": "Transcription state may be stuck after a server restart. Click reset to re-transcribe.",
            }
    return TranscriptionProgress(**progress)


@router.get("/{project_id}/transcription", response_model=TranscriptionOut)
async def get_transcription(project_id: int, db: AsyncSession = Depends(get_db)):
    project = await project_service.get(db, project_id)
    if not project.transcription:
        raise HTTPException(status_code=404, detail="No transcription found for this project")
    return project.transcription


@router.delete("/{project_id}/transcription", response_model=MessageResponse)
async def delete_transcription(project_id: int, db: AsyncSession = Depends(get_db)):
    project = await project_service.get(db, project_id)
    if not project.transcription:
        raise HTTPException(status_code=404, detail="No transcription found")

    transcription = project.transcription
    for file_attr in ["txt_file", "json_file", "srt_file", "vtt_file"]:
        file_path = getattr(transcription, file_attr)
        if file_path:
            Path(file_path).unlink(missing_ok=True)

    await db.delete(transcription)
    await db.flush()

    return MessageResponse(message="Transcription deleted")


# ── Search ──────────────────────────────────────────────────────────────────

@router.get("/{project_id}/transcription/search", response_model=SearchResponse)
async def search_transcription(
    project_id: int,
    q: str = "",
    speaker: str | None = None,
    limit: int = 50,
    context_words: int = 8,
    db: AsyncSession = Depends(get_db),
):
    """Full-text search across the transcript segments.

    Each hit includes the [start, end] time range in the source media and
    optional surrounding context words. Set ``speaker=SPEAKER_01`` to
    restrict the search to one speaker.
    """
    if not q or not q.strip():
        return SearchResponse(query=q, total=0, hits=[])

    project = await project_service.get(db, project_id)
    if not project.transcription or not project.transcription.segments:
        return SearchResponse(query=q, total=0, hits=[])

    segments = project.transcription.segments
    if not isinstance(segments, list):
        return SearchResponse(query=q, total=0, hits=[])

    # Case-insensitive search; words split on whitespace
    needle = q.lower().strip()
    needle_words = needle.split()

    def _matches(text: str) -> bool:
        if not text:
            return False
        haystack = text.lower()
        if len(needle_words) == 1:
            return needle_words[0] in haystack.split() or needle in haystack
        # Multi-word: every word must appear in order (loose phrase match)
        return needle in haystack

    def _words(text: str) -> list[str]:
        return (text or "").split()

    hits: list[SearchHit] = []
    for i, seg in enumerate(segments):
        if speaker and seg.get("speaker") != speaker:
            continue
        if not _matches(seg.get("text", "")):
            continue
        # Surrounding context from adjacent segments
        ctx_before = ""
        ctx_after = ""
        if i > 0 and context_words:
            words = _words(segments[i - 1].get("text", ""))
            ctx_before = " ".join(words[-context_words:])
        if i < len(segments) - 1 and context_words:
            words = _words(segments[i + 1].get("text", ""))
            ctx_after = " ".join(words[:context_words])
        hits.append(SearchHit(
            segment_id=seg.get("id"),
            start=float(seg.get("start", 0)),
            end=float(seg.get("end", 0)),
            text=seg.get("text", "").strip(),
            speaker=seg.get("speaker"),
            context_before=ctx_before or None,
            context_after=ctx_after or None,
        ))
        if len(hits) >= limit:
            break

    return SearchResponse(query=q, total=len(hits), hits=hits)


@router.get("/{project_id}/speakers")
async def list_speakers(project_id: int, db: AsyncSession = Depends(get_db)):
    """List speakers detected in the project's transcript (if diarization ran)."""
    project = await project_service.get(db, project_id)
    if not project.transcription:
        raise HTTPException(status_code=404, detail="No transcription")
    return {
        "diarization_available": bool(project.transcription.speaker_stats),
        "speakers": project.transcription.speaker_stats or [],
    }
