"""Vertical video render router.

Endpoints
---------
GET    /api/v1/vertical/styles                      -> list available presets
POST   /api/v1/projects/{id}/clips/{clip_id}/vertical  -> start a render
POST   /api/v1/projects/{id}/clips/{clip_id}/vertical/draft -> render a 480p draft inline (Phase 15)
GET    /api/v1/projects/{id}/vertical              -> list all renders for a project
GET    /api/v1/projects/{id}/clips/{clip_id}/vertical -> list renders for one clip
GET    /api/v1/projects/{id}/vertical/{render_id}   -> get a single render
GET    /api/v1/projects/{id}/vertical/{render_id}/download -> download the MP4
DELETE /api/v1/projects/{id}/vertical/{render_id}   -> delete a render
GET    /api/v1/vertical/presets                    -> list all saved presets
GET    /api/v1/vertical/presets/{preset_id}        -> get a single preset
POST   /api/v1/vertical/presets                    -> create or update a preset
DELETE /api/v1/vertical/presets/{preset_id}        -> delete a preset
POST   /api/v1/vertical/watermark/upload          -> upload a watermark PNG
"""
import json
import secrets
import shutil
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import AsyncSessionLocal, db_retry, get_db
from app.models.schemas import (
    VerticalRenderRequest, VerticalRenderOut, VerticalRenderListResponse,
    VerticalStylesResponse, VerticalStyleInfo, MessageResponse,
    VerticalPresetRequest, VerticalPresetOut, VerticalPresetListResponse,
    WatermarkUploadResponse,
    VerticalBatchRenderRequest, VerticalBatchRenderResponse, VerticalBatchRenderError,
)
from app.models.project import (
    Project, Clip, VerticalRender, VerticalRenderStatus, VerticalPreset,
)
from app.services.vertical_editor_service import (
    render_vertical, RenderOptions, extract_words_for_clip, WordTimestamp, BrollPlacement,
    VideoTransform,
)
from app.services.project_service import project_service
from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["vertical"])


# ── Preset metadata (for the UI) ──────────────────────────────────────────

_LAYOUT_PRESETS = [
    VerticalStyleInfo(
        id="split", label="Split (video + fondo)",
        description="Video ocupa la parte superior, fondo animado debajo",
    ),
    VerticalStyleInfo(
        id="centered", label="Centrado",
        description="Video centrado con borde de fondo animado",
    ),
    VerticalStyleInfo(
        id="fill", label="Lleno (sin fondo)",
        description="Video llena todo el frame 9:16",
    ),
    # Phase 10 — auto-reframe with active speaker detection
    VerticalStyleInfo(
        id="auto", label="Auto-reframe (IA)",
        description="Reencuadra automáticamente siguiendo al hablante con detección facial",
    ),
]

_BG_PRESETS = [
    VerticalStyleInfo(id="blur", label="Blur (video borroso)",
                      description="Fondo = tu mismo video difuminado",
                      preview_color="#1a1a2e"),
    VerticalStyleInfo(id="solid", label="Color sólido",
                      description="Fondo de un color plano",
                      preview_color="#1a1a2e"),
    VerticalStyleInfo(id="gradient", label="Gradiente",
                      description="Gradiente vertical de dos colores",
                      preview_color="#1a1a2e"),
    VerticalStyleInfo(id="zoom", label="Zoom Ken Burns",
                      description="Fondo con zoom lento tipo cinematográfico",
                      preview_color="#1a1a2e"),
]

_SUB_PRESETS = [
    VerticalStyleInfo(id="standard", label="Estándar",
                      description="Una línea por cada ~5 palabras"),
    VerticalStyleInfo(id="karaoke", label="Karaoke",
                      description="Palabra por palabra destacada (estilo TikTok)",
                      preview_color="#FFD700"),
    VerticalStyleInfo(id="neon", label="Neón",
                      description="Texto con glow / resplandor",
                      preview_color="#FF00FF"),
    # Phase 9 — OpusClips-style animated word-by-word styles
    VerticalStyleInfo(id="mrbeast", label="MrBeast",
                      description="Texto amarillo gigante, palabra activa en rojo con zoom 130%",
                      preview_color="#FFFF00"),
    VerticalStyleInfo(id="hormozi", label="Hormozi",
                      description="Texto blanco con outline grueso, palabra activa con zoom 115%",
                      preview_color="#FFFFFF"),
    VerticalStyleInfo(id="tiktok_classic", label="TikTok Classic",
                      description="CapCut-style: palabra activa en amarillo, sin zoom",
                      preview_color="#FFFF00"),
]


