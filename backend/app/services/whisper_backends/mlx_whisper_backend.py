"""MLX-Whisper backend (Apple MLX framework).

macOS Apple Silicon only. Uses the Neural Engine via Metal for
high-performance inference. Performance is comparable to CUDA on
discrete GPUs, with much lower power consumption.

Installation (only on macOS with M-series):
    pip install mlx-whisper

If mlx-whisper is not installed, the factory will fall back to
faster-whisper. The backend itself does not import mlx_whisper at
module load time so the app keeps working on non-macOS systems.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .base import WhisperBackend, TranscriptionResult, TranscriptionSegment
from app.utils.logger import get_logger

logger = get_logger(__name__)


class MlxWhisperBackend(WhisperBackend):
    name = "mlx_whisper"

    def __init__(self, model_size: str = "mlx-community/whisper-large-v3-mlx"):
        """
        Args:
            model_size: A model from the ``mlx-community`` HuggingFace org.
                Recommended: ``mlx-community/whisper-large-v3-mlx`` for
                Spanish, or ``mlx-community/whisper-large-v3-turbo`` for speed.
        """
        # Importing mlx_whisper here (lazy) means the rest of the app can
        # be imported on any platform without crashing.
        import mlx_whisper  # type: ignore  # noqa: F401

        self.model_size = model_size
        self._warmed_up = False
        logger.info("mlx_whisper_init", model_size=model_size)

    def warmup(self) -> None:
        # mlx_whisper loads on first transcribe(), so we do a quick warmup
        # by transcribing a tiny silence buffer. This is a no-op if the
        # model was already warmed up.
        if self._warmed_up:
            return
        try:
            import numpy as np  # type: ignore
            import mlx_whisper  # type: ignore
            import soundfile as sf  # type: ignore

            # 1 second of silence at 16kHz mono
            silence = np.zeros(16000, dtype="float32")
            tmp_path = Path("/tmp/_mlx_whisper_warmup.wav")
            sf.write(tmp_path, silence, 16000)
            try:
                mlx_whisper.transcribe(
                    str(tmp_path),
                    path_or_hf_repo=self.model_size,
                    language="en",
                )
            finally:
                if tmp_path.exists():
                    tmp_path.unlink()
            self._warmed_up = True
            logger.info("mlx_whisper_warmed_up")
        except Exception as e:
            logger.warning("mlx_whisper_warmup_failed", error=str(e))

    def transcribe(
        self,
        audio_path: str | Path,
        language: str | None = "es",
        beam_size: int = 5,
        vad_filter: bool = True,
    ) -> TranscriptionResult:
        import mlx_whisper  # type: ignore

        t0 = time.time()
        # mlx-whisper takes slightly different option names than faster-whisper.
        # We normalize here so the rest of the app can use a single interface.
        result: dict[str, Any] = mlx_whisper.transcribe(
            str(audio_path),
            path_or_hf_repo=self.model_size,
            language=language or "auto",
            word_timestamps=True,
        )

        segments: list[TranscriptionSegment] = []
        for i, seg in enumerate(result.get("segments", [])):
            words = []
            # mlx-whisper word_timestamps format: [{word, start, end, probability}]
            for w in seg.get("words", []) or []:
                # mlx-whisper uses "t" for start/end sometimes; normalize.
                words.append({
                    "word": w.get("word", ""),
                    "start": float(w.get("start", w.get("t", 0.0))),
                    "end": float(w.get("end", w.get("t", 0.0) + 0.1)),
                    "prob": float(w.get("probability", w.get("p", 1.0))),
                })
            segments.append(TranscriptionSegment(
                id=i,
                start=float(seg.get("start", 0.0)),
                end=float(seg.get("end", 0.0)),
                text=seg.get("text", "").strip(),
                words=words,
            ))
        text = result.get("text", "") or " ".join(s.text for s in segments)
        elapsed = time.time() - t0

        # mlx-whisper doesn't return language detection info as cleanly.
        # We use the language param we passed in, or default to "es".
        detected_lang = language or result.get("language", "es")
        duration = segments[-1].end if segments else 0.0

        logger.info("mlx_whisper_transcribed",
                    duration=round(duration, 1), elapsed=round(elapsed, 1),
                    n_segments=len(segments))
        return TranscriptionResult(
            text=text,
            segments=segments,
            language=detected_lang,
            duration=duration,
            model_used=self.model_size,
            backend_name=self.name,
        )
