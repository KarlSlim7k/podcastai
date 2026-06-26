"""Abstract base class for Whisper backends.

A backend wraps a specific underlying library (faster-whisper, mlx-whisper)
and exposes a uniform interface so the rest of the app doesn't have to
care which one is in use.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator


@dataclass
class TranscriptionSegment:
    """One segment of a transcription (matches the original Whisper output).

    A segment is typically one sentence / pause. It contains the recognized
    text plus per-word timestamps if available.
    """

    id: int
    start: float
    end: float
    text: str
    words: list[dict] = field(default_factory=list)  # [{word, start, end, prob}]


@dataclass
class TranscriptionResult:
    """Full transcription output from any backend."""

    text: str
    segments: list[TranscriptionSegment]
    language: str
    duration: float
    model_used: str
    backend_name: str  # "faster_whisper" or "mlx_whisper"

    def to_dict(self) -> dict:
        """Serialize to the same dict shape we already store in the DB.
        This keeps backwards compatibility with the existing transcription
        code in :mod:`app.services.transcription_service`.
        """
        return {
            "text": self.text,
            "language": self.language,
            "duration": self.duration,
            "segments": [
                {
                    "id": s.id,
                    "start": s.start,
                    "end": s.end,
                    "text": s.text,
                    "words": s.words,
                }
                for s in self.segments
            ],
        }


class WhisperBackend(ABC):
    """Abstract base class for all Whisper backends."""

    #: Human-readable name (used in logs and DB ``model_used``).
    name: str = "base"

    @abstractmethod
    def transcribe(
        self,
        audio_path: str | Path,
        language: str | None = "es",
        beam_size: int = 5,
        vad_filter: bool = True,
    ) -> TranscriptionResult:
        """Transcribe an audio file to text.

        Args:
            audio_path: Path to a 16kHz mono WAV/MP3/anything ffmpeg can read.
            language: ISO 639-1 code, or None to auto-detect.
            beam_size: Beam search width. Higher = slower but more accurate.
            vad_filter: Use voice activity detection to skip silences.
        """

    @abstractmethod
    def warmup(self) -> None:
        """Optional preload of the model into memory. Called once at startup."""


def iter_segments(segments: list[TranscriptionSegment]) -> Iterator[TranscriptionSegment]:
    """Helper to iterate over segments with the canonical schema."""
    return iter(segments)
