"""Whisper transcription backends.

The base class ``WhisperBackend`` defines the interface used by the rest
of the app. Concrete backends wrap different underlying libraries:

  - :class:`FasterWhisperBackend` — uses faster-whisper (CTranslate2).
    Works on Windows, Linux, and macOS. CUDA on NVIDIA, CPU otherwise.

  - :class:`MlxWhisperBackend` — uses mlx-whisper (Apple MLX framework).
    macOS Apple Silicon only. Uses the Neural Engine via Metal.

The right backend is picked by :func:`app.utils.hardware.detect_hardware`
and the matching subclass is instantiated by :func:`get_whisper_backend`.
"""
from .base import WhisperBackend, TranscriptionResult, TranscriptionSegment
from .factory import get_whisper_backend, reset_backend_cache

__all__ = [
    "WhisperBackend",
    "TranscriptionResult",
    "TranscriptionSegment",
    "get_whisper_backend",
    "reset_backend_cache",
]
