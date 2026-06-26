"""Debug: render with fill + gradient to see why it's 1920x1080 instead of 1080x1920."""
import asyncio, sys
sys.path.insert(0, ".")
from app.services.vertical_editor_service import (
    render_vertical, RenderOptions, extract_words_for_clip, _build_simple_filter,
)
import sqlite3, json
from pathlib import Path

db = sqlite3.connect("data/app.db")
db.row_factory = sqlite3.Row
clip = db.execute("SELECT id, start, end, title, audio_clip_path, video_clip_path "
                   "FROM clips WHERE project_id=5 AND id=15").fetchone()
segs_json = db.execute("SELECT segments FROM transcriptions WHERE project_id=5").fetchone()[0]
db.close()

words = extract_words_for_clip(json.loads(segs_json), float(clip["start"]), float(clip["end"]))

# Print the filter that _build_simple_filter generates for fill + gradient
opts = RenderOptions(layout="fill", bg_style="gradient", sub_style="neon",
                    add_title=True, title_text="Test")
ass_path = Path("data/clips/5/vertical/test_fill.ass")
ass_path.parent.mkdir(parents=True, exist_ok=True)
ass_path.write_text("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,Arial,72,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,40,40,200,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,Test\n")
print("=" * 60)
print("FILTER (fill + gradient + neon):")
print("=" * 60)
f = _build_simple_filter(opts, ass_path.name, has_subs=True)
print(f)
print("=" * 60)
print("Now testing with actual render...")
result = asyncio.run(render_vertical(
    source_video=Path(clip["video_clip_path"]),
    source_audio=Path(clip["audio_clip_path"]),
    output_path=Path("data/clips/5/vertical/test_fill_grad.mp4"),
    words=words,
    options=opts,
))
import subprocess
info = subprocess.run(
    ["ffprobe", "-v", "error", "-show_entries", "format=duration,size:stream=codec_name,width,height",
     "-of", "csv=p=0", "data/clips/5/vertical/test_fill_grad.mp4"],
    capture_output=True, text=True,
)
print(f"Result: {info.stdout}")
