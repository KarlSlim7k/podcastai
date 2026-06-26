"""End-to-end tests for Phase 14 (B-roll placements wired to the render).

These tests verify that a B-roll placement list passed to RenderOptions
actually causes the b-roll image to be composited onto the MP4 between
[start, end] seconds, while leaving the rest of the video untouched.

We don't talk to Pexels at all in the test: _download_broll() is monkey-patched
to copy a local PNG into the cache dir, so the test is fully offline and
deterministic. What we're really testing is the ffmpeg filter graph, the
enable='between(t,start,end)' windowing, and the round-trip persistence
through RenderOptions → ffmpeg invocation.

Run with:  cd backend && .venv/Scripts/python.exe tests/e2e/test_phase14_broll_render.py
"""
import asyncio
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Allow running from the backend/ dir
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from PIL import Image, ImageDraw, ImageFont  # type: ignore

from app.config import settings
from app.database import AsyncSessionLocal
from app.services import vertical_editor_service
from app.services.vertical_editor_service import (
    render_vertical, RenderOptions, extract_words_for_clip,
)
from app.models.project import Project, Clip
from app.models.schemas import BrollPlacement
from sqlalchemy import select
from sqlalchemy.orm import selectinload


PROJECT_ID = 5
CLIP_ID = 9  # must exist and have an extracted video_clip_path + audio_clip_path

# Two visually distinct PNGs: a red "TEST-RED" and a blue "TEST-BLUE".
# We render twice — once with no b-roll, once with the red b-roll at
# t=1.0..2.0s — and compare a frame in the window (must be red) vs
# outside the window (must NOT be red).
RED_PNG = Path("data/test_assets/broll_red.png")
BLUE_PNG = Path("data/test_assets/broll_blue.png")


def make_test_broll(path: Path, label: str, rgb: tuple[int, int, int]) -> Path:
    """Create a 1080x1920 PNG with a solid color and a label. Returns abs path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (1080, 1920), rgb)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 96)
    except Exception:
        font = ImageFont.load_default()
    draw.text((100, 900), label, fill=(255, 255, 255), font=font)
    img.save(path)
    return path.resolve()


async def fake_download_broll(url: str, cache_dir: Path) -> Path | None:
    """Test replacement for _download_broll — copies a local PNG to the cache.

    The 'url' is a sentinel like 'local://red' or 'local://blue' that we map
    to the appropriate test asset. This keeps the test offline and avoids
    any httpx/Pexels dependency.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    sentinel_map = {
        "local://red": RED_PNG,
        "local://blue": BLUE_PNG,
    }
    src = sentinel_map.get(url)
    if src is None or not src.exists():
        return None
    import hashlib
    key = hashlib.sha1(url.encode()).hexdigest()[:16]
    dest = cache_dir / f"{key}.png"
    shutil.copy(src, dest)
    return dest


def extract_frame(mp4: Path, t_seconds: float, out_png: Path) -> None:
    """Extract a single frame from an MP4 at time t using ffmpeg."""
    out_png.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", f"{t_seconds:.3f}",
        "-i", str(mp4),
        "-frames:v", "1",
        str(out_png),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 0, f"ffmpeg extract failed: {r.stderr}"


def average_color(png: Path) -> tuple[int, int, int]:
    """Return the (R, G, B) average of a PNG, downsampled to 32x32."""
    img = Image.open(png).convert("RGB").resize((32, 32))
    pixels = list(img.getdata())
    n = len(pixels)
    r = sum(p[0] for p in pixels) // n
    g = sum(p[1] for p in pixels) // n
    b = sum(p[2] for p in pixels) // n
    return (r, g, b)


async def get_clip_and_words() -> tuple[Clip, list]:
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(Clip).where(Clip.id == CLIP_ID, Clip.project_id == PROJECT_ID)
        )
        clip = r.scalar_one()
        r = await db.execute(
            select(Project)
            .where(Project.id == PROJECT_ID)
            .options(selectinload(Project.transcription))
        )
        proj = r.scalar_one()
        words = extract_words_for_clip(
            proj.transcription.segments,
            float(clip.start),
            float(clip.end),
        )
        return clip, words


async def test_broll_placement_schema_roundtrip():
    """BrollPlacement accepts the documented fields and round-trips through model_dump."""
    bp = BrollPlacement(url="local://red", start=1.5, end=3.0, opacity=0.8)
    d = bp.model_dump()
    assert d == {"url": "local://red", "start": 1.5, "end": 3.0, "opacity": 0.8}
    print("  ✓ BrollPlacement round-trips through model_dump()")


