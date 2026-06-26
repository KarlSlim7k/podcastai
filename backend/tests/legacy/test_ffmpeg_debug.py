"""Compare two ffmpeg invocations to see why one has 2 video streams."""
import subprocess
import os
import shutil

# Clean previous test outputs
for f in os.listdir("data/clips/5/vertical"):
    if f.startswith("test_") and f.endswith(".mp4"):
        os.unlink(f"data/clips/5/vertical/{f}")

# Test 1: relative path (what the script does, since cwd = output_path.parent)
print("=== Test 1: ffmpeg from data/clips/5/vertical/ with relative input ===")
cmd1 = [
    "ffmpeg", "-y", "-loglevel", "warning",
    "-i", "../clip_1.mp4",  # relative from cwd
    "-filter_complex",
    "[0:v]scale=-1:1920:flags=lanczos,crop=1080:1920:(in_w-1080)/2:0[v_main];"
    "[v_main]ass=test_print.ass[v_sub];"
    "[v_sub]drawtext=text='Test':fontcolor=0xFFFFFF:fontsize=72:"
    "x=(w-text_w)/2:y=140:box=1:boxcolor=black@0.55:boxborderw=24[v_out]",
    "-map", "[v_out]",
    "-map", "0:a:0?",
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
    "-c:a", "aac", "-b:a", "192k",
    "-movflags", "+faststart",
    "-shortest",
    "-dn",
    "test_t1.mp4",
]
# Make sure test_print.ass exists
if not os.path.exists("data/clips/5/vertical/test_print.ass"):
    with open("data/clips/5/vertical/test_print.ass", "w") as f:
        f.write("[Script Info]\nScriptType: v4.00+\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize\nStyle: Default,Arial,72\n\n[Events]\nFormat: Layer, Start, End\nDialogue: 0,0:00:00.00,0:00:01.00,,,0,0,0,,Test\n")
print("CWD: data/clips/5/vertical")
print("CMD:", " ".join(cmd1[:5]), "...")
r = subprocess.run(cmd1, capture_output=True, text=True, cwd="data/clips/5/vertical", timeout=20)
print(f"rc={r.returncode}")
if r.stderr: print("STDERR:", r.stderr[-300:])
out = "data/clips/5/vertical/test_t1.mp4"
r2 = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,width,height", "-of", "csv=p=0", out], capture_output=True, text=True)
print(f"Streams: {r2.stdout.strip()}")
print()

# Test 2: absolute path
print("=== Test 2: ffmpeg with absolute path ===")
cmd2 = cmd1.copy()
cmd2[cmd2.index("-i") + 1] = "C:/Users/karol/Documents/transcripciones/backend/data/clips/5/clip_1.mp4"
print("CMD:", " ".join(cmd2[:5]), "...")
r = subprocess.run(cmd2, capture_output=True, text=True, cwd="data/clips/5/vertical", timeout=20)
print(f"rc={r.returncode}")
if r.stderr: print("STDERR:", r.stderr[-300:])
out = "data/clips/5/vertical/test_t2.mp4"
r2 = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,width,height", "-of", "csv=p=0", out], capture_output=True, text=True)
print(f"Streams: {r2.stdout.strip()}")
print()

# Test 3: with audio file as 2nd input
print("=== Test 3: with audio file as 2nd input (this is what render_vertical does) ===")
cmd3 = [
    "ffmpeg", "-y", "-loglevel", "warning",
    "-i", "C:/Users/karol/Documents/transcripciones/backend/data/clips/5/clip_1.mp4",
    "-i", "C:/Users/karol/Documents/transcripciones/backend/data/clips/5/clip_1.mp3",
    "-filter_complex",
    "[0:v]scale=-1:1920:flags=lanczos,crop=1080:1920:(in_w-1080)/2:0[v_main];"
    "[v_main]ass=test_print.ass[v_sub];"
    "[v_sub]drawtext=text='Test':fontcolor=0xFFFFFF:fontsize=72:"
    "x=(w-text_w)/2:y=140:box=1:boxcolor=black@0.55:boxborderw=24[v_out]",
    "-map", "[v_out]",
    "-map", "1:a:0?",
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
    "-c:a", "aac", "-b:a", "192k",
    "-movflags", "+faststart",
    "-shortest",
    "-dn",
    "test_t3.mp4",
]
r = subprocess.run(cmd3, capture_output=True, text=True, cwd="data/clips/5/vertical", timeout=20)
print(f"rc={r.returncode}")
if r.stderr: print("STDERR:", r.stderr[-300:])
out = "data/clips/5/vertical/test_t3.mp4"
r2 = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,width,height", "-of", "csv=p=0", out], capture_output=True, text=True)
print(f"Streams: {r2.stdout.strip()}")
