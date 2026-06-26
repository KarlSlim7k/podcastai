import asyncio
import functools
import json
import time
from pathlib import Path
from typing import Callable
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.project import Transcription, TranscriptionStatus, Project, ProjectStatus
from app.config import settings
from app.services.diarization_service import diarization_service
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _format_timestamp(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def _segments_to_srt(segments: list) -> str:
    lines = []
    for i, seg in enumerate(segments, 1):
        start = _format_timestamp(seg["start"]).replace(".", ",")
        end = _format_timestamp(seg["end"]).replace(".", ",")
        lines.append(f"{i}\n{start} --> {end}\n{seg['text'].strip()}\n")
    return "\n".join(lines)


def _segments_to_vtt(segments: list) -> str:
    lines = ["WEBVTT\n"]
    for seg in segments:
        start = _format_timestamp(seg["start"])
        end = _format_timestamp(seg["end"])
        lines.append(f"{start} --> {end}\n{seg['text'].strip()}\n")
    return "\n".join(lines)


def _run_whisper_sync(
    audio_path: str,
    model_name: str,
    device: str,
    compute_type: str,
    beam_size: int,
    language: str | None,
    progress_callback: Callable | None = None,
) -> dict:
    """Run Whisper transcription using the auto-detected backend.

    The ``model_name``, ``device`` and ``compute_type`` parameters are
    kept for backwards compatibility but the actual backend (faster-whisper
    or mlx-whisper) is selected by :func:`app.utils.hardware.detect_hardware`.
    """
    from app.services.whisper_backends import get_whisper_backend

    backend = get_whisper_backend()
    result = backend.transcribe(
        audio_path,
        language=language,
        beam_size=beam_size,
        vad_filter=True,
    )
    total_duration = result.duration or 0.0
    transcribe_start = time.time()

    # Convert the backend-agnostic TranscriptionResult into the legacy
    # dict shape that the rest of the app (and the DB) already expects.
    # The progress callback still works because we know the segment times.
    full_text_parts: list[str] = []
    segments: list[dict] = []
    for seg in result.segments:
        # Normalize word shape to the one we already store in the DB:
        # {word, start, end, probability} (the old code used "probability"
        # not "prob"; we preserve that for backwards compat).
        words = []
        for w in seg.words:
            words.append({
                "word": w["word"],
                "start": w["start"],
                "end": w["end"],
                "probability": w.get("prob", 1.0),
            })
        segments.append({
            "id": seg.id,
            "start": seg.start,
            "end": seg.end,
            "text": seg.text,
            "words": words,
        })
        full_text_parts.append(seg.text)

        if progress_callback and total_duration > 0:
            pct = min(90, 5 + (seg.end / total_duration * 85))
            elapsed_seg = time.time() - transcribe_start
            speed = seg.end / elapsed_seg if elapsed_seg > 0 else 0
            remaining = (total_duration - seg.end) / speed if speed > 0 else None
            progress_callback(pct, seg.end, total_duration, remaining)

    # Best-effort: free CUDA cache if we used it. No-op on CPU/Metal.
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass

    return {
        "text": " ".join(full_text_parts).strip(),
        "segments": segments,
        "language": result.language,
        "language_probability": None,  # mlx-whisper doesn't expose this
        "duration": result.duration,
        "backend": result.backend_name,
        "model_used": result.model_used,
    }


class TranscriptionService:
    _progress_store: dict[int, dict] = {}

    def update_progress(self, project_id: int, data: dict):
        self._progress_store[project_id] = data

    def get_progress(self, project_id: int) -> dict:
        return self._progress_store.get(project_id, {"status": "idle", "progress": 0})

    async def transcribe(
        self,
        db: AsyncSession,
        project_id: int,
        audio_path: Path,
        model_name: str = "large-v3",
        language: str | None = None,
        beam_size: int = 5,
    ) -> Transcription:
        result = await db.execute(
            select(Transcription).where(Transcription.project_id == project_id)
        )
        transcription = result.scalar_one_or_none()
        if not transcription:
            transcription = Transcription(project_id=project_id)
            db.add(transcription)

        transcription.status = TranscriptionStatus.PROCESSING
        transcription.model_used = model_name
        transcription.language_requested = language
        transcription.beam_size = beam_size
        await db.flush()

        self.update_progress(project_id, {
            "status": "processing",
            "progress": 5,
            "current_step": "Loading Whisper model...",
        })

        def _progress_cb(pct: float, current_sec: float, total_sec: float, remaining: float | None):
            mins_done = current_sec / 60
            mins_total = total_sec / 60
            step = f"Transcribing... {mins_done:.1f}/{mins_total:.1f} min"
            self.update_progress(project_id, {
                "status": "processing",
                "progress": pct,
                "current_step": step,
                "estimated_remaining": remaining,
            })

        try:
            start_time = time.time()

            loop = asyncio.get_running_loop()
            result_data = await loop.run_in_executor(
                None,
                functools.partial(
                    _run_whisper_sync,
                    str(audio_path),
                    model_name,
                    settings.whisper_device,
                    settings.whisper_compute_type,
                    beam_size,
                    language,
                    _progress_cb,
                ),
            )

            # ── Diarization (optional) ─────────────────────────────────────
            # If pyannote + HF_TOKEN are available, run speaker attribution
            # AFTER whisper finishes. This is a second pass over the audio.
            # We surface progress updates so the UI doesn't appear frozen.
            speakers_count: int | None = None
            speaker_stats: list[dict] = []
            if diarization_service.is_available():
                self.update_progress(project_id, {
                    "status": "processing",
                    "progress": 92,
                    "current_step": "Identifying speakers (diarization)...",
                })
                try:
                    diarization = await loop.run_in_executor(
                        None,
                        diarization_service.diarize,
                        audio_path,
                    )
                    result_data["segments"] = diarization_service.assign_speakers_to_whisper_segments(
                        result_data["segments"], diarization,
                    )
                    speaker_stats = diarization_service.get_speaker_stats(result_data["segments"])
                    speakers_count = len(speaker_stats)
                    logger.info("diarization_completed",
                                project_id=project_id,
                                speakers=speakers_count,
                                segments=len(diarization))
                except Exception as e:
                    # Diarization failed — don't fail the whole transcription.
                    # Continue with the Whisper output (no speaker info).
                    logger.warning("diarization_failed",
                                   project_id=project_id, error=str(e))

            elapsed = time.time() - start_time

            self.update_progress(project_id, {
                "status": "saving",
                "progress": 95,
                "current_step": "Saving transcription files...",
            })

            transcription.text = result_data["text"]
            transcription.segments = result_data["segments"]
            transcription.language_detected = result_data["language"]
            transcription.processing_time = elapsed
            transcription.word_count = len(result_data["text"].split())
            transcription.speaker_stats = speaker_stats
            transcription.status = TranscriptionStatus.COMPLETED

            output_dir = settings.transcriptions_dir / str(project_id)
            output_dir.mkdir(parents=True, exist_ok=True)

            txt_path = output_dir / "transcription.txt"
            txt_path.write_text(result_data["text"], encoding="utf-8")
            transcription.txt_file = str(txt_path)

            json_path = output_dir / "transcription.json"
            json_path.write_text(json.dumps(result_data, ensure_ascii=False, indent=2), encoding="utf-8")
            transcription.json_file = str(json_path)

            srt_path = output_dir / "transcription.srt"
            srt_path.write_text(_segments_to_srt(result_data["segments"]), encoding="utf-8")
            transcription.srt_file = str(srt_path)

            vtt_path = output_dir / "transcription.vtt"
            vtt_path.write_text(_segments_to_vtt(result_data["segments"]), encoding="utf-8")
            transcription.vtt_file = str(vtt_path)

            await db.flush()

            self.update_progress(project_id, {
                "status": "completed",
                "progress": 100,
                "current_step": "Transcription complete",
            })

            logger.info("transcription_completed",
                       project_id=project_id,
                       words=transcription.word_count,
                       duration=f"{elapsed:.1f}s",
                       language=result_data["language"])

            return transcription

        except Exception as e:
            transcription.status = TranscriptionStatus.ERROR
            transcription.error_message = str(e)
            await db.flush()
            self.update_progress(project_id, {
                "status": "error",
                "progress": 0,
                "current_step": f"Error: {str(e)[:200]}",
            })
            logger.error("transcription_failed", project_id=project_id, error=str(e))
            raise


transcription_service = TranscriptionService()