# ── Background task ───────────────────────────────────────────────────────

async def _do_render_vertical(  # pragma: no cover
    project_id: int,
    clip_id: int,
    render_id: int,
    opts_dict: dict[str, Any],
):
    """Run the render in a background task. Persists results in the DB.

    Mirrors the pattern used by other routers (clips, transcription) so
    the lifecycle (status updates, error capture, cleanup) is consistent.
    """
    import json as _json
    from app.config import settings

    async def _run():
        async with AsyncSessionLocal() as db:
            # Load the render row + the clip + the transcription
            result = await db.execute(
                select(VerticalRender).where(VerticalRender.id == render_id)
            )
            vr = result.scalar_one_or_none()
            if not vr:
                logger.error("render_row_missing", render_id=render_id)
                return
            result = await db.execute(
                select(Clip).where(Clip.id == clip_id, Clip.project_id == project_id)
            )
            clip = result.scalar_one_or_none()
            if not clip:
                vr.status = VerticalRenderStatus.ERROR
                vr.error_message = f"Clip {clip_id} not found"
                await db.commit()
                return
            if not clip.audio_clip_path or not Path(clip.audio_clip_path).exists():
                vr.status = VerticalRenderStatus.ERROR
                vr.error_message = "Clip has no extracted audio/video. Extract it first."
                await db.commit()
                return

            # Mark processing
            vr.status = VerticalRenderStatus.PROCESSING
            await db.commit()

            # Load word timestamps from the transcription
            trans_result = await db.execute(
                select(Project).where(Project.id == project_id)
                .options(selectinload(Project.transcription))
            )
            proj = trans_result.scalar_one()
            if not proj.transcription or not proj.transcription.segments:
                vr.status = VerticalRenderStatus.ERROR
                vr.error_message = "Project has no transcription with segments"
                await db.commit()
                return
            segments = proj.transcription.segments
            if clip.caption_overrides:
                words = [
                    WordTimestamp(start=w["start"], end=w["end"], word=w["word"])
                    for w in clip.caption_overrides
                ]
            else:
                words = extract_words_for_clip(segments, float(clip.start), float(clip.end))

            # Build RenderOptions from the persisted fields
            opts = RenderOptions(
                layout=vr.layout,
                bg_style=vr.bg_style,
                bg_color=vr.bg_color or "#1a1a2e",
                bg_color2=vr.bg_color2 or "#16213e",
                sub_style=vr.sub_style,
                sub_color=vr.sub_color or "#FFFFFF",
                sub_highlight=vr.sub_highlight or "#FFD700",
                sub_outline=vr.sub_outline or "#000000",
                sub_size=vr.sub_size or 64,
                sub_position=vr.sub_position or 200,
                add_title=bool(vr.add_title),
                title_text=vr.title_text or clip.title or "",
                title_color=vr.title_color or "#FFFFFF",
                title_size=vr.title_size or 72,
                title_position=vr.title_position or "top",
                # Watermark (Phase 6)
                watermark_path=vr.watermark_path,
                watermark_position=vr.watermark_position or "bottom_right",
                watermark_opacity=vr.watermark_opacity if vr.watermark_opacity is not None else 0.8,
                # B-roll placements (Phase 3)
                broll_placements=[
                    BrollPlacement(url=bp["url"], start=bp["start"], end=bp["end"],
                                    opacity=bp.get("opacity", 1.0))
                    for bp in (vr.broll_placements or [])
                ],
                video_transform=(
                    VideoTransform(**vr.video_transform)
                    if getattr(vr, "video_transform", None) else None
                ),
            )

            # Build output path
            out_dir = settings.data_dir / "clips" / str(project_id) / "vertical"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"render_{render_id}.mp4"

            # Render!
            result_data = await render_vertical(
                source_video=Path(clip.video_clip_path or clip.audio_clip_path),
                source_audio=Path(clip.audio_clip_path),
                output_path=out_path,
                words=words,
                options=opts,
                duration=float(clip.end) - float(clip.start),
            )

            # Persist
            vr.status = VerticalRenderStatus.COMPLETED
            vr.output_path = result_data.output_path
            vr.file_size = result_data.file_size
            vr.width = result_data.width
            vr.height = result_data.height
            vr.duration = result_data.duration
            vr.processing_time = result_data.processing_time
            await db.commit()
            logger.info("vertical_render_done",
                        render_id=render_id, project_id=project_id,
                        clip_id=clip_id, size_mb=round(result_data.file_size/1024/1024, 2))

    try:
        await db_retry(_run)
    except Exception as e:
        logger.error("vertical_render_failed",
                     render_id=render_id, project_id=project_id, error=str(e))
        # Persist the error
        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(VerticalRender).where(VerticalRender.id == render_id)
                )
                vr = result.scalar_one_or_none()
                if vr:
                    vr.status = VerticalRenderStatus.ERROR
                    vr.error_message = str(e)[:1000]
                    await db.commit()
        except Exception as inner:
            logger.error("vertical_render_error_update_failed",
                         render_id=render_id, error=str(inner))


