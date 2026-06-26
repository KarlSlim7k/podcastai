"""Clips & social-media content router.

Endpoints
---------
POST   /api/v1/projects/{id}/clips/detect        -> find viral moments
GET    /api/v1/projects/{id}/clips               -> list detected clips
GET    /api/v1/projects/{id}/clips/{clip_id}     -> single clip + generations
POST   /api/v1/projects/{id}/clips/{clip_id}/generate -> generate platform content
POST   /api/v1/projects/{id}/clips/{clip_id}/extract  -> cut media with ffmpeg
DELETE /api/v1/projects/{id}/clips/{clip_id}     -> delete a clip
"""
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_db, AsyncSessionLocal, db_retry
from app.models.schemas import (
    ClipDetectionRequest, ClipGenerationRequest, ClipOut, ClipListResponse,
    ClipTrimRequest, CaptionWord, ClipCaptionsOut, ClipCaptionsRequest,
    MessageResponse, ViralityScoreOut, ViralityBreakdownOut, ViralityScoreRequest,
    BrollSuggestionOut, BrollSuggestionListResponse,
)
from app.models.project import (
    Project, ProjectStatus, Clip, ClipGeneration, ClipStatus,
)
from app.services.clips_service import clips_service, _extract_excerpt
from app.services.vertical_editor_service import extract_words_for_clip
from app.services.project_service import project_service
from app.utils.security import validate_model_name
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/projects", tags=["clips"])


# ── Background tasks ────────────────────────────────────────────────────────

async def _detect_clips_bg(project_id: int, num: int, mn: int, mx: int, model: str):  # pragma: no cover
    async def _run():
        async with AsyncSessionLocal() as db:
            await clips_service.detect_clips(db, project_id, num, mn, mx, model)
            await db.commit()
    try:
        await db_retry(_run)
        logger.info("clips_detect_done", project_id=project_id, num=num)
    except Exception as e:
        logger.error("clips_detect_failed", project_id=project_id, error=str(e))


async def _generate_bg(project_id: int, clip_id: int, platforms: list[str], model: str):  # pragma: no cover
    async def _run():
        async with AsyncSessionLocal() as db:
            await clips_service.generate_for_platforms(db, project_id, clip_id, platforms, model)
            await db.commit()
    try:
        await db_retry(_run)
        logger.info("clip_generate_done", project_id=project_id, clip_id=clip_id,
                    platforms=platforms)
    except Exception as e:
        logger.error("clip_generate_failed", project_id=project_id, clip_id=clip_id,
                     error=str(e))


async def _extract_bg(project_id: int, clip_id: int, with_video: bool):  # pragma: no cover
    async def _run():
        async with AsyncSessionLocal() as db:
            await clips_service.extract_media(db, project_id, clip_id, with_video)
            await db.commit()
    try:
        await db_retry(_run)
        logger.info("clip_extract_done", project_id=project_id, clip_id=clip_id)
    except Exception as e:
        logger.error("clip_extract_failed", project_id=project_id, clip_id=clip_id,
                     error=str(e))


# ── Routes ──────────────────────────────────────────────────────────────────

@router.post("/{project_id}/clips/detect", response_model=MessageResponse)
async def detect_clips(
    project_id: int,
    request: ClipDetectionRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    project = await project_service.get(db, project_id)
    if not project.transcription or not project.transcription.segments:
        raise HTTPException(status_code=400, detail="No transcription with segments")

    model = validate_model_name(request.model)
    background_tasks.add_task(
        _detect_clips_bg, project_id, request.num_clips,
        request.min_duration, request.max_duration, model,
    )
    return MessageResponse(
        message="Clip detection started",
        detail=f"Looking for {request.num_clips} moments between {request.min_duration}s and {request.max_duration}s",
    )


@router.get("/{project_id}/clips", response_model=ClipListResponse)
async def list_clips(project_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Clip)
        .where(Clip.project_id == project_id)
        .options(selectinload(Clip.platforms))
        .order_by(Clip.virality_score.desc().nullslast(), Clip.start)
    )
    clips = list(result.scalars().all())
    return ClipListResponse(clips=clips)


@router.get("/{project_id}/clips/{clip_id}", response_model=ClipOut)
async def get_clip(project_id: int, clip_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Clip)
        .where(Clip.id == clip_id, Clip.project_id == project_id)
        .options(selectinload(Clip.platforms))
    )
    clip = result.scalar_one_or_none()
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    return clip


