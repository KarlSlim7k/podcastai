from pathlib import Path
from fastapi import APIRouter
from app.models.schemas import SystemStatus, OllamaModel
from app.services.ai_service import ai_service
from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/system", tags=["system"])


def _is_whisper_model_cached(model_name: str) -> bool:
    """Return True if the faster-whisper model files are already in the HF cache."""
    import os
    hf_home = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    model_dir = hf_home / "hub" / f"models--Systran--faster-whisper-{model_name}"
    if not model_dir.exists():
        return False
    snapshots = model_dir / "snapshots"
    if not snapshots.exists():
        return False
    for snap in snapshots.iterdir():
        if snap.is_dir() and (snap / "model.bin").exists():
            return True
    return False


@router.get("/status", response_model=SystemStatus)
async def get_status():
    cuda_available = False
    vram_total = None
    vram_free = None

    try:
        import torch
        cuda_available = torch.cuda.is_available()
        if cuda_available:
            vram_total = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
            vram_free = (torch.cuda.get_device_properties(0).total_memory - torch.cuda.memory_allocated(0)) / (1024 ** 3)
    except ImportError:
        pass

    whisper_available = False
    try:
        import faster_whisper
        whisper_available = True
    except ImportError:
        pass

    ollama_available, ollama_models = await ai_service.check_availability()
    llamacpp_available, llamacpp_models = ai_service.check_llamacpp()

    whisper_model_name = settings.whisper_model
    whisper_model_cached = _is_whisper_model_cached(whisper_model_name) if whisper_available else False

    return SystemStatus(
        status="ok",
        whisper_available=whisper_available,
        whisper_model_cached=whisper_model_cached,
        whisper_model_name=whisper_model_name,
        ollama_available=ollama_available,
        ollama_models=ollama_models,
        llamacpp_available=llamacpp_available,
        llamacpp_models=llamacpp_models,
        cuda_available=cuda_available,
        vram_total_gb=round(vram_total, 2) if vram_total else None,
        vram_free_gb=round(vram_free, 2) if vram_free else None,
    )


@router.get("/models", response_model=list[OllamaModel])
async def list_models():
    models = await ai_service.list_models()
    return [
        OllamaModel(
            name=m.get("name", ""),
            size=m.get("size"),
            modified_at=str(m.get("modified_at", "")),
        )
        for m in models
    ]


@router.get("/health")
async def health():
    return {"status": "healthy", "version": settings.app_version}


@router.get("/hardware")
async def hardware():
    """Return detailed hardware info for the current machine.

    Used by the frontend to show a "running on..." badge and to help
    diagnose performance issues. Safe to call any time — does not
    trigger any expensive detection.
    """
    from app.utils.hardware import detect_hardware
    hw = detect_hardware()
    return {
        "os": hw.os,
        "is_apple_silicon": hw.is_apple_silicon,
        "has_cuda": hw.has_cuda,
        "has_metal": hw.has_metal,
        "has_ffmpeg_nvenc": hw.has_ffmpeg_nvenc,
        "has_ffmpeg_videotoolbox": hw.has_ffmpeg_videotoolbox,
        "has_ffmpeg_qsv": hw.has_ffmpeg_qsv,
        "compute_backend": hw.compute_backend,
        "whisper_backend": hw.whisper_backend,
        "ffmpeg_encoder": hw.ffmpeg_encoder,
        "ffmpeg_path": hw.ffmpeg_path,
        "summary": hw.summary(),
    }
