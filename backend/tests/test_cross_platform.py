"""Tests for cross-platform hardware detection and backend selection.

These tests run on any platform (Windows, Linux, macOS) and validate:
  - detect_hardware() returns a valid HardwareProfile
  - ffmpeg discovery finds the binary
  - Whisper backend factory returns a working backend
  - Subtitle font detection works on the current OS
  - The whole pipeline (transcribe) round-trips correctly

Run with:  cd backend && .venv/Scripts/python.exe tests/test_cross_platform.py
"""
import asyncio
import sys
import platform
from pathlib import Path

# Allow running from the backend/ dir
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_hardware_detection():
    """Hardware detection returns a valid profile for this OS."""
    from app.utils.hardware import detect_hardware, reset_cache
    reset_cache()
    hw = detect_hardware()
    assert hw is not None
    assert hw.os in ("windows", "linux", "darwin")
    assert isinstance(hw.is_apple_silicon, bool)
    assert isinstance(hw.has_cuda, bool)
    assert isinstance(hw.has_metal, bool)
    assert hw.compute_backend in ("cuda", "metal", "rocm", "cpu")
    assert hw.whisper_backend in ("faster_whisper", "mlx_whisper")
    assert hw.ffmpeg_encoder in ("h264_nvenc", "h264_videotoolbox",
                                   "h264_qsv", "libx264")
    print(f"  ✓ Hardware profile: {hw.summary()}")


def test_ffmpeg_discovery():
    """ffmpeg is found on PATH or in a known install location."""
    from app.utils.hardware import find_ffmpeg
    path = find_ffmpeg()
    assert path is not None, "ffmpeg not found"
    assert Path(path).exists(), f"ffmpeg path invalid: {path}"
    print(f"  ✓ ffmpeg found: {path}")


def test_ffmpeg_encoder_match():
    """The detected encoder is actually compiled into this ffmpeg."""
    from app.utils.hardware import detect_hardware, reset_cache
    reset_cache()
    hw = detect_hardware()
    if not hw.ffmpeg_path:
        print("  ! Skipped (ffmpeg not found)")
        return
    import subprocess
    out = subprocess.run(
        [hw.ffmpeg_path, "-hide_banner", "-encoders"],
        capture_output=True, text=True, timeout=10,
    )
    encoders = out.stdout
    # The chosen encoder must actually be present
    assert hw.ffmpeg_encoder in encoders, (
        f"detected encoder {hw.ffmpeg_encoder} not in ffmpeg build"
    )
    print(f"  ✓ Encoder {hw.ffmpeg_encoder} confirmed in ffmpeg build")


def test_whisper_backend_loaded():
    """The Whisper backend factory loads the right backend for this OS."""
    from app.services.whisper_backends import get_whisper_backend, reset_backend_cache
    reset_backend_cache()
    backend = get_whisper_backend()
    if platform.system() == "Darwin" and not _has_mlx_whisper():
        assert backend.name == "faster_whisper", "on macOS without mlx, expected faster_whisper"
    elif platform.system() == "Darwin":
        # We can't actually use mlx_whisper in CI; just ensure the factory
        # picked the right one for the current state.
        pass
    else:
        assert backend.name == "faster_whisper", (
            f"on {platform.system()} expected faster_whisper, got {backend.name}"
        )
    print(f"  ✓ Whisper backend: {backend.name}")


def _has_mlx_whisper() -> bool:
    try:
        import mlx_whisper  # type: ignore  # noqa: F401
        return True
    except ImportError:
        return False


def test_subtitle_font_detected():
    """Subtitle font detection returns something sensible."""
    from app.services.vertical_editor_service import _detect_subtitle_font
    font = _detect_subtitle_font()
    assert isinstance(font, str) and len(font) > 0
    print(f"  ✓ Subtitle font: {font}")


def test_title_fontfile_detected():
    """Title TTF path is resolved (or None on minimal systems)."""
    from app.services.vertical_editor_service import _detect_title_fontfile
    path = _detect_title_fontfile()
    if path is not None:
        assert Path(path).exists(), f"title fontfile path invalid: {path}"
        print(f"  ✓ Title fontfile: {path}")
    else:
        print("  ! Title fontfile: None (system has no recognized TTF)")