async def test_render_without_broll_unchanged():
    """Baseline: render with no b-rolls produces a normal MP4 (control case)."""
    make_test_broll(RED_PNG, "RED", (200, 30, 30))
    make_test_broll(BLUE_PNG, "BLUE", (30, 30, 200))
    clip, words = await get_clip_and_words()
    out = Path(f"data/clips/{PROJECT_ID}/vertical/test_phase14_no_broll.mp4")
    if out.exists():
        out.unlink()

    # Monkey-patch the network helper so even a non-empty placements list
    # wouldn't touch the internet — but we render with empty list here.
    vertical_editor_service._download_broll = fake_download_broll  # type: ignore[assignment]

    opts = RenderOptions(
        layout="split", bg_style="blur", sub_style="karaoke",
        add_title=True, title_text="phase14 baseline", title_color="#FFFFFF", title_size=72,
    )
    t0 = time.time()
    result = await render_vertical(
        source_video=Path(clip.video_clip_path or clip.audio_clip_path),
        source_audio=Path(clip.audio_clip_path),
        output_path=out, words=words, options=opts,
        duration=float(clip.end) - float(clip.start),
    )
    elapsed = time.time() - t0
    assert out.exists() and out.stat().st_size > 1000, f"Render produced empty/tiny file: {out.stat().st_size if out.exists() else 0}"
    assert result.width == 1080 and result.height == 1920
    print(f"  ✓ Baseline render: {out.stat().st_size / 1024 / 1024:.2f} MB in {elapsed:.1f}s ({result.width}x{result.height})")


async def test_render_with_broll_changes_pixel_in_window():
    """Render with a b-roll placement at t=1.0..2.0s. A frame at t=1.5s must be
    red-tinted (the b-roll dominates); a frame at t=0.2s must be NOT red
    (outside the window — the b-roll is invisible there)."""
    clip, words = await get_clip_and_words()
    out = Path(f"data/clips/{PROJECT_ID}/vertical/test_phase14_with_broll.mp4")
    if out.exists():
        out.unlink()
    vertical_editor_service._download_broll = fake_download_broll  # type: ignore[assignment]

    opts = RenderOptions(
        layout="split", bg_style="blur", sub_style="karaoke",
        add_title=True, title_text="phase14 broll", title_color="#FFFFFF", title_size=72,
        broll_placements=[BrollPlacement(url="local://red", start=1.0, end=2.0, opacity=1.0)],
    )
    t0 = time.time()
    result = await render_vertical(
        source_video=Path(clip.video_clip_path or clip.audio_clip_path),
        source_audio=Path(clip.audio_clip_path),
        output_path=out, words=words, options=opts,
        duration=float(clip.end) - float(clip.start),
    )
    elapsed = time.time() - t0
    assert out.exists() and out.stat().st_size > 1000

    # Frame at t=0.2s — outside the [1.0, 2.0] window. Should NOT be red-dominant.
    frame_outside = Path("data/test_assets/frame_outside.png")
    extract_frame(out, 0.2, frame_outside)
    rgb_outside = average_color(frame_outside)
    # Frame at t=1.5s — INSIDE the window. Should be red-dominant.
    frame_inside = Path("data/test_assets/frame_inside.png")
    extract_frame(out, 1.5, frame_inside)
    rgb_inside = average_color(frame_inside)

    print(f"  ✓ B-roll render: {out.stat().st_size / 1024 / 1024:.2f} MB in {elapsed:.1f}s")
    print(f"    frame@t=0.2s (outside window) avg RGB = {rgb_outside}")
    print(f"    frame@t=1.5s (inside window)  avg RGB = {rgb_inside}")

    # The red channel inside the window must be much larger than outside.
    # We give it a generous threshold because of the blurred background and
    # the subtitle text overlay — the b-roll just has to DOMINATE noticeably.
    r_inside, g_inside, b_inside = rgb_inside
    r_outside, g_outside, b_outside = rgb_outside
    assert r_inside > r_outside + 30, (
        f"Expected red channel to dominate inside window, "
        f"got r_inside={r_inside} vs r_outside={r_outside}"
    )
    # And the outside frame shouldn't be red-dominant either
    assert r_outside < 150, (
        f"Expected outside window to NOT be red, got {rgb_outside}"
    )
    print(f"  ✓ B-roll windowing works: r_inside ({r_inside}) >> r_outside ({r_outside})")


async def test_failed_broll_download_does_not_break_render():
    """If _download_broll returns None (download failed), the render must
    still complete successfully and the placements list is silently dropped."""
    clip, words = await get_clip_and_words()
    out = Path(f"data/clips/{PROJECT_ID}/vertical/test_phase14_broken_broll.mp4")
    if out.exists():
        out.unlink()

    async def always_fails(url: str, cache_dir: Path) -> Path | None:
        return None  # every download fails
    vertical_editor_service._download_broll = always_fails  # type: ignore[assignment]

    opts = RenderOptions(
        layout="split", bg_style="blur", sub_style="karaoke",
        add_title=True, title_text="phase14 broken", title_color="#FFFFFF", title_size=72,
        broll_placements=[BrollPlacement(url="http://invalid.example/never.jpg", start=0.5, end=1.5)],
    )
    result = await render_vertical(
        source_video=Path(clip.video_clip_path or clip.audio_clip_path),
        source_audio=Path(clip.audio_clip_path),
        output_path=out, words=words, options=opts,
        duration=float(clip.end) - float(clip.start),
    )
    assert out.exists() and out.stat().st_size > 1000
    print(f"  ✓ Render survives broken b-roll URL: {out.stat().st_size / 1024 / 1024:.2f} MB")


async def main():
    print("=" * 60)
    print("Phase 14 — B-roll placements wired to render")
    print("=" * 60)
    await test_broll_placement_schema_roundtrip()
    await test_render_without_broll_unchanged()
    await test_render_with_broll_changes_pixel_in_window()
    await test_failed_broll_download_does_not_break_render()
    print("=" * 60)
    print("All Phase 14 tests passed ✓")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
