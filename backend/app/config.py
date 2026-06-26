from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field


BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"


class Settings(BaseSettings):
    # App
    app_name: str = "PodcastAI Transcriber"
    app_version: str = "1.5.0"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    # Database
    database_url: str = f"sqlite+aiosqlite:///{DATA_DIR}/app.db"
    database_sync_url: str = f"sqlite:///{DATA_DIR}/app.db"

    # Storage
    data_dir: Path = DATA_DIR
    uploads_dir: Path = DATA_DIR / "uploads"
    projects_dir: Path = DATA_DIR / "projects"
    transcriptions_dir: Path = DATA_DIR / "transcriptions"
    exports_dir: Path = DATA_DIR / "exports"
    logs_dir: Path = DATA_DIR / "logs"

    # File validation
    max_file_size_mb: int = 2048
    allowed_extensions: list[str] = [".mp4", ".mkv", ".avi", ".mov", ".mp3", ".wav", ".m4a"]
    allowed_mime_types: list[str] = [
        "video/mp4", "video/x-matroska", "video/x-msvideo",
        "video/quicktime", "audio/mpeg", "audio/wav", "audio/x-wav",
        "audio/mp4", "audio/x-m4a", "audio/aac",
        "video/mpeg", "application/octet-stream"
    ]

    # Whisper
    whisper_model: str = "large-v3"
    whisper_device: str = "auto"  # "auto" lets hardware detection pick cuda/cpu
    whisper_compute_type: str = "auto"
    whisper_beam_size: int = 5
    whisper_language: str | None = None
    whisper_batch_size: int = 16

    # macOS Apple Silicon: mlx-whisper model (only used on M-series Macs)
    # Recommended: mlx-community/whisper-large-v3-mlx (best quality)
    # or mlx-community/whisper-large-v3-turbo (faster, slightly less accurate)
    mlx_whisper_model: str = "mlx-community/whisper-large-v3-mlx"

    # Fonts for subtitle rendering (ffmpeg/ASS). The first one found is used.
    # On Windows we try the system Arial; on macOS we use Helvetica/Arial;
    # on Linux we fall back to DejaVu Sans (always present).
    subtitle_font_paths: list[str] = [
        # Windows
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        # macOS
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        # Linux
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
    ]

    # Ollama
    ollama_host: str = "http://localhost:11434"
    ollama_default_model: str = "qwen3:14b"
    ollama_timeout: int = 300

    # Pexels API for AI b-rolls (Phase 11). Get a free key at https://www.pexels.com/api/
    # If left empty, the app uses a small set of mock b-rolls so the UI
    # can still be developed and tested without a Pexels account.
    pexels_api_key: str = ""

    # Max number of vertical renders (ffmpeg encodes) allowed to run at the
    # same time. Batch-exporting many clips queues them all as background
    # tasks immediately, but consumer GPUs (NVENC) and CPUs choke if too
    # many ffmpeg processes run concurrently — this caps it.
    vertical_render_concurrency: int = 2

    # Social media OAuth (Phase 12). Leave any of these empty to use the
    # mock publisher for that platform. See the Phase 12 README section
    # for step-by-step setup instructions.
    tiktok_client_key: str = ""
    tiktok_client_secret: str = ""
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    instagram_app_id: str = ""
    instagram_app_secret: str = ""

    # OAuth callback base URL — where social platforms redirect after
    # authorization. Must be reachable from the user's browser.
    # In dev, this is http://localhost:8000. For prod, set to your domain.
    oauth_redirect_base: str = "http://localhost:8000"

    # LlamaCpp (alternative AI backend)
    llamacpp_models_dir: Path = DATA_DIR / "models"
    llamacpp_n_gpu_layers: int = -1  # -1 = all layers on GPU
    llamacpp_n_ctx: int = 4096
    llamacpp_max_tokens: int = 2048

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"]

    class Config:
        # Look for .env in the project root (one level above backend/).
        # The user puts it there (next to start.sh / start.bat), and that's
        # where pydantic-settings should find it regardless of the cwd
        # the backend was launched from.
        import os as _os
        _project_root = Path(__file__).parent.parent.parent
        _env_candidates = [
            _project_root / ".env",
            Path(__file__).parent.parent / ".env",  # backend/.env (fallback)
        ]
        env_file = str(next((p for p in _env_candidates if p.exists()),
                            _env_candidates[0]))
        env_file_encoding = "utf-8"


settings = Settings()

# Ensure directories exist
for directory in [
    settings.data_dir,
    settings.uploads_dir,
    settings.projects_dir,
    settings.transcriptions_dir,
    settings.exports_dir,
    settings.logs_dir,
    settings.llamacpp_models_dir,
]:
    directory.mkdir(parents=True, exist_ok=True)
