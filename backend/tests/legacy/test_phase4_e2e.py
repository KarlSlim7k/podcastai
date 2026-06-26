"""Phase 4 E2E test: exercise the full vertical-editor pipeline
end-to-end via the HTTP API (same as the frontend would do).

Tests:
  1. GET /vertical/styles (returns the available presets)
  2. POST render on 3 different clips (start, middle, end of video)
  3. Poll status until completed
  4. Download the file and verify it's a valid 1080x1920 MP4
  5. DELETE the render and confirm file is gone

Each test prints PASS/FAIL so the user can see what works.
"""
import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000/api/v1"
PROJECT_ID = 5

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
WARN = "\033[93mWARN\033[0m"
RESET = "\033[0m"


def check(name, ok, detail=""):
    mark = PASS if ok else FAIL
    print(f"  [{mark}{RESET}] {name}" + (f"  -- {detail}" if detail else ""))
    return ok


def probe(path):
    """Get ffprobe stats for a video file."""
    out = subprocess.run(
        ["ffprobe", "-v", "error",
         "-show_entries", "format=duration,size:stream=codec_name,width,height",
         "-of", "csv=p=0", path],
        capture_output=True, text=True, timeout=10,
    )
    return out.stdout.strip()


def main():
    c = httpx.Client(base_url=BASE, timeout=60)
    fails = 0

    # ── 1. styles endpoint ──────────────────────────────────────────────
    print("\n[1] GET /vertical/styles")
    r = c.get("/vertical/styles")
    if not check("HTTP 200", r.status_code == 200, str(r.status_code)):
        fails += 1
        return
    styles = r.json()
    if not check("3 layouts", len(styles["layouts"]) == 3):
        fails += 1
    if not check("4 backgrounds", len(styles["backgrounds"]) == 4):
        fails += 1
    if not check("3 subtitle styles", len(styles["subtitle_styles"]) == 3):
        fails += 1
    bg_ids = {b["id"] for b in styles["backgrounds"]}
    if not check("blur+gradient+neon labels", {"blur", "gradient", "neon"}.issubset(bg_ids)):
        fails += 1

    # ── 2. list existing clips ───────────────────────────────────────────
    print("\n[2] List clips available for rendering")
    db = sqlite3.connect("data/app.db")
    db.row_factory = sqlite3.Row
    clips = list(db.execute(
        "SELECT id, start, end, title, "
        "       CASE WHEN audio_clip_path IS NOT NULL THEN 1 ELSE 0 END AS has_audio "
        "FROM clips WHERE project_id=? AND audio_clip_path IS NOT NULL "
        "ORDER BY id", (PROJECT_ID,)
    ).fetchall())
    db.close()
    # Pick 3 clips: one near the start, one in the middle, one at the end
    # (sorted by start time)
    clips_by_time = sorted(clips, key=lambda c: c["start"])
    selected = []
    if len(clips_by_time) >= 1:
        selected.append(clips_by_time[0])
    if len(clips_by_time) >= 3:
        selected.append(clips_by_time[len(clips_by_time) // 2])
    if len(clips_by_time) >= 2:
        selected.append(clips_by_time[-1])
    print(f"  {len(clips)} total clips, selected: {[c['id'] for c in selected]}")
    for c_ in selected:
        print(f"    clip {c_['id']}: {c_['start']:.0f}s-{c_['end']:.0f}s  '{c_['title'][:40]}'")

    # ── 3. POST render for each selected clip ───────────────────────────
    print("\n[3] POST render x3 (one per clip, different configs)")
    render_ids = []
    configs = [
        # (layout, bg_style, sub_style) tuples for variety
        ("split",  "blur",     "karaoke"),
        ("fill",   "gradient", "neon"),
        ("split",  "solid",    "standard"),
    ]
    for clip_, cfg in zip(selected, configs):
        layout, bg, sub = cfg
        body = {
            "layout": layout, "bg_style": bg, "sub_style": sub,
            "bg_color": "#1a1a2e", "bg_color2": "#FF6B6B",
            "sub_color": "#FFFFFF", "sub_highlight": "#FFD700",
            "sub_outline": "#000000", "sub_size": 64, "sub_position": 200,
            "add_title": True, "title_text": f"Test {layout}/{bg}/{sub}",
            "title_color": "#FFFFFF", "title_size": 72,
        }
        r = c.post(f"/projects/{PROJECT_ID}/clips/{clip_['id']}/vertical", json=body)
        if not check(f"clip {clip_['id']} POST {cfg}", r.status_code == 200, r.text[:80]):
            fails += 1
            continue
        msg = r.json()
        # Extract render id from detail like "Render id=1 ..."
        m = None
        import re
        m = re.search(r"id=(\d+)", msg.get("detail", ""))
        if not m:
            check(f"clip {clip_['id']} got render id", False, msg.get("detail", ""))
            fails += 1
            continue
        render_ids.append((clip_["id"], int(m.group(1))))
        print(f"    -> {msg.get('detail', '')[:60]}")

    # ── 4. poll until all renders complete ─────────────────────────────
    print("\n[4] Poll until completion (max 90s)")
    start = time.time()
    completed = {}  # render_id -> (clip_id, status, file_size, width, height)
    while time.time() - start < 90 and len(completed) < len(render_ids):
        for clip_id, rid in render_ids:
            if rid in completed:
                continue
            r = c.get(f"/projects/{PROJECT_ID}/vertical/{rid}")
            if r.status_code != 200:
                continue
            data = r.json()
            if data["status"] == "completed":
                completed[rid] = (clip_id, data)
                print(f"    render {rid} (clip {clip_id}): {data['status']}  size={data.get('file_size',0)/1024/1024:.1f}MB  {data.get('width')}x{data.get('height')}  dur={data.get('duration',0):.1f}s  proc={data.get('processing_time',0):.1f}s")
            elif data["status"] == "error":
                completed[rid] = (clip_id, data)
                fails += 1
                print(f"    [{FAIL}{RESET}] render {rid} (clip {clip_id}): ERROR -- {data.get('error_message','')[:100]}")
        if len(completed) < len(render_ids):
            time.sleep(2)
    elapsed = time.time() - start
    if not check(f"all {len(render_ids)} renders completed in {elapsed:.0f}s", len(completed) == len(render_ids)):
        fails += 1

    # ── 5. download each and verify with ffprobe ───────────────────────
    print("\n[5] Download each render and verify with ffprobe")
    download_dir = Path("data/test_downloads")
    download_dir.mkdir(exist_ok=True)
    for rid, (clip_id, data) in completed.items():
        if data.get("status") != "completed":
            continue
        out = download_dir / f"render_{rid}.mp4"
        with c.stream("GET", f"/projects/{PROJECT_ID}/vertical/{rid}/download") as resp:
            with open(out, "wb") as f:
                for chunk in resp.iter_bytes():
                    f.write(chunk)
        # Verify
        if not out.exists() or out.stat().st_size < 1024:
            check(f"render {rid} downloaded", False, f"file size={out.stat().st_size if out.exists() else 0}")
            fails += 1
            continue
        if not check(f"render {rid} file size > 1MB", out.stat().st_size > 1_000_000,
                     f"{out.stat().st_size/1024/1024:.1f}MB"):
            fails += 1
        # ffprobe check
        info = probe(str(out))
        lines = info.split("\n")
        width, height = 0, 0
        duration = 0
        for line in lines:
            parts = line.split(",")
            if len(parts) >= 3 and parts[0] == "h264":
                width, height = int(parts[1]), int(parts[2])
            elif len(parts) == 2:
                try:
                    duration = float(parts[0])
                except ValueError:
                    pass
        if not check(f"render {rid} is 1080x1920", width == 1080 and height == 1920,
                     f"{width}x{height}"):
            fails += 1
        if not check(f"render {rid} duration > 10s", duration > 10, f"{duration:.1f}s"):
            fails += 1

    # ── 6. test error handling ──────────────────────────────────────────
    print("\n[6] Error handling")

    # 6a. POST on a clip that doesn't exist
    r = c.post(f"/projects/{PROJECT_ID}/clips/99999/vertical",
               json={"layout": "split", "bg_style": "blur", "sub_style": "karaoke",
                     "bg_color": "#000", "bg_color2": "#000", "sub_color": "#fff",
                     "sub_highlight": "#fff", "sub_outline": "#000",
                     "sub_size": 64, "sub_position": 200,
                     "add_title": False, "title_text": None,
                     "title_color": "#fff", "title_size": 72})
    if not check("nonexistent clip -> 404", r.status_code == 404, str(r.status_code)):
        fails += 1

    # 6b. POST with invalid bg_style
    r = c.post(f"/projects/{PROJECT_ID}/clips/{selected[0]['id']}/vertical",
               json={"layout": "split", "bg_style": "INVALID", "sub_style": "karaoke",
                     "bg_color": "#000", "bg_color2": "#000", "sub_color": "#fff",
                     "sub_highlight": "#fff", "sub_outline": "#000",
                     "sub_size": 64, "sub_position": 200,
                     "add_title": False, "title_text": None,
                     "title_color": "#fff", "title_size": 72})
    if not check("invalid bg_style -> 422", r.status_code == 422, str(r.status_code)):
        fails += 1

    # 6c. GET nonexistent render
    r = c.get(f"/projects/{PROJECT_ID}/vertical/99999")
    if not check("nonexistent render -> 404", r.status_code == 404, str(r.status_code)):
        fails += 1

    # ── 7. DELETE renders + verify cleanup ─────────────────────────────
    print("\n[7] DELETE renders + verify cleanup")
    for rid, (clip_id, data) in completed.items():
        if data.get("status") != "completed":
            continue
        r = c.delete(f"/projects/{PROJECT_ID}/vertical/{rid}")
        if not check(f"DELETE render {rid}", r.status_code == 200, r.text[:80]):
            fails += 1
        # Verify file is gone
        expected_path = Path(data["output_path"])
        if not check(f"render {rid} file removed", not expected_path.exists(),
                     str(expected_path)):
            fails += 1

    # ── summary ────────────────────────────────────────────────────────
    print()
    if fails == 0:
        print(f"{'='*60}\n  {PASS} ALL TESTS PASSED\n{'='*60}")
    else:
        print(f"{'='*60}\n  {FAIL} {fails} TEST(S) FAILED\n{'='*60}")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
