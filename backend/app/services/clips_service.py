"""Clips service: detect viral moments, generate platform-specific content,
and extract the audio/video snippets via ffmpeg.

Workflow:
    1. ``detect_clips`` — LLM reads the transcript and returns a JSON list of
       time ranges (with rationale + virality score).
    2. User picks clips they like from the UI.
    3. ``generate_for_platforms`` — LLM writes a hook + caption + hashtags
       tailored to each platform's best practices.
    4. ``extract_media`` — ffmpeg cuts the [start, end] range from the
       source media into an audio (.mp3) and/or video (.mp4) file.
"""
from __future__ import annotations

import json
import re
import time
import asyncio
import subprocess
from pathlib import Path
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.project import (
    Project, Transcription, Clip, ClipGeneration, ClipStatus, ClipPlatform
)
from app.services.ai_service import ai_service
from app.services.audio_extractor import audio_extractor
from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Reuse the audio_extractor's ffmpeg discovery (cached after first call).
def _ffmpeg() -> str:
    return audio_extractor._ffmpeg


# ── LLM prompts ─────────────────────────────────────────────────────────────

DETECT_CLIPS_PROMPT = """You are a viral content expert. The Spanish transcript snippet below is a portion of a longer video.

Find exactly {num_clips} clip-worthy moments in THIS snippet only. Each must be {min_duration}-{max_duration} seconds.

Return ONLY a JSON array. No prose. Each object must have:
- "start": float, seconds (must be a real timestamp from the snippet)
- "end": float, seconds
- "duration_seconds": float
- "title": short catchy title in Spanish (5-8 words)
- "description": 1 sentence in Spanish
- "virality_score": integer 0-100
- "category": ONE WORD: funny, insightful, controversial, emotional, dramatic, useful
- "excerpt": the literal transcript text inside [start, end]

If no moment is interesting, return an empty array: []

Example output:
```json
[
  {{
    "start": 207.1, "end": 236.8, "duration_seconds": 29.7,
    "title": "Red Bull vs Halcones: análisis intenso",
    "description": "Momento clave del partido con análisis táctico detallado",
    "virality_score": 75, "category": "dramatic",
    "excerpt": "entre Red Bull y el equipo de los Halcones, un partido muy intenso"
  }}
]
```

TRANSCRIPT SNIPPET:
{segments}

JSON:"""