# ── Routes ─────────────────────────────────────────────────────────────────

@router.get("/vertical/styles", response_model=VerticalStylesResponse)
async def get_vertical_styles():
    """Return the available layout / background / subtitle presets."""
    return VerticalStylesResponse(
        layouts=_LAYOUT_PRESETS,
        backgrounds=_BG_PRESETS,
        subtitle_styles=_SUB_PRESETS,
    )


async def _validate_clip_for_render(db: AsyncSession, project_id: int, clip_id: int) -> Clip:
    """Fetch a clip and check it's ready to render. Raises HTTPException (404/400)."""
    result = await db.execute(
        select(Clip).where(Clip.id == clip_id, Clip.project_id == project_id)
    )
    clip = result.scalar_one_or_none()
    if not clip:
        raise HTTPException(status_code=404, detail=f"Clip {clip_id} not found in project {project_id}")
    if not clip.audio_clip_path or not Path(clip.audio_clip_path).exists():
        raise HTTPException(
            status_code=400,
            detail="Clip has no extracted audio/video. Extract it first via the 'Audio + Video' button.",
        )
    return clip


async def _create_render_row_and_task(
    db: AsyncSession,
    background_tasks: BackgroundTasks,
    project_id: int,
    clip: Clip,
    request: VerticalRenderRequest,
) -> VerticalRender:
    """Persist a pending VerticalRender row and queue its background render.

    Shared by the single-clip and batch endpoints so both stay in sync.
    """
    # Resolve watermark path to absolute (so background tasks can find it
    # regardless of cwd).
    wm_path = request.watermark_path
    if wm_path and not Path(wm_path).is_absolute():
        # Try to resolve relative to the data dir (where uploads live)
        candidate = settings.data_dir / wm_path
        if candidate.exists():
            wm_path = str(candidate.resolve())
        # Also try the data dir + "watermarks/<basename>"
        else:
            candidate = settings.data_dir / "watermarks" / Path(wm_path).name
            if candidate.exists():
                wm_path = str(candidate.resolve())

    # Persist the render row (status=pending)
    title_text = request.title_text or clip.title
    vr = VerticalRender(
        clip_id=clip.id,
        project_id=project_id,
        layout=request.layout,
        bg_style=request.bg_style,
        bg_color=request.bg_color,
        bg_color2=request.bg_color2,
        sub_style=request.sub_style,
        sub_color=request.sub_color,
        sub_highlight=request.sub_highlight,
        sub_outline=request.sub_outline,
        sub_size=request.sub_size,
        sub_position=request.sub_position,
        add_title=1 if request.add_title else 0,
        title_text=title_text,
        title_color=request.title_color,
        title_size=request.title_size,
        title_position=request.title_position,
        # Watermark (Phase 6)
        watermark_path=wm_path,
        watermark_position=request.watermark_position,
        watermark_opacity=request.watermark_opacity,
        # B-roll placements (Phase 3)
        broll_placements=(
            [bp.model_dump() for bp in request.broll_placements]
            if request.broll_placements else None
        ),
        video_transform=(
            request.video_transform.model_dump() if request.video_transform else None
        ),
        status=VerticalRenderStatus.PENDING,
    )
    db.add(vr)
    await db.commit()
    await db.refresh(vr)

    # Kick off the background task
    opts_dict = request.model_dump()
    background_tasks.add_task(_do_render_vertical, project_id, clip.id, vr.id, opts_dict)
    return vr


@router.post("/projects/{project_id}/clips/{clip_id}/vertical",
             response_model=MessageResponse)
