"""Factory that picks the right Whisper backend for the current hardware.

The chosen backend is cached as a module-level singleton so we don't
reload the model between transcriptions. Call :func:`reset_backend_cache`
in tests to force a fresh load.
"""
from __future__ import annotations

from functools import lru_cache

from .base import WhisperBackend
from app.utils.hardware import detect_hardware
from app.utils.logger import get_logger
from app.config import settings

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def _build_backend() -> WhisperBackend:
    """Construct the backend chosen by the hardware detector.

    Uses :func:`app.utils.hardware.detect_hardware` to decide between
    faster-whisper (universal) and mlx-whisper (Apple Silicon only).
    """
    hw = detect_hardware()

    if hw.whisper_backend == "mlx_whisper":
        try:
            from .mlx_whisper_backend import MlxWhisperBackend
            model_size = getattr(settings, "mlx_whisper_model",
                                 "mlx-community/whisper-large-v3-mlx")
            logger.info("whisper_backend_chosen",
                        backend="mlx_whisper", model=model_size)
            return MlxWhisperBackend(model_size=model_size)
        except Exception as e:
            logger.warning("mlx_whisper_init_failed_falling_back", error=str(e))

    from .faster_whisper_backend import FasterWhisperBackend
    model_size = getattr(settings, "whisper_model", "large-v3")
    logger.info("whisper_backend_chosen",
                backend="faster_whisper", model=model_size)
    return FasterWhisperBackend(model_size=model_size)


def get_whisper_backend() -> WhisperBackend:
    """Return the cached Whisper backend (loads on first call)."""
    return _build_backend()


def reset_backend_cache() -> None:
    """Clear the cached backend (for tests)."""
    _build_backend.cache_clear()