PLATFORM_PROMPTS = {
    "instagram_reels": """You are a social media manager specialized in Instagram Reels.
Write a publishing package for a short video clip from a podcast/show.

HOOK: Opening line (max 80 chars) that makes people stop scrolling. Must create curiosity.
CAPTION: 100-200 chars. Conversational, 1-2 emojis max. Lead with the hook, end with a question.
HASHTAGS: 8-12 hashtags, mix of broad (#reels #viral) and niche. With the # prefix.
CTA: 1 short sentence. Max 60 chars.
ON_SCREEN_TEXT: 3-6 words. Punchy. Capitalize key words. Max 40 chars.

Return ONLY valid JSON:
{{"hook":"...", "caption":"...", "hashtags":["..."], "cta":"...", "on_screen_text":"..."}}

CLIP TITLE: {title}
CLIP EXCERPT (transcript inside the clip):
{transcript_excerpt}

LANGUAGE: write everything in {language}.
""",

    "tiktok": """You are a TikTok growth expert. Write a publishing package for a short video.

HOOK: First line shown on screen + spoken (max 70 chars). Must create a curiosity gap.
CAPTION: 50-150 chars. Casual, punchy, native TikTok voice. 1-2 emojis.
HASHTAGS: 5-8 hashtags. Include #fyp #parati equivalents in {language}.
CTA: Optional, 1 short sentence. Max 50 chars.
ON_SCREEN_TEXT: 2-5 words. Use lowercase or sentence case. Max 35 chars.

Return ONLY valid JSON:
{{"hook":"...", "caption":"...", "hashtags":["..."], "cta":"...", "on_screen_text":"..."}}

CLIP TITLE: {title}
CLIP EXCERPT:
{transcript_excerpt}

LANGUAGE: {language}.
""",

    "youtube_shorts": """You are a YouTube Shorts growth strategist. Write a publishing package.

HOOK: First line, max 80 chars. Provocative or surprising.
CAPTION: 100-200 chars. Hook → tease → reason to watch.
HASHTAGS: 5-8 hashtags. Always include #shorts.
CTA: 1 sentence asking for subscribe/comment.
ON_SCREEN_TEXT: 3-5 words. Title-case. Max 40 chars.

Return ONLY valid JSON:
{{"hook":"...", "caption":"...", "hashtags":["..."], "cta":"...", "on_screen_text":"..."}}

CLIP TITLE: {title}
CLIP EXCERPT:
{transcript_excerpt}

LANGUAGE: {language}.
""",

    "facebook_reels": """You are a Facebook Reels copywriter. Write a publishing package.

HOOK: First line, max 90 chars. Create curiosity or emotion.
CAPTION: 150-300 chars. Tell a mini-story, lead to a question. 1-2 emojis.
HASHTAGS: 4-7 hashtags.
CTA: 1 short sentence. Ask for share/comment.
ON_SCREEN_TEXT: 3-6 words. Max 40 chars.

Return ONLY valid JSON:
{{"hook":"...", "caption":"...", "hashtags":["..."], "cta":"...", "on_screen_text":"..."}}

CLIP TITLE: {title}
CLIP EXCERPT:
{transcript_excerpt}

LANGUAGE: {language}.
""",

    "twitter_video": """You are a Twitter/X video strategist. Write a publishing package.

HOOK: First tweet, max 240 chars. Punchy, observational or contrarian.
CAPTION: 1-2 sentences. 1 emoji max.
HASHTAGS: 2-3 hashtags.
CTA: Optional, 1 sentence.
ON_SCREEN_TEXT: 2-4 words. Max 35 chars.

Return ONLY valid JSON:
{{"hook":"...", "caption":"...", "hashtags":["..."], "cta":"...", "on_screen_text":"..."}}

CLIP TITLE: {title}
CLIP EXCERPT:
{transcript_excerpt}

LANGUAGE: {language}.
""",

    "linkedin_video": """You are a LinkedIn content strategist. Write a publishing package.

HOOK: Professional opener with a contrarian or insight angle. Max 100 chars.
CAPTION: 200-400 chars. Professional, leads with a learning or POV, 2-3 short paragraphs.
HASHTAGS: 3-5 hashtags. Industry-focused.
CTA: 1 sentence asking for engagement.
ON_SCREEN_TEXT: 4-7 words. Professional tone. Max 50 chars.

Return ONLY valid JSON:
{{"hook":"...", "caption":"...", "hashtags":["..."], "cta":"...", "on_screen_text":"..."}}

CLIP TITLE: {title}
CLIP EXCERPT:
{transcript_excerpt}

LANGUAGE: {language}.
""",
}


# ── Helpers ─────────────────────────────────────────────────────────────────