async def create_vertical_render(
    project_id: int,
    clip_id: int,
    request: VerticalRenderRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Start a vertical render of a clip. Returns immediately with the
    render id; the actual encoding happens in a background task.
    """
    clip = await _validate_clip_for_render(db, project_id, clip_id)
    vr = await _create_render_row_and_task(db, background_tasks, project_id, clip, request)

    return MessageResponse(
        message="Vertical render started",
        detail=f"Render id={vr.id} · layout={request.layout} · bg={request.bg_style} · sub={request.sub_style}",
    )


@router.post("/projects/{project_id}/vertical/batch",
             response_model=VerticalBatchRenderResponse)
async def create_batch_vertical_render(
    project_id: int,
    request: VerticalBatchRenderRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Start vertical renders for several clips at once, all using the same
    configuration. Each clip is queued as its own background task (see
    ``_get_render_semaphore`` for how concurrent ffmpeg encodes are capped).

    Clips that fail validation (not found / no extracted audio) are skipped
    and reported in ``errors`` — they don't fail the whole batch.
    """
    render_ids: list[int] = []
    errors: list[VerticalBatchRenderError] = []
    for clip_id in request.clip_ids:
        try:
            clip = await _validate_clip_for_render(db, project_id, clip_id)
        except HTTPException as e:
            errors.append(VerticalBatchRenderError(clip_id=clip_id, detail=str(e.detail)))
            continue
        vr = await _create_render_row_and_task(db, background_tasks, project_id, clip, request.request)
        render_ids.append(vr.id)

    return VerticalBatchRenderResponse(render_ids=render_ids, errors=errors)


@router.post("/projects/{project_id}/clips/{clip_id}/vertical/draft")
async def create_vertical_draft_preview(
    project_id: int,
    clip_id: int,
    request: VerticalRenderRequest,
    db: AsyncSession = Depends(get_db),
):
    """Render a low-resolution draft synchronously and return the MP4 inline.

    Phase 15: this is the endpoint the editor's live-preview uses. It:
      - Forces quality='draft' (the request body's quality field is ignored).
      - Does NOT persist a VerticalRender row — drafts are throwaway.
      - Does NOT include B-rolls, watermark, or burned subtitles
        (set by the draft mode in vertical_editor_service).
      - Returns the MP4 bytes directly with Content-Type: video/mp4,
        so the frontend can just `fetch(url)` and assign the blob to a
        <video> element. No polling, no DB lookups.

    On a Windows + NVIDIA machine a 30s clip takes ~6s for the draft
    vs ~20s for the full render.
    """
    # Validate the project + clip exist (404 for nice error UX).
    result = await db.execute(
        select(Clip).where(Clip.id == clip_id, Clip.project_id == project_id)
    )
    clip = result.scalar_one_or_none()
    if not clip:
        raise HTTPException(status_code=404, detail=f"Clip {clip_id} not found in project {project_id}")
    if not clip.audio_clip_path or not Path(clip.audio_clip_path).exists():
        raise HTTPException(
            status_code=400,
            detail="Clip has no extracted audio/video. Extract it first via the 'Audio + Video' button.",
        )

    # Pull the words for this clip from the project transcription.
    proj_result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.transcription))
    )
    proj = proj_result.scalar_one_or_none()
    if not proj or not proj.transcription or not proj.transcription.segments:
        raise HTTPException(status_code=400, detail="Project has no transcription with segments")
    words = extract_words_for_clip(
        proj.transcription.segments, float(clip.start), float(clip.end)
    )

    # Build RenderOptions from the request, forcing draft mode. We don't
    # persist anything — the draft is throwaway.
    opts = RenderOptions(
        layout=request.layout,
        bg_style=request.bg_style,
        bg_color=request.bg_color,
        bg_color2=request.bg_color2,
        sub_style=request.sub_style,
        sub_color=request.sub_color,
        sub_highlight=request.sub_highlight,
        sub_outline=request.sub_outline,
        sub_size=request.sub_size,
        sub_position=request.sub_position,
        add_title=bool(request.add_title),
        title_text=request.title_text or clip.title or "",
        title_color=request.title_color,
        title_size=request.title_size,
        title_position=request.title_position,
        video_transform=(
            VideoTransform(**request.video_transform.model_dump())
            if request.video_transform else None
        ),
        quality="draft",  # forced — this endpoint is for previews only
    )

    # Render to a per-request tmp file. We could write to the bytes buffer
    # but ffmpeg expects a real file path, and the data dir is the only
    # place with reliable write permissions.
    from app.config import settings as _settings
    draft_dir = _settings.data_dir / "drafts"
    draft_dir.mkdir(parents=True, exist_ok=True)
    output_path = draft_dir / f"draft_p{project_id}_c{clip_id}_{int(time.time() * 1000)}.mp4"

    try:
        await render_vertical(
            source_video=Path(clip.video_clip_path or clip.audio_clip_path),
            source_audio=Path(clip.audio_clip_path),
            output_path=output_path,
            words=words,
            options=opts,
            duration=float(clip.end) - float(clip.start),
        )
    except Exception as e:
        logger.error("vertical_draft_render_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Draft render failed: {e}")

    # Return the MP4 inline. FastAPI's FileResponse streams it; for small
    # drafts (<5 MB) the browser will buffer it instantly.
    return FileResponse(
        path=str(output_path),
        media_type="video/mp4",
        filename=output_path.name,
        # Background-cleanup is awkward from a sync endpoint; we leave
        # drafts in /data/drafts/ — a tiny cron or on-startup sweep can
        # prune them. They're <5 MB each so it's not urgent.
    )


