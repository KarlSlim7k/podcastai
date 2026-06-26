"""Phase 6 test: render with watermark overlay using a real PNG."""
import asyncio, sys, json
from pathlib import Path
sys.path.insert(0, ".")
from PIL import Image, ImageDraw, ImageFont
from app.database import AsyncSessionLocal
from app.services.vertical_editor_service import render_vertical, RenderOptions, extract_words_for_clip
from app.models.project import Project, Clip
from sqlalchemy import select
from sqlalchemy.orm import selectinload


async def main():
    # 1) Create a watermark PNG (200x200 transparent with text "TEST")
    wm_dir = Path("data/watermarks")
    wm_dir.mkdir(parents=True, exist_ok=True)
    wm_path = wm_dir / "test_logo.png"
    img = Image.new("RGBA", (300, 100), (0, 0, 0, 0))  # transparent
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 48)
    except Exception:
        font = ImageFont.load_default()
    draw.text((10, 20), "KAROL", fill=(255, 215, 0, 255), font=font)
    img.save(wm_path)
    print(f"Created watermark: {wm_path} ({wm_path.stat().st_size} bytes)")

    # 2) Render a clip with the watermark
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Clip).where(Clip.id == 9, Clip.project_id == 5))
        clip = r.scalar_one()
        r = await db.execute(
            select(Project).where(Project.id == 5)
            .options(selectinload(Project.transcription))
        )
        proj = r.scalar_one()
        words = extract_words_for_clip(proj.transcription.segments, float(clip.start), float(clip.end))
        out = Path(f"data/clips/5/vertical/phase6_watermark_test.mp4")
        out.parent.mkdir(parents=True, exist_ok=True)
        opts = RenderOptions(
            layout="split", bg_style="blur", sub_style="karaoke",
            add_title=True, title_text="Watermark test",
            watermark_path=str(wm_path.resolve()),
            watermark_position="bottom_right",
            watermark_opacity=0.85,
        )
        r = await render_vertical(
            source_video=Path(clip.video_clip_path),
            source_audio=Path(clip.audio_clip_path),
            output_path=out, words=words, options=opts,
            duration=float(clip.end) - float(clip.start),
        )
        print(f"Result: {r.file_size/1024/1024:.2f}MB {r.width}x{r.height} {r.duration:.1f}s ({r.processing_time:.1f}s)")

    # 3) Extract a frame to confirm the watermark is visible
    import subprocess
    frame_path = Path("data/clips/5/vertical/phase6_watermark_frame.png")
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-ss", "5",
         "-i", str(out), "-frames:v", "1", str(frame_path)],
        check=True,
    )
    print(f"Frame extracted: {frame_path} ({frame_path.stat().st_size} bytes)")

asyncio.run(main())
