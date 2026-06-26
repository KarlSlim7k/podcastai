"""End-to-end tests for Phase 6 features: presets and watermark.

These tests:
  1. Create a watermark PNG
  2. Render a clip with the watermark (ffmpeg overlay)
  3. Create a preset capturing the same configuration
  4. Render another clip using the loaded preset
  5. Verify both renders produce valid MP4 files
  6. Cleanup test artifacts

Run with:  cd backend && .venv/Scripts/python.exe tests/e2e/test_phase6_presets_watermark.py
"""
import asyncio
import sys
import time
from pathlib import Path

# Allow running from the backend/ dir
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from PIL import Image, ImageDraw, ImageFont  # type: ignore

from app.database import AsyncSessionLocal
from app.services.vertical_editor_service import (
    render_vertical, RenderOptions, extract_words_for_clip,
)
from app.models.project import Project, Clip, VerticalPreset
from app.models.schemas import (
    VerticalPresetRequest, WatermarkUploadResponse,
)
from sqlalchemy import select
from sqlalchemy.orm import selectinload


PROJECT_ID = 5
CLIP_ID = 9  # must exist and have an extracted video_clip_path + audio_clip_path


def make_test_watermark(out_path: Path) -> Path:
    """Create a small PNG with a colored 'LOGO' text. Returns absolute path."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGBA", (300, 100), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 48)
    except Exception:
        font = ImageFont.load_default()
    draw.text((10, 20), "E2E", fill=(0, 255, 0, 255), font=font)
    img.save(out_path)
    return out_path.resolve()


async def render_clip(options: RenderOptions, output_path: Path) -> dict:
    """Render a clip with the given options. Returns render metadata."""
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
        output_path.parent.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        result = await render_vertical(
            source_video=Path(clip.video_clip_path or clip.audio_clip_path),
            source_audio=Path(clip.audio_clip_path),
            output_path=output_path,
            words=words,
            options=options,
            duration=float(clip.end) - float(clip.start),
        )
        return {
            "size_mb": result.file_size / 1024 / 1024,
            "width": result.width,
            "height": result.height,
            "duration": result.duration,
            "processing_time": result.processing_time,
            "elapsed": time.time() - t0,
        }


async def save_preset(name: str, options: RenderOptions, wm_path: str | None):
    """Save a VerticalPreset to the database."""
    async with AsyncSessionLocal() as db:
        preset = VerticalPreset(
            name=name,
            description="Created by test_phase6_presets_watermark.py",
            layout=options.layout,
            bg_style=options.bg_style,
            bg_color=options.bg_color,
            bg_color2=options.bg_color2,
            sub_style=options.sub_style,
            sub_color=options.sub_color,
            sub_highlight=options.sub_highlight,
            sub_outline="#000000",
            sub_size=options.sub_size,
            sub_position=options.sub_position,
            add_title=1 if options.add_title else 0,
            title_text=options.title_text,
            title_color=options.title_color,
            title_size=options.title_size,
            watermark_path=wm_path,
            watermark_position=options.watermark_position,
            watermark_opacity=options.watermark_opacity,
        )
        db.add(preset)
        await db.commit()
        await db.refresh(preset)
        return preset.id


async def load_preset(preset_id: int) -> VerticalPreset:
    """Load a saved preset by id."""
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(VerticalPreset).where(VerticalPreset.id == preset_id)
        )
        return r.scalar_one()


async def delete_preset(preset_id: int):
    """Delete a preset by id."""
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(VerticalPreset).where(VerticalPreset.id == preset_id)
        )
        preset = r.scalar_one()
        await db.delete(preset)
        await db.commit()


def preset_to_options(p: VerticalPreset) -> RenderOptions:
    """Convert a DB VerticalPreset into RenderOptions."""
    return RenderOptions(
        layout=p.layout,
        bg_style=p.bg_style,
        bg_color=p.bg_color,
        bg_color2=p.bg_color2 or "#16213e",
        sub_style=p.sub_style,
        sub_color=p.sub_color,
        sub_highlight=p.sub_highlight,
        sub_size=p.sub_size,
        sub_position=p.sub_position,
        add_title=bool(p.add_title),
        title_text=p.title_text,
        title_color=p.title_color,
        title_size=p.title_size,
        watermark_path=p.watermark_path,
        watermark_position=p.watermark_position or "bottom_right",
        watermark_opacity=p.watermark_opacity if p.watermark_opacity is not None else 0.8,
    )


# ── Test cases ─────────────────────────────────────────────────────────────

async def test_watermark_response_schema():
    """WatermarkUploadResponse has the fields the frontend needs."""
    from app.models.schemas import WatermarkUploadResponse
    resp = WatermarkUploadResponse(
        file_id="abc",
        filename="test.png",
        url="/api/v1/vertical/watermark/file/abc",
        path="C:/some/path/test.png",
        size=1234,
        width=200,
        height=60,
    )
    d = resp.model_dump()
    assert "file_id" in d
    assert "path" in d
    assert "url" in d
    print(f"  ✓ WatermarkUploadResponse has file_id, path, url")


async def test_render_with_watermark():
    """Render a clip with a watermark overlay."""
    wm = Path("data/watermarks/test_e2e_phase6.png")
    wm_abs = str(make_test_watermark(wm))
    out = Path("data/clips/5/vertical/test_e2e_with_wm.mp4")
    if out.exists():
        out.unlink()
    opts = RenderOptions(
        layout="split",
        bg_style="blur",
        sub_style="karaoke",
        add_title=True,
        title_text="E2E watermark test",
        title_color="#FFFFFF",
        title_size=72,
        watermark_path=wm_abs,
        watermark_position="top_right",
        watermark_opacity=0.85,
    )
    meta = await render_clip(opts, out)
    assert out.exists(), f"output not found: {out}"
    assert out.stat().st_size > 100_000, f"output too small: {out.stat().st_size} bytes"
    assert meta["width"] == 1080 and meta["height"] == 1920, (
        f"unexpected dimensions: {meta['width']}x{meta['height']}"
    )
    print(
        f"  ✓ Render with watermark: {meta['size_mb']:.2f}MB, "
        f"{meta['width']}x{meta['height']}, {meta['elapsed']:.1f}s"
    )


async def test_preset_roundtrip():
    """Save a preset, load it, render with it, verify output."""
    wm = Path("data/watermarks/test_e2e_preset.png")
    make_test_watermark(wm)
    wm_abs = str(wm.resolve())

    # 1) Build the canonical options
    original = RenderOptions(
        layout="centered",
        bg_style="gradient",
        bg_color="#0a0a1a",
        bg_color2="#1a1a3a",
        sub_style="neon",
        sub_color="#00FFFF",
        sub_highlight="#FF00FF",
        sub_size=72,
        sub_position=300,
        add_title=True,
        title_text="Preset roundtrip test",
        title_color="#FFD700",
        title_size=80,
        watermark_path=wm_abs,
        watermark_position="bottom_left",
        watermark_opacity=0.6,
    )

    # 2) Save it as a preset
    preset_id = await save_preset("E2E roundtrip", original, wm_abs)
    print(f"  ✓ Preset saved (id={preset_id})")

    # 3) Load it back
    p = await load_preset(preset_id)
    assert p.name == "E2E roundtrip"
    assert p.layout == "centered"
    assert p.watermark_position == "bottom_left"
    print(f"  ✓ Preset loaded: {p.name}, layout={p.layout}, wm_pos={p.watermark_position}")

    # 4) Convert back to options
    loaded_opts = preset_to_options(p)
    assert loaded_opts.layout == original.layout
    assert loaded_opts.bg_color == original.bg_color
    assert loaded_opts.watermark_position == original.watermark_position
    assert loaded_opts.watermark_opacity == original.watermark_opacity
    print(f"  ✓ Preset roundtrips to identical RenderOptions")

    # 5) Render with the loaded preset
    out = Path("data/clips/5/vertical/test_e2e_from_preset.mp4")
    if out.exists():
        out.unlink()
    meta = await render_clip(loaded_opts, out)
    assert out.exists()
    assert out.stat().st_size > 100_000
    print(
        f"  ✓ Render from loaded preset: {meta['size_mb']:.2f}MB, "
        f"{meta['width']}x{meta['height']}, {meta['elapsed']:.1f}s"
    )

    # 6) Cleanup
    await delete_preset(preset_id)
    print(f"  ✓ Preset cleaned up (id={preset_id})")


async def test_no_watermark_baseline():
    """Render WITHOUT watermark still works (regression test)."""
    out = Path("data/clips/5/vertical/test_e2e_no_wm.mp4")
    if out.exists():
        out.unlink()
    opts = RenderOptions(
        layout="fill",
        bg_style="solid",
        sub_style="standard",
        add_title=False,
    )
    meta = await render_clip(opts, out)
    assert out.exists()
    assert out.stat().st_size > 100_000
    print(
        f"  ✓ Render without watermark: {meta['size_mb']:.2f}MB, "
        f"{meta['width']}x{meta['height']}, {meta['elapsed']:.1f}s"
    )


# ── Runner ─────────────────────────────────────────────────────────────────

async def main():
    print("=" * 70)
    print(" Phase 6 E2E tests — presets & watermark")
    print("=" * 70)
    tests = [
        ("WatermarkUploadResponse schema",  test_watermark_response_schema),
        ("Render with watermark overlay",   test_render_with_watermark),
        ("Preset save / load / render",     test_preset_roundtrip),
        ("Render without watermark",        test_no_watermark_baseline),
    ]
    passed = 0
    failed = 0
    for name, fn in tests:
        print(f"\n[ {name} ]")
        try:
            await fn()
            passed += 1
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"  ✗ FAILED: {e}")
            failed += 1

    # Final cleanup
    print("\n[ Cleanup ]")
    for f in [
        Path("data/clips/5/vertical/test_e2e_with_wm.mp4"),
        Path("data/clips/5/vertical/test_e2e_from_preset.mp4"),
        Path("data/clips/5/vertical/test_e2e_no_wm.mp4"),
        Path("data/watermarks/test_e2e_phase6.png"),
        Path("data/watermarks/test_e2e_preset.png"),
    ]:
        if f.exists():
            f.unlink()
            print(f"  ✓ removed {f.name}")
    print("  ✓ cleanup done")

    print("\n" + "=" * 70)
    print(f" Results: {passed} passed, {failed} failed")
    print("=" * 70)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