@router.get("/projects/{project_id}/vertical", response_model=VerticalRenderListResponse)
async def list_project_verticals(project_id: int, db: AsyncSession = Depends(get_db)):
    """List all vertical renders for a project (newest first)."""
    result = await db.execute(
        select(VerticalRender)
        .where(VerticalRender.project_id == project_id)
        .order_by(VerticalRender.created_at.desc())
    )
    rows = list(result.scalars().all())
    return VerticalRenderListResponse(renders=rows)


@router.get("/projects/{project_id}/clips/{clip_id}/vertical",
            response_model=VerticalRenderListResponse)
async def list_clip_verticals(project_id: int, clip_id: int, db: AsyncSession = Depends(get_db)):
    """List all vertical renders for a single clip."""
    result = await db.execute(
        select(VerticalRender)
        .where(VerticalRender.project_id == project_id, VerticalRender.clip_id == clip_id)
        .order_by(VerticalRender.created_at.desc())
    )
    rows = list(result.scalars().all())
    return VerticalRenderListResponse(renders=rows)


@router.get("/projects/{project_id}/vertical/{render_id}",
            response_model=VerticalRenderOut)
async def get_vertical_render(project_id: int, render_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(VerticalRender).where(
            VerticalRender.id == render_id,
            VerticalRender.project_id == project_id,
        )
    )
    vr = result.scalar_one_or_none()
    if not vr:
        raise HTTPException(status_code=404, detail="Render not found")
    return vr


@router.get("/projects/{project_id}/vertical/{render_id}/download")
async def download_vertical_render(project_id: int, render_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(VerticalRender).where(
            VerticalRender.id == render_id,
            VerticalRender.project_id == project_id,
        )
    )
    vr = result.scalar_one_or_none()
    if not vr:
        raise HTTPException(status_code=404, detail="Render not found")
    if vr.status != VerticalRenderStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail=f"Render not ready (status={vr.status})",
        )
    if not vr.output_path or not Path(vr.output_path).exists():
        raise HTTPException(
            status_code=410,
            detail="Output file missing on disk. Re-run the render.",
        )
    return FileResponse(
        vr.output_path,
        media_type="video/mp4",
        filename=f"render_{render_id}.mp4",
    )


@router.delete("/projects/{project_id}/vertical/{render_id}",
               response_model=MessageResponse)
async def delete_vertical_render(project_id: int, render_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(VerticalRender).where(
            VerticalRender.id == render_id,
            VerticalRender.project_id == project_id,
        )
    )
    vr = result.scalar_one_or_none()
    if not vr:
        raise HTTPException(status_code=404, detail="Render not found")
    # Remove the file from disk
    if vr.output_path and Path(vr.output_path).exists():
        try:
            Path(vr.output_path).unlink()
        except OSError:
            pass
    await db.delete(vr)
    await db.commit()
    return MessageResponse(message="Render deleted", detail=f"Render {render_id} removed")


# ── Preset endpoints ──────────────────────────────────────────────────────

@router.get("/vertical/presets", response_model=VerticalPresetListResponse)
async def list_presets(db: AsyncSession = Depends(get_db)):
    """List all saved vertical presets (most recently used first)."""
    result = await db.execute(
        select(VerticalPreset).order_by(VerticalPreset.updated_at.desc())
    )
    rows = list(result.scalars().all())
    return VerticalPresetListResponse(presets=rows)


