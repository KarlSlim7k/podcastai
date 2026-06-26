"""Speaker diarization service using pyannote-audio (optional dependency).

This service is only active if ``pyannote.audio`` is installed AND a valid
HuggingFace token (``HF_TOKEN`` or ``PYANNOTE_TOKEN``) is set in the
environment. If either is missing, ``is_available()`` returns False and the
service becomes a no-op, so transcription still works for everyone.

First-time setup (one-time, ~1.5 GB download):
    1. Accept the EULA at https://huggingface.co/pyannote/speaker-diarization-3.1
    2. Accept the EULA at https://huggingface.co/pyannote/segmentation-3.0
    3. Create a token at https://huggingface.co/settings/tokens
    4. Set HF_TOKEN=hf_xxxx in backend/.env
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from app.utils.logger import get_logger

logger = get_logger(__name__)


class DiarizationService:
    """Wrapper around pyannote-audio's pretrained diarization pipeline."""

    _pipeline: Any | None = None  # lazy-loaded, cached across calls
    _available: bool | None = None  # tri-state: None=unchecked, True/False

    def is_available(self) -> bool:
        """Return True only if pyannote AND a HF token are present."""
        if self._available is not None:
            return self._available

        try:
            import pyannote.audio  # noqa: F401
        except ImportError:
            logger.info("diarization_unavailable", reason="pyannote.audio not installed")
            self._available = False
            return False

        token = os.environ.get("HF_TOKEN") or os.environ.get("PYANNOTE_TOKEN")
        if not token:
            logger.info("diarization_unavailable", reason="HF_TOKEN not set")
            self._available = False
            return False

        self._available = True
        return True

    def _get_pipeline(self) -> Any:
        if self._pipeline is not None:
            return self._pipeline
        from pyannote.audio import Pipeline
        token = os.environ.get("HF_TOKEN") or os.environ.get("PYANNOTE_TOKEN")
        # The pipeline will lazy-download the two required models on first use.
        self._pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=token,
        )
        # Send to GPU if available (CTranslate2/faster-whisper already use it;
        # pyannote needs the same device for max throughput).
        try:
            import torch
            if torch.cuda.is_available():
                self._pipeline.to(torch.device("cuda"))
        except ImportError:
            pass
        return self._pipeline

    def diarize(self, audio_path: Path, min_speakers: int | None = None, max_speakers: int | None = None) -> list[dict]:
        """Run speaker diarization on an audio file.

        Returns a list of segments:
            [{"speaker": "SPEAKER_00", "start": 1.2, "end": 5.4}, ...]

        ``min_speakers`` / ``max_speakers`` are optional hints (set them if you
        already know the number of hosts).
        """
        if not self.is_available():
            return []

        pipeline = self._get_pipeline()
        kwargs: dict = {}
        if min_speakers is not None:
            kwargs["min_speakers"] = min_speakers
        if max_speakers is not None:
            kwargs["max_speakers"] = max_speakers

        diarization = pipeline(str(audio_path), **kwargs)

        segments: list[dict] = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            segments.append({
                "speaker": speaker,
                "start": round(turn.start, 3),
                "end": round(turn.end, 3),
            })
        return segments

    @staticmethod
    def assign_speakers_to_whisper_segments(
        whisper_segments: list[dict],
        diarization_segments: list[dict],
    ) -> list[dict]:
        """For each Whisper segment, find the speaker with the most overlap.

        Pure-Python implementation — avoids requiring pyannote if we already
        have the diarization output. The overlap is measured in seconds and
        the speaker with the longest overlap wins (ties broken by earlier
        start time).
        """
        if not diarization_segments:
            return whisper_segments

        out: list[dict] = []
        for seg in whisper_segments:
            seg_start = seg["start"]
            seg_end = seg["end"]
            best_speaker = None
            best_overlap = 0.0
            best_diar_start = float("inf")
            for diar in diarization_segments:
                overlap = max(0.0, min(seg_end, diar["end"]) - max(seg_start, diar["start"]))
                if overlap > best_overlap or (overlap == best_overlap and overlap > 0 and diar["start"] < best_diar_start):
                    best_overlap = overlap
                    best_speaker = diar["speaker"]
                    best_diar_start = diar["start"]
            out.append({**seg, "speaker": best_speaker})
        return out

    @staticmethod
    def get_speaker_stats(segments: list[dict]) -> list[dict]:
        """Aggregate per-speaker totals for display.

        Returns: [{"speaker": "SPEAKER_00", "total_time": 142.3, "turns": 27, "words": 432}]
        """
        stats: dict[str, dict] = {}
        for seg in segments:
            sp = seg.get("speaker")
            if not sp:
                continue
            if sp not in stats:
                stats[sp] = {"speaker": sp, "total_time": 0.0, "turns": 0, "words": 0}
            stats[sp]["total_time"] += max(0.0, seg["end"] - seg["start"])
            stats[sp]["turns"] += 1
            stats[sp]["words"] += len((seg.get("text") or "").split())
        return sorted(stats.values(), key=lambda s: s["total_time"], reverse=True)


diarization_service = DiarizationService()
