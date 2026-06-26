"""Faster-Whisper backend (CTranslate2).

Works on Windows, Linux, and macOS. Uses CUDA on NVIDIA GPUs, falls back
to CPU otherwise. This is the universal backend and is always available.
"""
from __future__ import annotations

import time
from pathlib import Path

from .base import WhisperBackend, TranscriptionResult, TranscriptionSegment
from app.utils.logger import get_logger

logger = get_logger(__name__)


class FasterWhisperBackend(WhisperBackend):
    name = "faster_whisper"

    def __init__(self, model_size: str = "large-v3", device: str = "auto",
                 compute_type: str = "auto"):
        """
        Args:
            model_size: One of tiny/base/small/medium/large-v3, or a HF model id.
            device: ``"cuda"``, ``"cpu"``, or ``"auto"`` (use CUDA if available).
            compute_type: ``"float16"``, ``"int8"``, ``"auto"`` — auto picks based on device.
        """
        from faster_whisper import WhisperModel  # heavy import, deferred

        if device == "auto":
            try:
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                device = "cpu"

        if compute_type == "auto":
            compute_type = "float16" if device == "cuda" else "int8"

        logger.info("faster_whisper_init",
                    model_size=model_size, device=device, compute_type=compute_type)
        self.model = WhisperModel(model_size, device=device, compute_type=compute_type)
        self.model_size = model_size
        self._warmed_up = False

    def warmup(self) -> None:
        # faster-whisper loads on __init__, so this is a no-op
        # but we keep the API symmetric with mlx_whisper.
        self._warmed_up = True

    def transcribe(
        self,
        audio_path: str | Path,
        language: str | None = "es",
        beam_size: int = 5,
        vad_filter: bool = True,
    ) -> TranscriptionResult:
        t0 = time.time()
        segments_iter, info = self.model.transcribe(
            str(audio_path),
            language=language,
            beam_size=beam_size,
            vad_filter=vad_filter,
            word_timestamps=True,  # needed for the vertical editor's karaoke subs
        )
        segments: list[TranscriptionSegment] = []
        for seg in segments_iter:
            words = []
            if seg.words:
                words = [
                    {
                        "word": w.word,
                        "start": float(w.start) if w.start is not None else 0.0,
                        "end": float(w.end) if w.end is not None else 0.0,
                        "prob": float(w.probability) if hasattr(w, "probability") else 1.0,
                    }
                    for w in seg.words
                ]
            segments.append(TranscriptionSegment(
                id=seg.id,
                start=float(seg.start),
                end=float(seg.end),
                text=seg.text.strip(),
                words=words,
            ))
        text = " ".join(s.text for s in segments)
        elapsed = time.time() - t0
        logger.info("faster_whisper_transcribed",
                    duration=info.duration, elapsed=round(elapsed, 1),
                    n_segments=len(segments))
        return TranscriptionResult(
            text=text,
            segments=segments,
            language=info.language,
            duration=info.duration,
            model_used=self.model_size,
            backend_name=self.name,
        )