@router.get("/vertical/presets/{preset_id}", response_model=VerticalPresetOut)
async def get_preset(preset_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(VerticalPreset).where(VerticalPreset.id == preset_id)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Preset not found")
    return p


@router.post("/vertical/presets", response_model=VerticalPresetOut)
async def create_preset(request: VerticalPresetRequest, db: AsyncSession = Depends(get_db)):
    """Create a new preset. Names are unique — a duplicate name returns 409."""
    # Check for duplicate name
    existing = await db.execute(
        select(VerticalPreset).where(VerticalPreset.name == request.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"A preset named '{request.name}' already exists. Choose a different name or delete the existing one first.",
        )
    p = VerticalPreset(
        name=request.name,
        description=request.description,
        layout=request.layout,
        bg_style=request.bg_style,
        bg_color=request.bg_color,
        bg_color2=request.bg_color2,
        sub_style=request.sub_style,
        sub_color=request.sub_color,
        sub_highlight=request.sub_highlight,
        sub_outline=request.sub_outline,
        sub_size=request.sub_size,
        sub_position=request.sub_position,
        add_title=1 if request.add_title else 0,
        title_text=request.title_text,
        title_color=request.title_color,
        title_size=request.title_size,
        title_position=request.title_position,
        watermark_path=request.watermark_path,
        watermark_position=request.watermark_position,
        watermark_opacity=request.watermark_opacity,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


@router.put("/vertical/presets/{preset_id}", response_model=VerticalPresetOut)
async def update_preset(preset_id: int, request: VerticalPresetRequest,
                        db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(VerticalPreset).where(VerticalPreset.id == preset_id)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Preset not found")
    for field in [
        "name", "description", "layout", "bg_style", "bg_color", "bg_color2",
        "sub_style", "sub_color", "sub_highlight", "sub_outline", "sub_size",
        "sub_position", "title_text", "title_color", "title_size", "title_position",
        "watermark_path", "watermark_position", "watermark_opacity",
    ]:
        setattr(p, field, getattr(request, field))
    p.add_title = 1 if request.add_title else 0
    await db.commit()
    await db.refresh(p)
    return p


@router.delete("/vertical/presets/{preset_id}", response_model=MessageResponse)
async def delete_preset(preset_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(VerticalPreset).where(VerticalPreset.id == preset_id)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Preset not found")
    await db.delete(p)
    await db.commit()
    return MessageResponse(message="Preset deleted", detail=f"Preset {preset_id} removed")


# ── Watermark upload ──────────────────────────────────────────────────────

@router.post("/vertical/watermark/upload", response_model=WatermarkUploadResponse)
async def upload_watermark(file: UploadFile = File(...)):
    """Upload a PNG image to use as a watermark.

    The file is stored under ``data/watermarks/`` with a random name to
    avoid collisions. The returned ``url`` is served by the static files
    endpoint and the ``file_id`` can be passed back as
    ``watermark_path`` when creating a render or preset.

    Accepted formats: PNG (with transparency recommended), JPEG.
    Max size: 2 MB.
    """
    # Validate extension
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename in upload")
    ext = Path(file.filename).suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format '{ext}'. Use PNG (with transparency) for best results.",
        )

    # Read the file (capped at 2 MB to avoid abuse)
    contents = await file.read()
    max_bytes = 2 * 1024 * 1024
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(contents)} bytes). Max is {max_bytes} bytes (2 MB).",
        )

    # Save to data/watermarks/ with a unique name
    wm_dir = settings.data_dir / "watermarks"
    wm_dir.mkdir(parents=True, exist_ok=True)
    file_id = secrets.token_urlsafe(12) + ext
    out_path = wm_dir / file_id
    out_path.write_bytes(contents)

    # Try to read dimensions (best effort)
    width: int | None = None
    height: int | None = None
    try:
        from PIL import Image
        import io
        with Image.open(io.BytesIO(contents)) as im:
            width, height = im.size
    except Exception:
        pass

    return WatermarkUploadResponse(
        file_id=file_id,
        filename=file.filename,
        url=f"/api/v1/vertical/watermark/file/{file_id}",
        path=str(out_path.resolve()),
        size=len(contents),
        width=width,
        height=height,
    )


@router.get("/vertical/watermark/file/{file_id}")
async def serve_watermark(file_id: str):
    """Serve an uploaded watermark file (so the UI can preview it)."""
    # Validate the file_id to prevent path traversal
    if "/" in file_id or "\\" in file_id or ".." in file_id:
        raise HTTPException(status_code=400, detail="Invalid file_id")
    wm_dir = settings.data_dir / "watermarks"
    fpath = wm_dir / file_id
    if not fpath.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(fpath)