@router.post("/{project_id}/clips/{clip_id}/generate", response_model=MessageResponse)
async def generate_clip_content(
    project_id: int,
    clip_id: int,
    request: ClipGenerationRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Clip).where(Clip.id == clip_id, Clip.project_id == project_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Clip not found")

    if not request.platforms:
        raise HTTPException(status_code=400, detail="No platforms selected")

    model = validate_model_name(request.model)
    background_tasks.add_task(
        _generate_bg, project_id, clip_id, request.platforms, model,
    )
    return MessageResponse(
        message=f"Generating content for {len(request.platforms)} platform(s)",
        detail=f"Platforms: {', '.join(request.platforms)}",
    )


@router.post("/{project_id}/clips/{clip_id}/extract", response_model=MessageResponse)
async def extract_clip(
    project_id: int,
    clip_id: int,
    background_tasks: BackgroundTasks,
    with_video: bool = True,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Clip).where(Clip.id == clip_id, Clip.project_id == project_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Clip not found")

    # Make sure source media exists before queuing
    proj = await db.execute(select(Project).where(Project.id == project_id))
    project = proj.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    has_source = (
        (with_video and project.original_file and Path(project.original_file).exists())
        or (project.audio_file and Path(project.audio_file).exists())
    )
    if not has_source:
        raise HTTPException(status_code=400, detail="No source media available")

    background_tasks.add_task(_extract_bg, project_id, clip_id, with_video)
    return MessageResponse(
        message="Extracting clip media",
        detail=("video + audio" if with_video else "audio only"),
    )


@router.patch("/{project_id}/clips/{clip_id}", response_model=ClipOut)
async def trim_clip(
    project_id: int,
    clip_id: int,
    request: ClipTrimRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Manually adjust a clip's [start, end] boundaries (timeline trim).

    Re-extracts audio/video at the new boundaries in the background —
    clips_service.extract_media() clamps against the real media duration,
    so we don't need to duplicate that validation here.
    """
    result = await db.execute(
        select(Clip).where(Clip.id == clip_id, Clip.project_id == project_id)
        .options(selectinload(Clip.platforms))
    )
    clip = result.scalar_one_or_none()
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    if request.end <= request.start:
        raise HTTPException(status_code=400, detail="end must be greater than start")
    new_duration = request.end - request.start
    if new_duration < 3:
        raise HTTPException(status_code=400, detail="Clip must be at least 3 seconds long")
    if new_duration > 180:
        raise HTTPException(status_code=400, detail="Clip cannot be longer than 180 seconds")

    proj_result = await db.execute(
        select(Project).where(Project.id == project_id)
        .options(selectinload(Project.transcription))
    )
    project = proj_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    clip.start = round(request.start, 2)
    clip.end = round(request.end, 2)
    clip.duration = round(new_duration, 2)
    if project.transcription and project.transcription.segments:
        clip.transcript_excerpt = _extract_excerpt(
            project.transcription.segments, clip.start, clip.end
        )
    await db.commit()
    await db.refresh(clip, attribute_names=["platforms"])

    # Re-cut audio/video from the original source at the new boundaries.
    has_source = (
        (project.original_file and Path(project.original_file).exists())
        or (project.audio_file and Path(project.audio_file).exists())
    )
    if has_source:
        background_tasks.add_task(_extract_bg, project_id, clip_id, bool(clip.video_clip_path))

    return clip


async def _auto_caption_words(db: AsyncSession, project_id: int, clip: Clip) -> list[CaptionWord]:
    """Dynamically slice the parent transcription's words for this clip's
    [start, end] range — the same words the renderer would use by default."""
    proj_result = await db.execute(
        select(Project).where(Project.id == project_id)
        .options(selectinload(Project.transcription))
    )
    project = proj_result.scalar_one_or_none()
    if not project or not project.transcription or not project.transcription.segments:
        return []
    words = extract_words_for_clip(project.transcription.segments, float(clip.start), float(clip.end))
    return [CaptionWord(start=w.start, end=w.end, word=w.word) for w in words]


@router.get("/{project_id}/clips/{clip_id}/captions", response_model=ClipCaptionsOut)
async def get_clip_captions(project_id: int, clip_id: int, db: AsyncSession = Depends(get_db)):
    """Return the *effective* caption words: manual overrides if present,
    otherwise the words auto-sliced from the transcription."""
    result = await db.execute(
        select(Clip).where(Clip.id == clip_id, Clip.project_id == project_id)
    )
    clip = result.scalar_one_or_none()
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    if clip.caption_overrides:
        words = [CaptionWord(**w) for w in clip.caption_overrides]
        return ClipCaptionsOut(clip_id=clip_id, words=words, is_custom=True)

    words = await _auto_caption_words(db, project_id, clip)
    return ClipCaptionsOut(clip_id=clip_id, words=words, is_custom=False)


@router.put("/{project_id}/clips/{clip_id}/captions", response_model=ClipCaptionsOut)
async def save_clip_captions(
    project_id: int, clip_id: int, request: ClipCaptionsRequest,
    db: AsyncSession = Depends(get_db),
):
    """Save a manually-edited caption word list. Overrides what would
    otherwise be auto-sliced from the transcription at render time."""
    result = await db.execute(
        select(Clip).where(Clip.id == clip_id, Clip.project_id == project_id)
    )
    clip = result.scalar_one_or_none()
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    clip.caption_overrides = [w.model_dump() for w in request.words]
    await db.commit()
    return ClipCaptionsOut(clip_id=clip_id, words=request.words, is_custom=True)


@router.delete("/{project_id}/clips/{clip_id}/captions", response_model=ClipCaptionsOut)
async def reset_clip_captions(project_id: int, clip_id: int, db: AsyncSession = Depends(get_db)):
    """Discard manual caption edits and revert to auto-generated words."""
    result = await db.execute(
        select(Clip).where(Clip.id == clip_id, Clip.project_id == project_id)
    )
    clip = result.scalar_one_or_none()
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    clip.caption_overrides = None
    await db.commit()
    words = await _auto_caption_words(db, project_id, clip)
    return ClipCaptionsOut(clip_id=clip_id, words=words, is_custom=False)


@router.delete("/{project_id}/clips/{clip_id}", response_model=MessageResponse)
async def delete_clip(project_id: int, clip_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Clip).where(Clip.id == clip_id, Clip.project_id == project_id)
        .options(selectinload(Clip.platforms))
    )
    clip = result.scalar_one_or_none()
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    # Remove extracted files from disk
    for path_attr in ("audio_clip_path", "video_clip_path"):
        p = getattr(clip, path_attr)
        if p:
            try:
                Path(p).unlink(missing_ok=True)
            except OSError:
                pass

    await db.delete(clip)
    await db.flush()
    return MessageResponse(message="Clip deleted")


# ── File download endpoints ────────────────────────────────────────────────

@router.get("/{project_id}/clips/{clip_id}/download/audio")
async def download_clip_audio(project_id: int, clip_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Clip).where(Clip.id == clip_id, Clip.project_id == project_id)
    )
    clip = result.scalar_one_or_none()
    if not clip or not clip.audio_clip_path or not Path(clip.audio_clip_path).exists():
        raise HTTPException(status_code=404, detail="Audio clip not found or not yet extracted")
    return FileResponse(
        clip.audio_clip_path,
        media_type="audio/mpeg",
        filename=f"clip_{clip_id}.mp3",
    )


@router.get("/{project_id}/clips/{clip_id}/download/video")
async def download_clip_video(project_id: int, clip_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Clip).where(Clip.id == clip_id, Clip.project_id == project_id)
    )
    clip = result.scalar_one_or_none()
    if not clip or not clip.video_clip_path or not Path(clip.video_clip_path).exists():
        raise HTTPException(status_code=404, detail="Video clip not found or not yet extracted")
    return FileResponse(
        clip.video_clip_path,
        media_type="video/mp4",
        filename=f"clip_{clip_id}.mp4",
    )


# ── Virality score (Phase 8) ───────────────────────────────────────────────

import json as _json
from app.services.virality_service import compute_virality as _compute_virality


def _clip_to_score_out(clip: Clip) -> ViralityScoreOut:
    """Convert a Clip row into the API response shape.

    The ``virality_breakdown`` column is stored as a JSON string, so we
    parse it back into the ``ViralityBreakdownOut`` model here. If the
    column is empty (score not yet computed) we return ``computed=False``.
    """
    breakdown_out = None
    if clip.virality_breakdown:
        try:
            data = _json.loads(clip.virality_breakdown)
            breakdown_out = ViralityBreakdownOut(
                hook=int(data.get("hook", 1)),
                pacing=int(data.get("pacing", 1)),
                emotional_pull=int(data.get("emotional_pull", 1)),
                shareability=int(data.get("shareability", 1)),
            )
        except (ValueError, _json.JSONDecodeError):
            breakdown_out = None
    return ViralityScoreOut(
        clip_id=clip.id,
        score=clip.virality_score,
        reason=clip.virality_reason,
        breakdown=breakdown_out,
        category=clip.category,
        model_used=None,  # not persisted in the row
        computed=clip.virality_score is not None,
    )


async def _compute_virality_bg(
    project_id: int, clip_id: int, model: str | None = None
) -> None:  # pragma: no cover
    """Compute virality for one clip in the background.

    Updates the Clip row with score, breakdown JSON, reason, category.
    Failures are logged but do not raise — the UI shows a "pending" state.
    """
    async def _run():
        async with AsyncSessionLocal() as db:
            r = await db.execute(
                select(Clip).where(Clip.id == clip_id, Clip.project_id == project_id)
            )
            clip = r.scalar_one_or_none()
            if not clip:
                logger.warning("virality_clip_not_found", clip_id=clip_id)
                return
            result = await _compute_virality(
                title=clip.title,
                description=clip.description,
                transcript=clip.transcript_excerpt or "",
                duration=clip.duration,
                model=model,
            )
            clip.virality_score = result.score
            clip.virality_reason = result.reason
            # Store breakdown as JSON string (SQLite has no native JSON)
            breakdown_dict = result.breakdown.to_dict()
            breakdown_dict["reason"] = result.reason
            breakdown_dict["category"] = result.category
            clip.virality_breakdown = _json.dumps(breakdown_dict)
            # Only overwrite category if we don't already have one (the
            # initial detection step may have set a more specific category).
            if not clip.category:
                clip.category = result.category
            await db.commit()
            logger.info(
                "virality_computed_for_clip",
                clip_id=clip_id,
                score=result.score,
                category=result.category,
            )
    try:
        await db_retry(_run)
    except Exception as e:
        logger.error("virality_compute_failed", clip_id=clip_id, error=str(e))


@router.get(
    "/{project_id}/clips/{clip_id}/virality-score",
    response_model=ViralityScoreOut,
)
async def get_virality_score(
    project_id: int, clip_id: int, db: AsyncSession = Depends(get_db)
):
    """Return the current virality score for a clip (may be pending)."""
    r = await db.execute(
        select(Clip).where(Clip.id == clip_id, Clip.project_id == project_id)
    )
    clip = r.scalar_one_or_none()
    if not clip:
        raise HTTPException(status_code=404, detail=f"Clip {clip_id} not found")
    return _clip_to_score_out(clip)


@router.post(
    "/{project_id}/clips/{clip_id}/virality-score",
    response_model=MessageResponse,
)
async def recompute_virality_score(
    project_id: int,
    clip_id: int,
    request: ViralityScoreRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Trigger a recompute of the virality score in the background.

    Returns immediately with a message; the frontend polls the GET endpoint
    until ``computed=true`` (or shows the updated score on its next refetch).
    """
    r = await db.execute(
        select(Clip).where(Clip.id == clip_id, Clip.project_id == project_id)
    )
    clip = r.scalar_one_or_none()
    if not clip:
        raise HTTPException(status_code=404, detail=f"Clip {clip_id} not found")
    if not clip.transcript_excerpt:
        raise HTTPException(
            status_code=400,
            detail="Clip has no transcript excerpt yet. Wait for clip detection to finish.",
        )
    # Validate model if provided
    model = request.model
    if model:
        model = validate_model_name(model)
    background_tasks.add_task(_compute_virality_bg, project_id, clip_id, model)
    return MessageResponse(message="Virality score computation started")


# ── B-roll suggestions (Phase 11) ───────────────────────────────────────

@router.get(
    "/{project_id}/clips/{clip_id}/brolls",
    response_model=BrollSuggestionListResponse,
)
async def get_broll_suggestions(
    project_id: int, clip_id: int, db: AsyncSession = Depends(get_db)
):
    """Get AI-suggested b-roll (stock image/video) suggestions for a clip.

    The flow:
      1. We use Ollama to extract 2-4 visual keywords from the clip's
         transcript excerpt
      2. We search Pexels (or the mock) for each keyword
      3. We return up to 12 unique suggestions for the user to pick from

    The user is then expected to choose which ones to apply (Phase 11.5+).
    If Pexels is not configured (``settings.pexels_api_key`` is empty),
    we return a small set of curated mock b-rolls so the UI works
    without a Pexels account.
    """
    r = await db.execute(
        select(Clip).where(Clip.id == clip_id, Clip.project_id == project_id)
    )
    clip = r.scalar_one_or_none()
    if not clip:
        raise HTTPException(status_code=404, detail=f"Clip {clip_id} not found")
    if not clip.transcript_excerpt:
        # No transcript — fall back to a generic search so the UI is not empty
        transcript = f"{clip.title or ''} {clip.description or ''}"
    else:
        transcript = clip.transcript_excerpt
    # Run the search
    from app.services.broll_service import suggest_brolls, extract_keywords
    from app.config import settings
    keywords = await extract_keywords(transcript)
    suggestions = await suggest_brolls(transcript)
    # Mark source: pexels if we have a key, otherwise mock
    source = "pexels" if getattr(settings, "pexels_api_key", None) else "mock"
    return BrollSuggestionListResponse(
        clip_id=clip_id,
        keywords=keywords,
        suggestions=[BrollSuggestionOut(**s.to_dict()) for s in suggestions],
        source=source,
        total=len(suggestions),
    )
