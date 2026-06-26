"""Hardware detection utilities.

Detects the optimal compute backend (CUDA, Metal, CPU) and the best
available ffmpeg video encoder (h264_nvenc, h264_videotoolbox, libx264)
for the current platform.

This module is the single source of truth for hardware-specific decisions.
The rest of the codebase should import from here rather than detecting
hardware themselves.
"""
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.utils.logger import get_logger

logger = get_logger(__name__)

ComputeBackend = Literal["cuda", "metal", "rocm", "cpu"]
WhisperBackendName = Literal["faster_whisper", "mlx_whisper"]


@dataclass(frozen=True)
class HardwareProfile:
    """The hardware capabilities detected on this machine.

    Attributes:
        os: ``"windows"``, ``"linux"``, or ``"darwin"`` (macOS).
        is_apple_silicon: True if running on macOS with an M-series chip.
        has_cuda: True if an NVIDIA GPU is visible to PyTorch / faster-whisper.
        has_metal: True if Metal is available (macOS).
        has_ffmpeg_nvenc: True if ffmpeg has the ``h264_nvenc`` encoder compiled in.
        has_ffmpeg_videotoolbox: True if ffmpeg has ``h264_videotoolbox`` (macOS).
        has_ffmpeg_qsv: True if ffmpeg has Intel QuickSync.
        compute_backend: The optimal compute backend for ML workloads.
        whisper_backend: Which Whisper backend to use.
        ffmpeg_encoder: The best available ffmpeg video encoder.
        ffmpeg_path: Absolute path to the ffmpeg binary.
    """

    os: str
    is_apple_silicon: bool
    has_cuda: bool
    has_metal: bool
    has_ffmpeg_nvenc: bool
    has_ffmpeg_videotoolbox: bool
    has_ffmpeg_qsv: bool
    compute_backend: ComputeBackend
    whisper_backend: WhisperBackendName
    ffmpeg_encoder: str
    ffmpeg_path: str

    def summary(self) -> str:
        """One-line human readable summary for logs / startup banner."""
        return (
            f"OS={self.os} AppleSilicon={self.is_apple_silicon} "
            f"CUDA={self.has_cuda} Metal={self.has_metal} "
            f"compute={self.compute_backend} whisper={self.whisper_backend} "
            f"ffmpeg_encoder={self.ffmpeg_encoder}"
        )


# ── ffmpeg discovery ──────────────────────────────────────────────────────

def find_ffmpeg() -> str | None:
    """Find the ffmpeg binary on the current system.

    Search order:
      1. ``ffmpeg`` in PATH (preferred — matches the system package manager)
      2. Common Windows install locations (BtbN, gyan.dev builds)
      3. Common macOS install locations (Homebrew, MacPorts)

    Returns the absolute path or None if not found.
    """
    # PATH first
    p = shutil.which("ffmpeg")
    if p:
        return p

    sys_os = platform.system().lower()
    if sys_os == "windows":
        candidates = [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
            str(Path.home() / "scoop" / "shims" / "ffmpeg.exe"),
        ]
    elif sys_os == "darwin":
        candidates = [
            "/opt/homebrew/bin/ffmpeg",      # Apple Silicon Homebrew
            "/usr/local/bin/ffmpeg",         # Intel Mac Homebrew
            "/opt/local/bin/ffmpeg",         # MacPorts
        ]
    else:  # linux
        candidates = [
            "/usr/bin/ffmpeg",
            "/usr/local/bin/ffmpeg",
            str(Path.home() / ".local" / "bin" / "ffmpeg"),
        ]

    for c in candidates:
        if Path(c).exists():
            return c
    return None


