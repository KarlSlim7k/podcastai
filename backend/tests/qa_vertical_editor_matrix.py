"""QA matrix for the vertical editor.

Covers every visible editor option family at least once:
- layouts: split, centered, fill, auto
- backgrounds: blur, solid, gradient, zoom
- subtitles: standard, karaoke, neon, mrbeast, hormozi, tiktok_classic
- title on/off
- validates output dimensions with ffprobe

Run: cd backend && .venv/Scripts/python.exe tests/qa_vertical_editor_matrix.py
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.vertical_editor_service import RenderOptions, WordTimestamp, render_vertical
from app.services.audio_extractor import audio_extractor

ROOT = Path(__file__).resolve().parents[1]
CLIP = ROOT / "data" / "clips" / "5" / "clip_9.mp4"
OUTDIR = ROOT / "data" / "clips" / "5" / "vertical" / "qa_matrix"

WORDS = [
    WordTimestamp(0.10, 0.45, "Esto"),
    WordTimestamp(0.50, 0.95, "es"),
    WordTimestamp(1.00, 1.45, "una"),
    WordTimestamp(1.50, 2.05, "prueba"),
    WordTimestamp(2.10, 2.65, "visual"),
    WordTimestamp(2.70, 3.25, "del"),
    WordTimestamp(3.30, 3.95, "editor"),
]

CASES = [
    ("split_blur_standard",       dict(layout="split",    bg_style="blur",     sub_style="standard",       add_title=True)),
    ("centered_solid_karaoke",    dict(layout="centered", bg_style="solid",    sub_style="karaoke",        add_title=False)),
    ("fill_gradient_neon",        dict(layout="fill",     bg_style="gradient", sub_style="neon",           add_title=True)),
    ("auto_zoom_mrbeast",         dict(layout="auto",     bg_style="zoom",     sub_style="mrbeast",        add_title=True)),
    ("split_solid_hormozi",       dict(layout="split",    bg_style="solid",    sub_style="hormozi",        add_title=True)),
    ("centered_gradient_tiktok",  dict(layout="centered", bg_style="gradient", sub_style="tiktok_classic", add_title=True)),
]


def ffprobe_dims(path: Path) -> tuple[int, int]:
    cmd = [
        audio_extractor._ffmpeg.replace("ffmpeg", "ffprobe"),
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0:s=x",
        str(path),
    ]
    out = subprocess.check_output(cmd, text=True).strip()
    w, h = out.split("x")
    return int(w), int(h)


async def main() -> int:
    if not CLIP.exists():
        print(f"Missing clip: {CLIP}")
        return 1
    OUTDIR.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    for name, opts in CASES:
        out = OUTDIR / f"{name}.mp4"
        if out.exists():
            out.unlink()
        options = RenderOptions(
            **opts,
            bg_color="#0f172a",
            bg_color2="#7c3aed",
            sub_color="#ffffff",
            sub_highlight="#ffd700",
            sub_outline="#000000",
            sub_size=64,
            sub_position=220,
            title_text=f"QA {name}",
            title_color="#ffffff",
            title_size=64,
        )
        print(f"\n=== {name} ===")
        print(f"layout={options.layout} bg={options.bg_style} sub={options.sub_style} title={options.add_title}")
        try:
            result = await render_vertical(
                source_video=CLIP,
                source_audio=None,
                output_path=out,
                words=WORDS,
                options=options,
                title_text=f"QA {name}",
                duration=None,
            )
            w, h = ffprobe_dims(out)
            mb = out.stat().st_size / 1024 / 1024
            print(f"OK file={mb:.2f}MB dims={w}x{h} processing={result.processing_time:.1f}s")
            if (w, h) != (1080, 1920):
                failures.append(f"{name}: expected 1080x1920, got {w}x{h}")
        except Exception as e:
            print(f"FAIL {name}: {e}")
            failures.append(f"{name}: {e}")
    print("\n=== SUMMARY ===")
    if failures:
        for f in failures:
            print("FAIL", f)
        return 1
    print(f"PASS {len(CASES)}/{len(CASES)} cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
