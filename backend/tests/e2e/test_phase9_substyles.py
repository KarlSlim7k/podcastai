"""End-to-end tests for Phase 9 — OpusClips-style subtitle styles.

These tests:
  1. Verify each of the 5 sub styles generates a valid ASS Style line
  2. Verify the word-by-word tags are correct per style
  3. Render a real clip with each of the 3 NEW styles (mrbeast, hormozi, tiktok_classic)
  4. Verify the output MP4s exist and are valid

Run with:  cd backend && .venv/Scripts/python.exe tests/e2e/test_phase9_substyles.py
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.database import AsyncSessionLocal
from app.services.vertical_editor_service import (
    render_vertical, RenderOptions, extract_words_for_clip,
    build_ass_karaoke_from_words, build_ass_style_line, _STYLE_LINE_BUILDERS,
    WordTimestamp,
)
from app.models.project import Project, Clip
from sqlalchemy import select
from sqlalchemy.orm import selectinload


# ── Unit tests on the ASS builder ────────────────────────────────────────

def test_all_5_styles_have_builders():
    expected = {"standard", "neon", "mrbeast", "hormozi", "tiktok_classic"}
    actual = set(_STYLE_LINE_BUILDERS.keys())
    missing = expected - actual
    assert not missing, f"Missing style builders: {missing}"
    print(f"  ✓ All 5 styles registered: {sorted(actual)}")


def test_style_lines_are_different():
    """Each style should produce a different ASS Style line."""
    lines = {}
    for style in _STYLE_LINE_BUILDERS:
        lines[style] = build_ass_style_line(style, 64, "#FFFFFF", "#000000", 200)
    unique = set(lines.values())
    assert len(unique) == len(lines), f"Some styles produce identical lines: {lines}"
    print(f"  ✓ All 5 styles produce unique Style lines")
    for style, line in lines.items():
        # Show the key params: fontname, fontsize, primary, outline, BorderStyle, Outline, Shadow
        parts = line.replace("Style: Default,", "").split(",")
        primary, secondary, outline, _back, _bold, _italic, _ul, _so, _sx, _sy, _sp, _ag, bs, ow, sh = parts[2:17]
        print(f"    {style:18} primary={primary} secondary={secondary} outline={outline} (border={bs} ow={ow} sh={sh})")


def test_word_tags_per_style():
    """The word-active and word-dim tags should be different per style."""
    words = [
        WordTimestamp(word='Hola', start=0.0, end=0.4),
        WordTimestamp(word='mundo', start=0.4, end=0.8),
    ]
    for style in ["karaoke", "mrbeast", "hormozi", "tiktok_classic", "neon"]:
        ass = build_ass_karaoke_from_words(
            words, chunk_size=2, sub_style=style,
            text_color="#FFFFFF", highlight_color="#FFD700",
            outline_color="#000000", font_size=64, bottom_margin=200, clip_offset=0.0,
        )
        first_dialogue = next((l for l in ass.split("\n") if l.startswith("Dialogue:")), "")
        # mrbeast: must contain \fscx130 (130% scale)
        if style == "mrbeast":
            assert "\\fscx130" in first_dialogue, f"mrbeast missing 130% scale: {first_dialogue}"
            assert "000000FF" in first_dialogue, f"mrbeast missing red color: {first_dialogue}"
        elif style == "hormozi":
            assert "\\fscx115" in first_dialogue, f"hormozi missing 115% scale: {first_dialogue}"
        elif style == "tiktok_classic":
            assert "0000FFFF" in first_dialogue, f"tiktok_classic missing yellow: {first_dialogue}"
        elif style == "neon":
            assert "\\fscx110" in first_dialogue, f"neon missing 110% scale: {first_dialogue}"
        elif style == "karaoke":
            # Plain bold only
            assert "{\\b1}" in first_dialogue
        print(f"  ✓ {style:18} active-word tag correct")


# ── Render E2E with real clip ────────────────────────────────────────────

async def render_with_style(style: str, output_path: Path) -> dict:
    async with AsyncSessionLocal() as db:
        r = await db.execute(
            select(Clip).where(Clip.id == 9, Clip.project_id == 5)
        )
        clip = r.scalar_one()
        r = await db.execute(
            select(Project).where(Project.id == 5).options(selectinload(Project.transcription))
        )
        proj = r.scalar_one()
        words = extract_words_for_clip(
            proj.transcription.segments, float(clip.start), float(clip.end),
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        opts = RenderOptions(
            layout="split",
            bg_style="blur",
            sub_style=style,  # type: ignore (the Literal accepts all)
            sub_size=72,
            sub_color="#FFFFFF",
            sub_highlight="#FFD700",
            sub_outline="#000000",
            add_title=True,
            title_text=f"Phase 9 — {style}",
        )
        t0 = time.time()
        result = await render_vertical(
            source_video=Path(clip.video_clip_path or clip.audio_clip_path),
            source_audio=Path(clip.audio_clip_path),
            output_path=output_path,
            words=words,
            options=opts,
            duration=float(clip.end) - float(clip.start),
        )
        return {
            "size_mb": result.file_size / 1024 / 1024,
            "width": result.width,
            "height": result.height,
            "duration": result.duration,
            "elapsed": time.time() - t0,
        }


async def test_render_with_each_new_style():
    out_dir = Path("data/clips/5/vertical")
    new_styles = ["mrbeast", "hormozi", "tiktok_classic"]
    results = {}
    for style in new_styles:
        out = out_dir / f"test_e2e_phase9_{style}.mp4"
        if out.exists():
            out.unlink()
        meta = await render_with_style(style, out)
        assert out.exists(), f"Output not found: {out}"
        assert out.stat().st_size > 100_000, f"Output too small: {out.stat().st_size}"
        assert meta["width"] == 1080 and meta["height"] == 1920, f"Wrong dims: {meta}"
        results[style] = meta
        print(
            f"  ✓ {style:18} → {meta['size_mb']:.2f}MB, {meta['width']}x{meta['height']}, "
            f"{meta['elapsed']:.1f}s"
        )
    return results


async def test_legacy_karaoke_still_works():
    """The original karaoke style should still render correctly (regression)."""
    out = Path("data/clips/5/vertical/test_e2e_phase9_karaoke_legacy.mp4")
    if out.exists():
        out.unlink()
    meta = await render_with_style("karaoke", out)
    assert out.exists()
    assert out.stat().st_size > 100_000
    print(
        f"  ✓ karaoke (legacy) → {meta['size_mb']:.2f}MB, "
        f"{meta['width']}x{meta['height']}, {meta['elapsed']:.1f}s"
    )


# ── Runner ──────────────────────────────────────────────────────────────

async def main():
    print("=" * 70)
    print(" Phase 9 E2E tests — OpusClips-style subtitle styles")
    print("=" * 70)

    # Unit tests
    print("\n[ Unit tests ]")
    unit_tests = [
        ("All 5 styles registered",   test_all_5_styles_have_builders),
        ("Unique style lines",         test_style_lines_are_different),
        ("Word tags per style",        test_word_tags_per_style),
    ]
    passed = 0
    failed = 0
    for name, fn in unit_tests:
        print(f"\n[ {name} ]")
        try:
            fn()
            passed += 1
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"  ✗ FAILED: {e}")
            failed += 1

    # Render E2E
    print("\n[ Render E2E with each new style ]")
    try:
        await test_render_with_each_new_style()
        passed += 1
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"  ✗ FAILED: {e}")
        failed += 1

    # Regression
    print("\n[ Regression: legacy karaoke still works ]")
    try:
        await test_legacy_karaoke_still_works()
        passed += 1
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"  ✗ FAILED: {e}")
        failed += 1

    # Cleanup
    print("\n[ Cleanup ]")
    for f in Path("data/clips/5/vertical").glob("test_e2e_phase9_*.mp4"):
        f.unlink()
        # Also remove the .ass file that ffmpeg generates alongside
        ass = f.with_suffix(".ass")
        if ass.exists():
            ass.unlink()
        print(f"  ✓ removed {f.name}")
    print(f"\n{'=' * 70}\n Results: {passed} passed, {failed} failed\n{'=' * 70}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