def _ffmpeg_has_encoder(ffmpeg_path: str, encoder: str) -> bool:
    """Return True if the ffmpeg binary was compiled with ``encoder``."""
    try:
        out = subprocess.run(
            [ffmpeg_path, "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=10,
        )
        # Encoder names appear as " V..... encoder_name  description"
        return any(line.strip().startswith(encoder) and "V" in line[:10]
                   for line in out.stdout.splitlines())
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


# ── GPU / compute detection ───────────────────────────────────────────────

def _detect_cuda() -> bool:
    """Return True if PyTorch can see a CUDA device (NVIDIA GPU).

    We probe via ``torch.cuda.is_available()`` because that's the same
    library faster-whisper uses internally. If torch is not installed
    we return False (the rest of the app will fall back to CPU).
    """
    try:
        import torch  # type: ignore
        return bool(torch.cuda.is_available())
    except (ImportError, Exception):
        return False


def _detect_metal() -> bool:
    """Return True if running on macOS with an Apple Silicon chip.

    Apple Silicon = M1 / M2 / M3 / M4 (and Pro / Max / Ultra variants).
    We detect via platform.machine() which returns ``arm64`` on M-series.
    """
    if platform.system() != "Darwin":
        return False
    machine = platform.machine().lower()
    return machine == "arm64"


def _detect_apple_silicon() -> bool:
    """Same as _detect_metal but kept separate for clarity in HardwareProfile."""
    return _detect_metal()


# ── Whisper backend choice ────────────────────────────────────────────────

def _choose_whisper_backend(hw: HardwareProfile) -> WhisperBackendName:
    """Decide which Whisper backend to load at startup.

    Priority:
      1. ``mlx_whisper`` on Apple Silicon (uses the Neural Engine via Metal)
      2. ``faster_whisper`` everywhere else (CUDA / CPU)
    """
    if hw.is_apple_silicon:
        # Only use mlx-whisper if it's actually installed. The user can
        # install it with `pip install mlx-whisper` on macOS. If they don't,
        # we fall back to faster-whisper which still works on Metal via CPU.
        try:
            import mlx_whisper  # type: ignore  # noqa: F401
            return "mlx_whisper"
        except ImportError:
            logger.warning("mlx_whisper_not_installed_falling_back",
                          hint="pip install mlx-whisper for best performance on Apple Silicon")
            return "faster_whisper"
    return "faster_whisper"


# ── ffmpeg encoder choice ─────────────────────────────────────────────────

def _choose_ffmpeg_encoder(hw: HardwareProfile) -> str:
    """Return the best available ffmpeg encoder for the current platform.

    Priority:
      - macOS:         h264_videotoolbox > libx264
      - Windows/Linux: h264_nvenc (NVIDIA) > h264_qsv (Intel) > libx264
    """
    if hw.os == "darwin":
        if hw.has_ffmpeg_videotoolbox:
            return "h264_videotoolbox"
    else:
        if hw.has_ffmpeg_nvenc:
            return "h264_nvenc"
        if hw.has_ffmpeg_qsv:
            return "h264_qsv"
    return "libx264"


# ── Main entry point ──────────────────────────────────────────────────────

_cached_profile: HardwareProfile | None = None


def detect_hardware(force: bool = False) -> HardwareProfile:
    """Detect and return the hardware profile for this machine.

    The result is cached after the first call. Pass ``force=True`` to
    re-detect (useful in tests).
    """
    global _cached_profile
    if _cached_profile is not None and not force:
        return _cached_profile

    sys_os = platform.system().lower()
    if sys_os not in ("windows", "linux", "darwin"):
        logger.warning("unknown_os", os=sys_os)
        sys_os = "linux"  # safe default

    is_apple_silicon = _detect_apple_silicon() if sys_os == "darwin" else False
    has_cuda = _detect_cuda()
    has_metal = is_apple_silicon  # Metal is only relevant on Apple Silicon

    ffmpeg_path = find_ffmpeg()
    if not ffmpeg_path:
        # This will be a hard error later when we try to render. We log
        # a clear warning and let the rest of the code handle the missing
        # binary gracefully.
        logger.error("ffmpeg_not_found", hint="Install ffmpeg and add to PATH")
        has_nvenc = has_videotoolbox = has_qsv = False
    else:
        has_nvenc = _ffmpeg_has_encoder(ffmpeg_path, "h264_nvenc")
        has_videotoolbox = _ffmpeg_has_encoder(ffmpeg_path, "h264_videotoolbox")
        has_qsv = _ffmpeg_has_encoder(ffmpeg_path, "h264_qsv")

    # Pick compute backend
    if has_cuda:
        compute_backend: ComputeBackend = "cuda"
    elif is_apple_silicon and has_metal:
        compute_backend = "metal"
    else:
        compute_backend = "cpu"

    profile = HardwareProfile(
        os=sys_os,
        is_apple_silicon=is_apple_silicon,
        has_cuda=has_cuda,
        has_metal=has_metal,
        has_ffmpeg_nvenc=has_nvenc,
        has_ffmpeg_videotoolbox=has_videotoolbox,
        has_ffmpeg_qsv=has_qsv,
        compute_backend=compute_backend,
        # whisper_backend filled in below (depends on platform + is_apple_silicon)
        whisper_backend="faster_whisper",  # placeholder, replaced next
        ffmpeg_encoder="libx264",           # placeholder, replaced next
        ffmpeg_path=ffmpeg_path or "",
    )

    # Now that the profile exists, we can compute the dependent fields
    whisper = _choose_whisper_backend(profile)
    encoder = _choose_ffmpeg_encoder(profile)

    profile = HardwareProfile(
        **{**profile.__dict__, "whisper_backend": whisper, "ffmpeg_encoder": encoder}
    )

    logger.info("hardware_detected", summary=profile.summary())
    _cached_profile = profile
    return profile


def reset_cache() -> None:
    """Clear the cached profile (for tests)."""
    global _cached_profile
    _cached_profile = None