def _format_segments_for_prompt(segments: list[dict], max_chars: int = 12000) -> str:
    """Turn a list of segments into a compact timestamped transcript.

    We use [start-end] text format (with square brackets) because the LLM
    uses these as visual anchors to output the same format in its JSON.
    Empirically, models like gemma4 and qwen3 respect the format better
    when we use this exact delimiter.
    """
    total_chars = sum(len(seg.get("text", "")) + 30 for seg in segments)

    # If it fits, send everything
    if total_chars <= max_chars:
        return "\n".join(
            f"[{s['start']:.1f}-{s['end']:.1f}] {s['text'].strip()}"
            for s in segments
        )

    # Sample every Nth segment to fit under the cap.
    sample_every = max(1, total_chars // max_chars)
    sampled = segments[::sample_every]
    if sampled and sampled[-1] is not segments[-1]:
        sampled.append(segments[-1])
    return "\n".join(
        f"[{s['start']:.1f}-{s['end']:.1f}] {s['text'].strip()}"
        for s in sampled
    )


def _parse_clips_json(raw: str) -> list[dict]:
    """Robustly parse the LLM's JSON array.

    Some models (qwen3 in particular) wrap their answer in ```json ... ```
    or add a leading sentence. We try multiple extraction strategies.
    """
    raw = raw.strip()

    # Strip code fences
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

    # Find the first '[' and last ']'
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1:
        raise ValueError("No JSON array found in LLM response")

    candidate = raw[start:end + 1]

    # Try strict parse first
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    # Try to recover: remove trailing commas, fix smart quotes, strip control chars
    cleaned = candidate
    # Remove control characters (0x00-0x1F) except \n, \r, \t
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", cleaned)
    # Replace smart quotes with ASCII
    cleaned = cleaned.replace("\u201c", '"').replace("\u201d", '"')
    cleaned = cleaned.replace("\u2018", "'").replace("\u2019", "'")
    # Drop trailing commas before ] or }
    cleaned = re.sub(r",(\s*[}\]])", r"\1", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        # Last resort: try to find individual JSON objects and parse them
        # (some LLMs output slightly malformed JSON with extra commas)
        objects = []
        depth = 0
        obj_start = -1
        for i, ch in enumerate(cleaned):
            if ch == "{":
                if depth == 0:
                    obj_start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and obj_start >= 0:
                    try:
                        objects.append(json.loads(cleaned[obj_start:i + 1]))
                    except json.JSONDecodeError:
                        pass
                    obj_start = -1
        if objects:
            return objects
        raise ValueError(f"Failed to parse JSON: {e}")


def _parse_platform_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in platform response")
    return json.loads(raw[start:end + 1])


# ── Service ─────────────────────────────────────────────────────────────────

class ClipsService:
    async def detect_clips(
        self,
        db: AsyncSession,
        project_id: int,
        num_clips: int = 8,
        min_duration: int = 15,
        max_duration: int = 60,
        model: str = "qwen3:8b",
    ) -> list[Clip]:
        """Run the LLM over the transcript in chunks and persist the resulting clips.

        Local 8B models lose coherence on prompts over ~2k chars. We split the
        transcript into chunks of at most ~5-10 minutes of audio each, ask
        the LLM for up to ``num_clips`` candidates per chunk, and aggregate
        the results. We dedupe overlapping ranges and rank by virality_score.

        Existing clips for this project are kept — we just add the new ones.
        """
        project = await _load_project_with_transcription(db, project_id)
        segments = project.transcription.segments or []
        if not segments:
            raise ValueError("Transcription has no segments to analyze")

        language = project.transcription.language_detected or "Spanish"

        # Split segments into time-based chunks of ~5 minutes each.
        # Each chunk becomes one LLM call. The model sees only that portion,
        # which keeps the prompt short (~2-3k chars) and the model focused.
        chunk_seconds = 300  # 5 minutes
        first_start = float(segments[0].get("start", 0))
        last_end = float(segments[-1].get("end", 0))
        chunk_starts = []
        t = first_start
        while t < last_end:
            chunk_starts.append(t)
            t += chunk_seconds
        num_chunks = len(chunk_starts)
        if num_chunks == 0:
            num_chunks = 1
            chunk_starts = [first_start]

        logger.info("clips_detection_starting",
                    project_id=project_id,
                    num_chunks=num_chunks,
                    model=model)

        all_candidates: list[dict] = []
        for ci, chunk_start in enumerate(chunk_starts):
            chunk_end = chunk_start + chunk_seconds
            chunk_segs = [
                s for s in segments
                if float(s.get("start", 0)) < chunk_end
                and float(s.get("end", 0)) > chunk_start
            ]
            if not chunk_segs:
                continue
            formatted = _format_segments_for_prompt(chunk_segs, max_chars=2000)
            prompt = DETECT_CLIPS_PROMPT.format(
                num_clips=3,  # per chunk
                min_duration=min_duration,
                max_duration=max_duration,
                segments=formatted,
            )

            try:
                raw = await ai_service.generate(prompt, model)
                parsed = _parse_clips_json(raw) if raw and len(raw) > 20 else []
                logger.info("clips_chunk_done",
                            project_id=project_id, chunk=ci + 1,
                            chunk_segments=len(chunk_segs),
                            candidates=len(parsed))
                all_candidates.extend(parsed)
            except Exception as e:
                logger.warning("clips_chunk_failed",
                               project_id=project_id, chunk=ci + 1, error=str(e))
                continue

        # Build segments index by start for excerpt lookup
        seg_by_time = sorted(segments, key=lambda s: s.get("start", 0))
        video_duration = max(float(seg.get("end", 0)) for seg in segments) if segments else 0

        # Dedupe by start time (within 2s) and rank
        seen_starts: list[float] = []
        unique: list[dict] = []
        for c in all_candidates:
            try:
                s = float(c.get("start"))
                e = float(c.get("end"))
            except (TypeError, ValueError):
                continue
            if e <= s:
                continue
            # Dedupe window: 2 seconds
            if any(abs(s - prev) < 2.0 for prev in seen_starts):
                continue
            seen_starts.append(s)
            unique.append(c)

        # Rank by virality_score desc, keep top num_clips
        def _score(c: dict) -> int:
            try:
                return int(c.get("virality_score", 0))
            except (TypeError, ValueError):
                return 0

        unique.sort(key=_score, reverse=True)
        unique = unique[:num_clips]

        new_clips: list[Clip] = []
        for item in unique:
            try:
                start_sec = float(item["start"])
                end_sec = float(item["end"])
            except (KeyError, ValueError, TypeError):
                continue
            if end_sec <= start_sec:
                continue
            duration = end_sec - start_sec
            if duration < 10 or duration > max_duration * 2:
                continue
            # Reject clips that start beyond the actual video duration
            # (the LLM sometimes hallucinates timestamps past the end of
            # the audio). This is a hard reject — better to skip than to
            # persist a clip that can't be extracted.
            if start_sec >= video_duration - 1.0:
                continue
            # Clamp end to video duration; if clamping makes it too short, skip
            end_sec = min(end_sec, video_duration)
            duration = end_sec - start_sec
            if duration < 10:
                continue

            excerpt = item.get("excerpt", "").strip()
            if not excerpt:
                excerpt = _extract_excerpt(seg_by_time, start_sec, end_sec)

            clip = Clip(
                transcription_id=project.transcription.id,
                project_id=project_id,
                start=round(start_sec, 2),
                end=round(end_sec, 2),
                duration=round(duration, 2),
                title=str(item.get("title", "Untitled"))[:255],
                description=item.get("description"),
                virality_score=_score(item) or None,
                category=item.get("category"),
                transcript_excerpt=excerpt,
                status=ClipStatus.PENDING,
            )
            db.add(clip)
            new_clips.append(clip)

        await db.flush()
        for c in new_clips:
            await db.refresh(c)
        logger.info("clips_persisted",
                    project_id=project_id,
                    candidates=len(all_candidates),
                    unique=len(unique),
                    accepted=len(new_clips))
        return new_clips

    async def generate_for_platforms(
        self,
        db: AsyncSession,
        project_id: int,
        clip_id: int,
        platforms: list[str],
        model: str = "qwen3:8b",
    ) -> list[ClipGeneration]:
        """For a given clip, generate a publishing package per platform."""
        # Validate platforms
        valid = {p.value for p in ClipPlatform}
        bad = [p for p in platforms if p not in valid]
        if bad:
            raise ValueError(f"Unknown platform(s): {bad}. Valid: {sorted(valid)}")

        # Load clip
        result = await db.execute(
            select(Clip)
            .where(Clip.id == clip_id, Clip.project_id == project_id)
            .options(selectinload(Clip.platforms))
        )
        clip = result.scalar_one_or_none()
        if not clip:
            raise ValueError(f"Clip {clip_id} not found in project {project_id}")

        # Project language for the prompt
        proj = await _load_project_with_transcription(db, project_id)
        language = proj.transcription.language_detected or "Spanish"

        # Existing generations for this clip+platform pair, so we can update
        existing_by_platform = {g.platform: g for g in clip.platforms}

        new_gens: list[ClipGeneration] = []
        for platform in platforms:
            prompt_template = PLATFORM_PROMPTS.get(platform)
            if not prompt_template:
                continue
            prompt = prompt_template.format(
                title=clip.title,
                transcript_excerpt=clip.transcript_excerpt or "",
                language=language,
            )

            start = time.time()
            try:
                raw = await ai_service.generate(prompt, model)
                payload = _parse_platform_json(raw)
            except Exception as e:
                # Persist the error so the UI can show it
                if platform in existing_by_platform:
                    gen = existing_by_platform[platform]
                else:
                    gen = ClipGeneration(
                        clip_id=clip.id, project_id=project_id, platform=platform,
                        hook="", caption="",
                    )
                    db.add(gen)
                gen.error_message = f"Generation failed: {e}"
                gen.model_used = model
                await db.flush()
                logger.error("platform_gen_failed",
                             project_id=project_id, clip_id=clip_id,
                             platform=platform, error=str(e))
                continue
            elapsed = time.time() - start

            # Coerce hashtags to list[str]
            hashtags = payload.get("hashtags", [])
            if isinstance(hashtags, str):
                hashtags = [h.strip() for h in re.split(r"[,#\s]+", hashtags) if h.strip()]

            if platform in existing_by_platform:
                gen = existing_by_platform[platform]
            else:
                gen = ClipGeneration(
                    clip_id=clip.id, project_id=project_id, platform=platform,
                    hook="", caption="",
                )
                db.add(gen)
            gen.hook = (payload.get("hook", "") or "")[:500]
            gen.caption = payload.get("caption", "") or ""
            gen.hashtags = hashtags or []
            gen.cta = (payload.get("cta", "") or "")[:255]
            gen.on_screen_text = (payload.get("on_screen_text", "") or "")[:500]
            gen.model_used = model
            gen.processing_time = round(elapsed, 2)
            gen.error_message = None
            new_gens.append(gen)

        await db.flush()
        for g in new_gens:
            await db.refresh(g)
        return new_gens

    async def extract_media(
        self,
        db: AsyncSession,
        project_id: int,
        clip_id: int,
        with_video: bool = True,
    ) -> Clip:
        """Cut [start, end] from the source media into audio (and optionally video).

        Validates the clip's timestamps against the actual source media duration
        before invoking ffmpeg. The local LLMs sometimes hallucinate timestamps
        beyond the video length; cutting at those produces empty (0.4s) clips
        that can't be played in any system. We clamp to the actual end.
        """
        result = await db.execute(
            select(Clip).where(Clip.id == clip_id, Clip.project_id == project_id)
        )
        clip = result.scalar_one_or_none()
        if not clip:
            raise ValueError(f"Clip {clip_id} not found in project {project_id}")

        # Load project to get original media
        result = await db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if not project:
            raise ValueError(f"Project {project_id} not found")

        source = None
        if with_video and project.original_file and Path(project.original_file).exists():
            source = Path(project.original_file)
        elif project.audio_file and Path(project.audio_file).exists():
            source = Path(project.audio_file)
        else:
            raise ValueError("No source media available for this project")

        # ── Validate clip timestamps against the actual media ────────────
        # LLMs (especially 8B local models) sometimes output timestamps
        # beyond the actual video duration. Cutting at those yields a 0.4s
        # empty clip. We probe the source and clamp.
        loop = asyncio.get_event_loop()
        probe_cmd = [
            _ffmpeg().replace("ffmpeg", "ffprobe"),
            "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(source),
        ]
        try:
            probe_out = await loop.run_in_executor(
                None, lambda: subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)
            )
            media_duration = float(probe_out.stdout.strip())
        except Exception as e:
            raise RuntimeError(f"Could not probe media duration: {e}")

        # Clamp the clip to the actual media range
        original_start = clip.start
        original_end = clip.end
        start_sec = max(0.0, min(float(clip.start), media_duration - 0.5))
        end_sec = max(start_sec + 0.5, min(float(clip.end), media_duration))
        if end_sec - start_sec < 1.0:
            raise ValueError(
                f"Clip range [{clip.start:.1f}s-{clip.end:.1f}s] is outside the "
                f"actual media duration ({media_duration:.1f}s). Delete and re-detect."
            )

        # Update the DB row so the UI shows the correct (clamped) range
        if abs(start_sec - original_start) > 0.1 or abs(end_sec - original_end) > 0.1:
            logger.warning("clip_timestamps_clamped",
                           project_id=project_id, clip_id=clip_id,
                           orig_start=original_start, orig_end=original_end,
                           new_start=start_sec, new_end=end_sec,
                           media_duration=media_duration)
            clip.start = round(start_sec, 2)
            clip.end = round(end_sec, 2)
            clip.duration = round(end_sec - start_sec, 2)
            await db.flush()

        out_dir = settings.data_dir / "clips" / str(project_id)
        out_dir.mkdir(parents=True, exist_ok=True)

        # ffmpeg -ss <start> -to <end> -i <src> -c copy <out>
        # -ss BEFORE -i = fast seek (keyframe-based), so we add 0.1s margin
        # to be safe on the left edge. -to AFTER -i = precise end.
        audio_out = out_dir / f"clip_{clip_id}.mp3"
        # Wipe any prior file so we don't serve a stale small one
        if audio_out.exists():
            audio_out.unlink()
        cmd = [
            _ffmpeg(),
            "-y", "-loglevel", "error",
            "-ss", str(start_sec),
            "-to", str(end_sec),
            "-i", str(source),
            "-vn", "-acodec", "libmp3lame", "-b:a", "192k",
            str(audio_out),
        ]
        await loop.run_in_executor(None, lambda: subprocess.run(cmd, check=True))
        # Verify the output has the expected size
        if audio_out.stat().st_size < 1024:
            audio_out.unlink(missing_ok=True)
            raise RuntimeError(f"Generated audio clip is too small ({audio_out.stat().st_size} bytes); ffmpeg may have failed silently")
        clip.audio_clip_path = str(audio_out)

        if with_video:
            video_out = out_dir / f"clip_{clip_id}.mp4"
            if video_out.exists():
                video_out.unlink()
            # -c copy to avoid re-encoding (very fast, frame-accurate to ~keyframe)
            cmd = [
                _ffmpeg(),
                "-y", "-loglevel", "error",
                "-ss", str(start_sec),
                "-to", str(end_sec),
                "-i", str(source),
                "-c", "copy",
                "-avoid_negative_ts", "make_zero",
                str(video_out),
            ]
            used_reencode = False
            try:
                await loop.run_in_executor(None, lambda: subprocess.run(cmd, check=True))
            except subprocess.CalledProcessError:
                # Some codecs don't support stream-copy cut; fall back to re-encode
                used_reencode = True
                cmd = [
                    _ffmpeg(),
                    "-y", "-loglevel", "error",
                    "-ss", str(start_sec), "-to", str(end_sec), "-i", str(source),
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                    "-c:a", "aac", "-b:a", "160k",
                    "-avoid_negative_ts", "make_zero",
                    str(video_out),
                ]
                await loop.run_in_executor(None, lambda: subprocess.run(cmd, check=True))

            # Verify the output duration is what we asked for
            try:
                probe_out = await loop.run_in_executor(
                    None, lambda: subprocess.run(
                        [_ffmpeg().replace("ffmpeg", "ffprobe"),
                         "-v", "error", "-show_entries", "format=duration",
                         "-of", "default=noprint_wrappers=1:nokey=1",
                         str(video_out)],
                        capture_output=True, text=True, timeout=10,
                    )
                )
                out_dur = float(probe_out.stdout.strip() or 0)
            except Exception:
                out_dur = 0

            if out_dur < 0.5:
                # Re-encode didn't help — try a precise re-encode
                if not used_reencode:
                    video_out.unlink(missing_ok=True)
                    cmd = [
                        _ffmpeg(),
                        "-y", "-loglevel", "error",
                        "-i", str(source),
                        "-ss", str(start_sec), "-to", str(end_sec),
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                        "-c:a", "aac", "-b:a", "160k",
                        "-avoid_negative_ts", "make_zero",
                        str(video_out),
                    ]
                    await loop.run_in_executor(None, lambda: subprocess.run(cmd, check=True))
                    probe_out = await loop.run_in_executor(
                        None, lambda: subprocess.run(
                            [_ffmpeg().replace("ffmpeg", "ffprobe"),
                             "-v", "error", "-show_entries", "format=duration",
                             "-of", "default=noprint_wrappers=1:nokey=1",
                             str(video_out)],
                            capture_output=True, text=True, timeout=10,
                        )
                    )
                    out_dur = float(probe_out.stdout.strip() or 0)

            if out_dur < 0.5:
                # Even re-encode failed. Mark as missing rather than serving garbage.
                video_out.unlink(missing_ok=True)
                logger.error("clip_video_too_short", project_id=project_id, clip_id=clip_id,
                             output_duration=out_dur, requested=end_sec - start_sec)
            else:
                clip.video_clip_path = str(video_out)

        clip.status = ClipStatus.GENERATED
        await db.flush()
        await db.refresh(clip)
        logger.info("clip_extracted", project_id=project_id, clip_id=clip_id,
                    audio=bool(clip.audio_clip_path), video=bool(clip.video_clip_path),
                    audio_size=Path(clip.audio_clip_path).stat().st_size if clip.audio_clip_path else 0)
        return clip


def _extract_excerpt(segments: list[dict], start: float, end: float) -> str:
    """Build the transcript text that falls inside [start, end]."""
    parts: list[str] = []
    for seg in segments:
        s = float(seg.get("start", 0))
        e = float(seg.get("end", 0))
        if e < start:
            continue
        if s > end:
            break
        parts.append(seg.get("text", "").strip())
    return " ".join(p for p in parts if p).strip()


async def _load_project_with_transcription(db: AsyncSession, project_id: int) -> Project:
    result = await db.execute(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.transcription))
    )
    project = result.scalar_one_or_none()
    if not project:
        raise ValueError(f"Project {project_id} not found")
    if not project.transcription or not project.transcription.segments:
        raise ValueError("Project has no transcription with segments. Transcribe first.")
    return project


clips_service = ClipsService()