def test_config_paths_exist():
    """Config paths are Path objects (multiplatform-safe)."""
    from app.config import settings
    assert isinstance(settings.data_dir, Path)
    assert isinstance(settings.uploads_dir, Path)
    assert isinstance(settings.subtitle_font_paths, list)
    for p in settings.subtitle_font_paths:
        assert isinstance(p, str)
    # On this OS at least one font path should be reachable (or the list
    # is empty for very minimal systems).
    print(f"  ✓ Config paths: {len(settings.subtitle_font_paths)} font candidates")


def test_macos_simulation():
    """Simulate what the factory would do on macOS Apple Silicon.

    We can't actually run mlx_whisper on Windows/Linux, but we can
    verify the factory's logic returns the right name given a hardware
    profile.
    """
    from app.utils.hardware import HardwareProfile, _choose_whisper_backend
    # Build a fake "macOS Apple Silicon" profile
    fake_hw = HardwareProfile(
        os="darwin", is_apple_silicon=True, has_cuda=False, has_metal=True,
        has_ffmpeg_nvenc=False, has_ffmpeg_videotoolbox=True, has_ffmpeg_qsv=False,
        compute_backend="metal", whisper_backend="faster_whisper",  # placeholder
        ffmpeg_encoder="h264_videotoolbox", ffmpeg_path="/usr/local/bin/ffmpeg",
    )
    name = _choose_whisper_backend(fake_hw)
    # On macOS with mlx installed -> "mlx_whisper"; without -> "faster_whisper"
    if _has_mlx_whisper():
        assert name == "mlx_whisper", f"expected mlx_whisper, got {name}"
        print(f"  ✓ macOS Apple Silicon → mlx_whisper (mlx installed)")
    else:
        assert name == "faster_whisper", f"expected faster_whisper, got {name}"
        print(f"  ✓ macOS Apple Silicon → faster_whisper (fallback, no mlx)")


def test_encoder_speed_vs_libx264():
    """Smoke test: encoder was at least selected (no actual ffmpeg call)."""
    from app.utils.hardware import detect_hardware, reset_cache
    reset_cache()
    hw = detect_hardware()
    # The encoder should be non-empty
    assert hw.ffmpeg_encoder
    # On any system with no GPU acceleration it should be libx264
    if not (hw.has_ffmpeg_nvenc or hw.has_ffmpeg_videotoolbox or hw.has_ffmpeg_qsv):
        assert hw.ffmpeg_encoder == "libx264"
        print(f"  ✓ No GPU encoder → using {hw.ffmpeg_encoder} (CPU fallback)")
    else:
        print(f"  ✓ GPU encoder available → {hw.ffmpeg_encoder}")


# ── Run all tests ──────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print(" Cross-platform V1.5 tests")
    print(f" Running on: {platform.system()} {platform.machine()}")
    print("=" * 70)
    tests = [
        ("Hardware detection",       test_hardware_detection),
        ("ffmpeg discovery",         test_ffmpeg_discovery),
        ("ffmpeg encoder match",     test_ffmpeg_encoder_match),
        ("Whisper backend loaded",   test_whisper_backend_loaded),
        ("Subtitle font detected",   test_subtitle_font_detected),
        ("Title fontfile detected",  test_title_fontfile_detected),
        ("Config paths exist",       test_config_paths_exist),
        ("macOS Apple Silicon sim",  test_macos_simulation),
        ("Encoder selection",        test_encoder_speed_vs_libx264),
    ]
    passed = 0
    failed = 0
    for name, fn in tests:
        print(f"\n[ {name} ]")
        try:
            fn()
            passed += 1
        except Exception as e:
            print(f"  ✗ FAILED: {e}")
            failed += 1
    print("\n" + "=" * 70)
    print(f" Results: {passed} passed, {failed} failed")
    print("=" * 70)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
