"""Vertical video editor service.

Converts a horizontal clip (16:9, typically 1920x1080) into a vertical
clip (9:16, 1080x1920) ready for Instagram Reels / TikTok / YouTube Shorts.

Features (V1):
- 4 background styles: blur, solid, gradient, zoom
- 3 subtitle styles: standard, karaoke (word-by-word highlight), neon
- Optional title overlay at the top
- Fast re-encode with libx264 (or h264_nvenc if available)

Pipeline (single ffmpeg invocation, fast):
    source 1920x1080
      -> scale to 3413x1920 (preserve height, 9:16 of full height)
      -> crop center 1080x1920
      -> optionally overlay blurred/scaled/zoomed background
      -> burn ASS subtitles
      -> optionally overlay title
      -> libx264 + AAC

The output is a 1080x1920 MP4 with H.264 video and AAC audio, ready to
upload to any short-form platform.
"""
from __future__ import annotations

import asyncio
import json
import math
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from app.services.audio_extractor import audio_extractor
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Reuse the cached ffmpeg path discovery
def _ffmpeg() -> str:
    return audio_extractor._ffmpeg


# ── Cross-platform font detection ─────────────────────────────────────────

def _detect_subtitle_font() -> str:
    """Return the best available system font for ASS subtitles.

    We return only the *family name* (e.g. "Arial", "DejaVu Sans") which
    goes in the ASS ``Style:`` line. libass looks up the actual TTF file
    on its own.

    Falls back to "Arial" (which most fontconfig installs alias to
    Liberation Sans on Linux or Helvetica on macOS).
    """
    from app.config import settings
    for path in settings.subtitle_font_paths:
        if Path(path).exists():
            name = Path(path).stem.lower()
            # Common aliases
            if "arial" in name or "helvetica" in name:
                return "Arial"
            if "dejavu" in name:
                return "DejaVu Sans"
            if "liberation" in name:
                return "Liberation Sans"
            if "segoe" in name:
                return "Segoe UI"
            return Path(path).stem
    return "Arial"


def _detect_title_fontfile() -> str | None:
    """Return the absolute path of a bold TTF for the drawtext filter, or None.

    drawtext needs the literal path to a TTF (it doesn't use fontconfig).
    We pick the bold variant of the system font when available.
    """
    from app.config import settings
    candidates = settings.subtitle_font_paths
    # Try the bold versions of the same fonts first
    bold_candidates: list[str] = []
    for c in candidates:
        p = Path(c)
        if p.stem.lower().startswith("arial"):
            bold_candidates.append(str(p.with_name("arialbd.ttf")))
        elif p.stem.lower().startswith("helvetica"):
            bold_candidates.append(str(p.with_name("Helvetica-Bold.ttc")))
    for c in candidates + bold_candidates:
        if Path(c).exists():
            return c
    return None


# ── Types ───────────────────────────────────────────────────────────────────

SubStyle = Literal[
    "standard",       # white text, black outline (default)
    "karaoke",        # word-by-word highlight with bold/regular switch
    "neon",           # bright color with thick outline + glow shadow
    "mrbeast",        # huge bold yellow text, red word-active with shake (Phase 9)
    "hormozi",        # white text with thick outline, word zooms in (Phase 9)
    "tiktok_classic", # white text, yellow highlight, 2-line wrap (Phase 9, like CapCut default)
]
BgStyle = Literal["blur", "solid", "gradient", "zoom"]
# Phase 10: "auto" = active speaker detection + dynamic crop
Layout = Literal["split", "centered", "fill", "auto"]


@dataclass
class SubtitleEntry:
    """One subtitle line. Times are in seconds, relative to the clip start (0 = clip start)."""
    start: float
    end: float
    text: str


@dataclass
class WordTimestamp:
    """One word with timing. Times are in seconds, absolute (video-level, not clip-relative)."""
    start: float
    end: float
    word: str


@dataclass
class BrollPlacement:
    """A B-roll image overlaid full-bleed during [start, end] (clip-relative seconds)."""
    url: str
    start: float
    end: float
    opacity: float = 1.0


@dataclass
class VideoTransform:
    """Translate/scale/rotate the main video inside the 1080x1920 frame."""
    x: float = 0.0          # px offset from frame center
    y: float = 0.0          # px offset from frame center
    scale: float = 100.0    # 100 = original size
    rotation: float = 0.0   # degrees

    def is_identity(self) -> bool:
        return (
            abs(self.x) < 0.01 and abs(self.y) < 0.01
            and abs(self.scale - 100.0) < 0.01 and abs(self.rotation) < 0.01
        )


@dataclass
class RenderOptions:
    layout: Layout = "split"           # 'split' = full-bleed video; 'centered' = blurred bg + smaller video; 'fill' = video fills vertical
    bg_style: BgStyle = "blur"          # 'blur' | 'solid' | 'gradient' | 'zoom'
    bg_color: str = "#1a1a2e"           # for 'solid' or as gradient start
    bg_color2: str = "#16213e"          # for 'gradient' end color
    sub_style: SubStyle = "karaoke"     # 'standard' | 'karaoke' | 'neon'
    sub_color: str = "#FFFFFF"          # subtitle text color (hex)
    sub_highlight: str = "#FFD700"      # karaoke highlight color
    sub_outline: str = "#000000"        # outline color
    sub_size: int = 64                  # font size in pixels
    sub_position: int = 200             # pixels from bottom
    add_title: bool = True
    title_text: str = ""                # if empty, uses clip title
    title_color: str = "#FFFFFF"
    title_size: int = 72
    title_position: str = "top"         # 'top' | 'center' | 'bottom'
    # Watermark (Phase 6)
    watermark_path: str | None = None   # absolute path to a PNG image, or None
    watermark_position: str = "bottom_right"  # 'top_left'|'top_right'|'bottom_left'|'bottom_right'|'center'
    watermark_opacity: float = 0.8     # 0.0 to 1.0
    # B-roll placements (Vertical Editor Phase 3) — full-bleed image cutaways
    broll_placements: list[BrollPlacement] = field(default_factory=list)
    # Video transform (Priority 1) — translate/scale/rotate [v_main]. None = layout defaults.
    video_transform: VideoTransform | None = None
    # Phase 15 — render quality. 'draft' produces a 480p, ultrafast-encoded
    # preview used for fast UI feedback; B-rolls and watermark are skipped
    # to avoid blocking the user on network/disk I/O. 'final' is the full
    # quality render that gets persisted and published.
    quality: str = "final"              # 'draft' | 'final'


# ── ASS subtitle generator ──────────────────────────────────────────────────

# ASS time format: H:MM:SS.cc (centiseconds, 2 digits)
def _ass_time(t: float) -> str:
    if t < 0:
        t = 0
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    cs = int(round((s - int(s)) * 100))
    if cs >= 100:
        cs = 99
    return f"{h:d}:{m:02d}:{int(s):02d}.{cs:02d}"


def _hex_to_ass(hex_color: str) -> str:
    """Convert '#RRGGBB' to ASS '&H00BBGGRR' (BGR order, alpha 00)."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b.upper()}{g.upper()}{r.upper()}"


def _escape_ass_text(text: str) -> str:
    """Escape characters that have special meaning in ASS dialogue text."""
    # ASS uses \ as escape, so we need to escape backslashes and braces
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def _style_line_standard(
    font_size: int, primary: str, outline: str, bottom_margin: int,
) -> str:
    """Default white-on-black style. The most universal safe choice."""
    return (
        f"Style: Default,{_detect_subtitle_font()},{font_size},{primary},&H0000FFFF,{outline},&H80000000,"
        f"-1,0,0,0,100,100,0,0,1,4,2,2,40,40,{bottom_margin},1"
    )


def _style_line_neon(
    font_size: int, primary: str, outline: str, bottom_margin: int,
) -> str:
    """Neon glow: thick outline + bright shadow color matches the text."""
    outline_w = 8
    shadow = 4
    return (
        f"Style: Default,{_detect_subtitle_font()},{font_size},{primary},&H0000FFFF,&H00000000,{outline},"
        f"-1,0,0,0,100,100,0,0,1,{outline_w},{shadow},2,40,40,{bottom_margin},1"
    )


def _style_line_mrbeast(
    font_size: int, primary: str, outline: str, bottom_margin: int,
) -> str:
    """MrBeast style: huge bold yellow text with black outline.

    The actual word-active effect is applied at the Dialogue-line level
    using ``{\\fscx120\\fscy120\\3c&H0000FF&\\t(...)}`` to scale the
    active word and flash it red. Here we only configure the base style:
    a giant bold yellow font with thick black outline.
    """
    # Primary = yellow (&H0000FFFF), outline = black, very thick (8px)
    return (
        f"Style: Default,{_detect_subtitle_font()},{font_size},{primary},&H000000FF,{outline},&H80000000,"
        f"-1,0,0,0,110,110,0,0,1,8,3,2,30,30,{bottom_margin},1"
    )


def _style_line_hormozi(
    font_size: int, primary: str, outline: str, bottom_margin: int,
) -> str:
    """Hormozi style: white text, very thick white outline, no shadow.

    The "punch" effect is added per-line using ``{\\fad(200,0)\\3c&HFFFFFF&}``
    and a quick scale-up. The base style is the signature chunky white look.
    """
    return (
        f"Style: Default,{_detect_subtitle_font()},{font_size},{primary},&H000000FF,&H00FFFFFF,&H80000000,"
        f"-1,0,0,0,100,100,0,0,1,12,0,2,40,40,{bottom_margin},1"
    )


def _style_line_tiktok_classic(
    font_size: int, primary: str, outline: str, bottom_margin: int,
) -> str:
    """TikTok / CapCut default: white text, thick black outline, no shadow.

    The "word-active yellow highlight" is applied at the Dialogue level
    by switching SecondaryColour to yellow and using ``{\\1c&H0000FFFF}``
    on the highlighted word. Base style is clean and very legible.
    """
    return (
        f"Style: Default,{_detect_subtitle_font()},{font_size},{primary},&H0000FFFF,{outline},&H80000000,"
        f"-1,0,0,0,100,100,0,0,1,6,2,2,40,40,{bottom_margin},1"
    )


# Registry: maps a SubStyle to its ASS Style line builder.
# Each function takes the same args: (font_size, primary, outline, bottom_margin).
_STYLE_LINE_BUILDERS = {
    "standard":       _style_line_standard,
    "neon":           _style_line_neon,
    "mrbeast":        _style_line_mrbeast,
    "hormozi":        _style_line_hormozi,
    "tiktok_classic": _style_line_tiktok_classic,
}


def build_ass_style_line(
    sub_style: SubStyle,
    font_size: int,
    text_color: str,
    outline_color: str,
    bottom_margin: int = 200,
) -> str:
    """Pick the right ASS Style line for the given sub style.

    Centralized so all code paths (line subs, karaoke, presets) use the
    same definition. Unknown styles fall back to "standard".
    """
    primary = _hex_to_ass(text_color)
    outline = _hex_to_ass(outline_color)
    builder = _STYLE_LINE_BUILDERS.get(sub_style, _style_line_standard)
    return builder(font_size, primary, outline, bottom_margin)


def build_ass_subtitles(
    entries: list[SubtitleEntry],
    style: SubStyle = "karaoke",
    text_color: str = "#FFFFFF",
    highlight_color: str = "#FFD700",
    outline_color: str = "#000000",
    font_size: int = 64,
    bottom_margin: int = 200,
    width: int = 1080,
    height: int = 1920,
) -> str:
    """Build an ASS file from a list of subtitle entries.

    For 'standard' and 'neon' styles, each entry becomes one Dialogue line.
    For 'karaoke', each entry becomes one line but the text is rendered with
    progressive word highlighting using {\an8} and {\b1} tags.

    NOTE: True karaoke (per-word timing) is implemented separately via
    ``build_ass_karaoke_from_words`` because the highlight must advance as
    each word is spoken. This function handles line-level subs only.
    """
    # Margins: 40 sides, 40 top, bottom from style
    primary = _hex_to_ass(text_color)
    outline = _hex_to_ass(outline_color)
    # Use the new style-line registry (handles standard, neon, mrbeast, hormozi, tiktok_classic)
    style_line = build_ass_style_line(style, font_size, text_color, outline_color, bottom_margin)

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 2",  # smart wrapping
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        style_line,
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    for entry in entries:
        if entry.end <= entry.start:
            continue
        text = _escape_ass_text(entry.text.strip())
        if not text:
            continue
        # Per-style "Effect" prefix. Keep these short — most visual
        # styling lives in the Style line itself; the Effect column is
        # for entry-level overrides (fade, pop-in, shake).
        effect = ""
        if style == "mrbeast":
            # Pop-in: starts at 90% scale, eases to 100% in 80ms
            effect = "{\\fscx90\\fscy90\\t(0,80,\\fscx100\\fscy100)}"
        elif style == "hormozi":
            # Quick fade in, then a "punch" via a brief overshoot
            effect = "{\\fad(120,80)\\fscx105\\fscy105\\t(0,140,\\fscx100\\fscy100)}"
        elif style == "tiktok_classic":
            # Gentle fade-in only — CapCut's default
            effect = "{\\fad(200,0)}"
        lines.append(
            f"Dialogue: 0,{_ass_time(entry.start)},{_ass_time(entry.end)},Default,,0,0,0,,"
            f"{effect}{text}"
        )

    return "\n".join(lines) + "\n"


def build_ass_karaoke_from_words(
    words: list[WordTimestamp],
    chunk_size: int = 5,
    sub_style: SubStyle = "karaoke",
    text_color: str = "#FFFFFF",
    highlight_color: str = "#FFD700",
    outline_color: str = "#000000",
    font_size: int = 64,
    bottom_margin: int = 200,
    width: int = 1080,
    height: int = 1920,
    clip_offset: float = 0.0,
) -> str:
    """Build ASS with word-by-word highlighting for the chosen ``sub_style``.

    Each line groups ``chunk_size`` words. Within a line, we emit multiple
    Dialogue events that overlap in time, each showing one more word in
    highlight (the others stay dim). This creates the "growing highlight"
    effect used in TikTok/Shorts, MrBeast, Hormozi, etc.

    The visual flavour of the highlight depends on ``sub_style``:
      - ``karaoke``:        bold + secondary color (default)
      - ``mrbeast``:        red text + scale 130% on active word
      - ``hormozi``:        secondary color + scale 115% on active word
      - ``tiktok_classic``: yellow color on active word, no scale
      - ``standard`` / ``neon``: not really meant for karaoke, but fall back
        to bold + highlight color so the user still gets *some* animation.

    ``clip_offset`` is the absolute video time of the clip's start. Word
    timestamps are absolute; we subtract the offset to make them relative.
    """
    primary = _hex_to_ass(text_color)
    secondary = _hex_to_ass(highlight_color)  # active word
    outline = _hex_to_ass(outline_color)
    # Use the style-line registry so the base font/outline/size match
    # the chosen style. The karaoke (highlight) tag overrides the
    # SecondaryColour at the dialogue level.
    style_line = build_ass_style_line(sub_style, font_size, text_color, outline_color, bottom_margin)

    # Per-style "active word" effect. The {\\b1} tag is the universal
    # ASS way to say "use SecondaryColour + Bold for the rest of this
    # override group". We combine it with style-specific extras.
    active_word_tag = {
        "karaoke":        "{\\b1}",
        "mrbeast":        "{\\1c&H000000FF&\\3c&H00FFFFFF&\\b1\\fscx130\\fscy130}",  # red, white outline, 130% scale
        "hormozi":        "{\\b1\\fscx115\\fscy115}",  # secondary color, 115% scale
        "tiktok_classic": "{\\1c&H0000FFFF&\\b1}",   # yellow, bold
        "standard":       "{\\b1}",
        "neon":           "{\\b1\\fscx110\\fscy110}",  # slight pop
    }.get(sub_style, "{\\b1}")
    dim_word_tag = {
        "mrbeast":        "{\\b0}",                   # mrbeast: dim words stay yellow, only active flips red
        "hormozi":        "{\\b0}",
        "tiktok_classic": "{\\b0}",                   # dim words stay white
        "karaoke":        "{\\b0}",
        "standard":       "{\\b0}",
        "neon":           "{\\b0}",
    }.get(sub_style, "{\\b0}")

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 2",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        style_line,
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    # Group words into chunks for readability
    chunks: list[list[WordTimestamp]] = []
    for i in range(0, len(words), chunk_size):
        chunks.append(words[i:i + chunk_size])

    for chunk in chunks:
        if not chunk:
            continue
        # Convert to clip-relative times
        rel_starts = [max(0.0, w.start - clip_offset) for w in chunk]
        rel_ends = [max(0.0, w.end - clip_offset) for w in chunk]
        chunk_start = rel_starts[0]
        chunk_end = rel_ends[-1]
        if chunk_end <= chunk_start:
            continue

        # For each word in the chunk, emit a Dialogue that runs from
        # the chunk_start to the END of that word. This way, when the
        # current word is being spoken, all words up to and including it
        # are highlighted. The result is a "growing" highlight that
        # moves word-by-word.
        for j, w in enumerate(chunk):
            parts = []
            for k, w2 in enumerate(chunk):
                wt = _escape_ass_text(w2.word.strip())
                if k <= j:
                    parts.append(f"{active_word_tag}{wt}")
                else:
                    parts.append(f"{dim_word_tag}{wt}")
            full_text = " ".join(parts)
            lines.append(
                f"Dialogue: 0,{_ass_time(chunk_start)},{_ass_time(rel_ends[j])},Default,,0,0,0,,"
                f"{full_text}"
            )

    return "\n".join(lines) + "\n"


# ── Subtitle extraction ─────────────────────────────────────────────────────

def extract_words_for_clip(
    segments: list[dict],
    clip_start: float,
    clip_end: float,
) -> list[WordTimestamp]:
    """Pull word timestamps that fall inside [clip_start, clip_end].

    Returns clip-relative timestamps (subtract clip_start).
    """
    out: list[WordTimestamp] = []
    for seg in segments:
        for w in seg.get("words") or []:
            ws = float(w.get("start", 0))
            we = float(w.get("end", 0))
            if we <= clip_start or ws >= clip_end:
                continue
            # Clip to range
            cs = max(0.0, ws - clip_start)
            ce = min(clip_end - clip_start, we - clip_start)
            if ce - cs < 0.02:  # skip tiny slivers
                continue
            out.append(WordTimestamp(start=cs, end=ce, word=str(w.get("word", "")).strip()))
    return out


def group_words_into_lines(
    words: list[WordTimestamp],
    max_words: int = 6,
    max_duration: float = 3.5,
) -> list[SubtitleEntry]:
    """Group word timestamps into readable subtitle lines.

    Lines break on:
    - More than ``max_words`` words
    - Longer than ``max_duration`` seconds
    - Sentence-ending punctuation (., !, ?, …)
    """
    if not words:
        return []
    lines: list[SubtitleEntry] = []
    current: list[WordTimestamp] = []
    line_start = words[0].start

    def flush():
        nonlocal current, line_start
        if not current:
            return
        text = " ".join(w.word for w in current).strip()
        if text:
            lines.append(SubtitleEntry(
                start=line_start,
                end=current[-1].end,
                text=text,
            ))
        current = []

    for w in words:
        # Sentence-end break
        if current and (current[-1].word.endswith((".", "!", "?", "…"))):
            flush()
            line_start = w.start
        if current and (len(current) >= max_words or (w.end - line_start) > max_duration):
            flush()
            line_start = w.start
        current.append(w)
    flush()
    return lines


# ── Render ──────────────────────────────────────────────────────────────────

def build_filter_complex(
    options: RenderOptions,
    has_subs: bool,
    has_title: bool,
) -> str:
    """Build the ffmpeg filter_complex string for vertical conversion.

    Layouts:
      - 'fill':   video fills the entire 1080x1920 frame (vertical crop from center)
      - 'split':  video on top half, blurred video on bottom (or solid color)
      - 'centered': video centered in a blurred/solid background (smaller)

    Backgrounds:
      - 'blur':     heavily blurred copy of the source behind/around
      - 'solid':    solid color from options.bg_color
      - 'gradient': vertical gradient from options.bg_color to options.bg_color2
      - 'zoom':     zoomed-in slow Ken Burns effect on the source
    """
    # Step 1: prepare the main video (always 1080x1920)
    # Source is 16:9 (e.g. 1920x1080). We scale so HEIGHT = 1920, width
    # becomes 3413, then crop center 1080 wide. This preserves full height.
    main_chain = (
        "[0:v]scale=-1:1920:flags=lanczos,"
        "crop=1080:1920:(in_w-1080)/2:0"
    )

    if options.layout == "fill":
        # Main video fills the whole frame; we still apply optional title/subs
        main_v = "[v_main]"
        chain = f"{main_chain}{main_v};"
    elif options.layout == "centered":
        # Main video scaled smaller, centered over a background
        # Scale main to 810x1440 (75% of frame) — leaves a border for the bg
        main_chain_centered = (
            "[0:v]scale=810:1440:flags=lanczos:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=#00000000[main_s];"
        )
        bg_v = _build_background_filter(options, "[bg]", width=1080, height=1920)
        chain = main_chain_centered + bg_v + "[bg][main_s]overlay=0:0[main_v];"
        main_v = "[main_v]"
    else:  # 'split' (default) — video takes ~60% of the height
        # Main video scaled to fit 1080x1152 (60% of 1920), top-aligned
        main_chain_split = (
            "[0:v]scale=1080:-2:flags=lanczos,"
            "pad=1080:1920:0:0:color=#00000000[main_s];"
        )
        bg_v = _build_background_filter(options, "[bg]", width=1080, height=1920)
        chain = main_chain_split + bg_v + "[bg][main_s]overlay=0:0[main_v];"
        main_v = "[main_v]"

    # Step 2: burn subtitles (passed in via [1:v] which is the ASS file)
    if has_subs:
        chain += f"{main_v.replace('[', '[').replace(']', ']')}[1:v]overlay=0:0[v_sub];"
        last = "[v_sub]"
    else:
        last = main_v

    # Step 3: optional title at the top
    if has_title:
        # Use drawtext for the title. We embed it directly in the filter.
        # Escape single quotes in title text for ffmpeg drawtext
        title_safe = options.title_text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
        title_color_ass = _hex_to_ass(options.title_color)[2:]  # remove &H00
        # drawtext uses &HBBGGRR but with leading alpha
        title_color_ffmpeg = f"&H00{title_color_ass[4:6]}{title_color_ass[2:4]}{title_color_ass[0:2]}"
        # Actually simpler: use hex after &H
        # Convert #RRGGBB -> 0xBBGGRR for ffmpeg
        h = options.title_color.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        r, g, b = h[0:2], h[2:4], h[4:6]
        title_color_ffmpeg = f"0x{b}{g}{r}"
        # Resolve a real TTF for the drawtext filter (libass-style font name
        # is not enough; drawtext needs the literal file path).
        fontfile_for_drawtext = _detect_title_fontfile()
        if fontfile_for_drawtext:
            # Escape colons for ffmpeg's option parser (Windows C:\ issue)
            fontfile_escaped = fontfile_for_drawtext.replace("\\", "/").replace(":", "\\:")
            fontfile_part = f"fontfile='{fontfile_escaped}':"
        else:
            # Last resort: just give it a name, drawtext will use fontconfig
            fontfile_part = f"font='{_detect_subtitle_font()}':"
        drawtext = (
            f"drawtext=text='{title_safe}':"
            f"fontcolor={title_color_ffmpeg}:"
            f"fontsize={options.title_size}:"
            f"{fontfile_part}"
            f"x=(w-text_w)/2:y=120:"
            f"box=1:boxcolor=black@0.6:boxborderw=20"
        )
        chain += f"{last}{drawtext}[v_out];"
        last = "[v_out]"

    return chain


def _build_background_filter(options: RenderOptions, label: str, width: int = 1080, height: int = 1920) -> tuple[str, str]:
    """Build the background video filter chain ending in ``label``.

    Returns (filter_chain, output_label) where the chain emits a video
    stream tagged with ``output_label`` (defaults to ``label``).
    """
    if options.bg_style == "blur":
        # Heavily blurred copy of the source, scaled to fill 1080x1920.
        # Source is 1920x1080. We force-scale to 1080x1920 (stretching
        # the wider dimension), then blur it. Result is a blurred
        # widescreen-stretched background.
        return (
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={width}:{height}:(in_w-{width})/2:(in_h-{height})/2,"
            f"boxblur=30:1",
            label,
        )
    elif options.bg_style == "solid":
        # Solid color background using lavfi color source.
        h = options.bg_color.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return (
            f"color=c=0x{b:02X}{g:02X}{r:02X}:s={width}x{height}:r=25",
            label,
        )
    elif options.bg_style == "gradient":
        # Vertical gradient using lavfi's gradients source. We use
        # type=linear with x0=0,y0=0,x1=0,y1=1 to force a top-to-bottom
        # gradient (regardless of canvas size).
        h1 = options.bg_color.lstrip("#")
        h2 = options.bg_color2.lstrip("#")
        if len(h1) == 3:
            h1 = "".join(c * 2 for c in h1)
        if len(h2) == 3:
            h2 = "".join(c * 2 for c in h2)
        c1 = f"0x{h1[4:6]}{h1[2:4]}{h1[0:2]}"
        c2 = f"0x{h2[4:6]}{h2[2:4]}{h2[0:2]}"
        return (
            f"gradients=size={width}x{height}:type=linear:c0={c1}:c1={c2}:"
            f"nb_colors=2:r=25:x0=0:y0=0:x1=0:y1={height}",
            label,
        )
    elif options.bg_style == "zoom":
        # Slow Ken Burns zoom on the source: scale 2x, zoompan 1.0 -> 1.2.
        return (
            f"[0:v]scale={width*2}:{height*2}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={width*2}:{height*2}:(in_w-{width*2})/2:(in_h-{height*2})/2,"
            f"zoompan=z='1+0.0003*on':d=1:s={width}x{height}:fps=25,"
            f"boxblur=15:1",
            label,
        )
    # Fallback: solid black
    return f"color=c=black:s={width}x{height}:r=25", label


def gpu_str(label: str) -> str:
    """Helper to append the output label correctly (with comma prefix)."""
    return f",{label}"


async def _download_broll(url: str, cache_dir: Path) -> Path | None:
    """Download a B-roll image to a local cache, keyed by a hash of the URL.

    Returns None (and logs a warning) on failure — a broken B-roll source
    shouldn't fail the whole render, just skip that overlay.
    """
    import hashlib
    import httpx

    cache_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(url.split("?")[0]).suffix or ".jpg"
    key = hashlib.sha1(url.encode()).hexdigest()[:16]
    dest = cache_dir / f"{key}{ext}"
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
        return dest
    except Exception as e:
        logger.warning("broll_download_failed", url=url, error=str(e))
        return None


# ── Main render function ────────────────────────────────────────────────────

@dataclass
class RenderResult:
    output_path: str
    duration: float
    file_size: int
    width: int
    height: int
    processing_time: float


# Caps how many renders (ffmpeg encodes + face detection) run at once. Created
# lazily so it binds to whichever event loop is running when the first render
# starts, and so ``settings.vertical_render_concurrency`` can be read (and
# overridden in tests) without an import-time dependency on app.config.
_render_semaphore: asyncio.Semaphore | None = None


def _get_render_semaphore() -> asyncio.Semaphore:
    global _render_semaphore
    if _render_semaphore is None:
        from app.config import settings
        _render_semaphore = asyncio.Semaphore(max(1, settings.vertical_render_concurrency))
    return _render_semaphore


async def render_vertical(
    source_video: Path,
    source_audio: Path | None,
    output_path: Path,
    words: list[WordTimestamp],
    options: RenderOptions | None = None,
    title_text: str = "",
    duration: float | None = None,
) -> RenderResult:
    """Render a vertical 1080x1920 MP4 from a horizontal source.

    Thin wrapper around ``_render_vertical_impl`` that bounds how many
    renders run at once (see ``_get_render_semaphore``) — batch-exporting
    many clips queues them all immediately, but only
    ``settings.vertical_render_concurrency`` actually run ffmpeg/face
    detection at the same time; the rest wait their turn.
    """
    async with _get_render_semaphore():
        return await _render_vertical_impl(
            source_video, source_audio, output_path, words, options, title_text, duration,
        )


async def _render_vertical_impl(
    source_video: Path,
    source_audio: Path | None,
    output_path: Path,
    words: list[WordTimestamp],
    options: RenderOptions | None = None,
    title_text: str = "",
    duration: float | None = None,
) -> RenderResult:
    """Render a vertical 1080x1920 MP4 from a horizontal source.

    Args:
        source_video: pre-cut horizontal clip (1920x1080, 16:9)
        source_audio: pre-cut audio file. If None, audio is taken from source_video.
        output_path: where to write the final MP4
        words: list of WordTimestamp (clip-relative) for subtitles
        options: RenderOptions (uses defaults if None)
        title_text: text to display at the top (overrides options.title_text)
        duration: expected output duration in seconds (sanity check)

    Returns:
        RenderResult with paths and stats
    """
    if options is None:
        options = RenderOptions()
    if title_text:
        options.title_text = title_text
        options.add_title = True

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Resolve B-roll placements to local files (download once, cache by URL hash).
    # Placements whose download fails are dropped rather than failing the render.
    resolved_brolls: list[tuple[Path, BrollPlacement]] = []
    if options.broll_placements and options.quality != "draft":
        from app.config import settings
        cache_dir = settings.data_dir / "broll_cache"
        for bp in options.broll_placements:
            local_path = await _download_broll(bp.url, cache_dir)
            if local_path:
                resolved_brolls.append((local_path, bp))

    # Build ASS file
    # Styles that use word-by-word highlighting (each spoken word is the
    # "active" one and gets a special effect). Other styles use line-level
    # subs without per-word animation.
    # In draft mode we keep the ASS filter — the user is iterating on
    # the editor and the subtitle style is one of the most-edited fields.
    # The micro-benchmark in _bench_subs.py confirmed that on this codebase
    # the ass= filter is not the bottleneck (draft WITH subs: 14.6s, draft
    # WITHOUT subs: 18.0s — the bottleneck is the 1080→480 downscale).
    WORD_BY_WORD_STYLES = {"karaoke", "mrbeast", "hormozi", "tiktok_classic", "neon"}
    if options.sub_style in WORD_BY_WORD_STYLES:
        ass_text = build_ass_karaoke_from_words(
            words,
            chunk_size=5,
            sub_style=options.sub_style,
            text_color=options.sub_color,
            highlight_color=options.sub_highlight,
            outline_color=options.sub_outline,
            font_size=options.sub_size,
            bottom_margin=options.sub_position,
        )
    else:
        # Group words into lines for standard (and any future "static" style)
        entries = group_words_into_lines(words, max_words=6, max_duration=3.5)
        ass_text = build_ass_subtitles(
            entries,
            style=options.sub_style,
            text_color=options.sub_color,
            highlight_color=options.sub_highlight,
            outline_color=options.sub_outline,
            font_size=options.sub_size,
            bottom_margin=options.sub_position,
        )

    # Write ASS to a file next to the source (use simple ASCII-safe name
    # to avoid ffmpeg's path-parsing issues on Windows)
    ass_path = output_path.parent / (output_path.stem + ".ass")
    # ASS files are UTF-8; ensure no BOM
    ass_path.write_text(ass_text, encoding="utf-8")
    has_subs = any(line.strip() for line in ass_text.split("\n") if line.startswith("Dialogue"))

    # Phase 10: if layout is "auto", run face detection on the source video
    # to build a dynamic crop trajectory that follows the speaker.
    auto_crop_expr: str | None = None
    if options.layout == "auto":
        from app.services.face_detection import detect_face_trajectory, trajectory_to_ffmpeg_crop
        # We need the source video dimensions to build the crop expression
        import cv2 as _cv2
        _cap = _cv2.VideoCapture(str(source_video))
        _src_w = int(_cap.get(_cv2.CAP_PROP_FRAME_WIDTH))
        _src_h = int(_cap.get(_cv2.CAP_PROP_FRAME_HEIGHT))
        _cap.release()
        logger.info("auto_reframe_start", source=str(source_video), src_size=f"{_src_w}x{_src_h}")
        keyframes, face_summary = detect_face_trajectory(source_video)
        if face_summary.fallback or not keyframes:
            logger.info("auto_reframe_fallback_to_fill", reason="no_faces_detected")
        else:
            auto_crop_expr = trajectory_to_ffmpeg_crop(keyframes, _src_w, _src_h)
            logger.info(
                "auto_reframe_trajectory_built",
                keyframes=len(keyframes),
                detection_rate=face_summary.detection_rate,
                crop_expr_len=len(auto_crop_expr),
            )

    # Build filter complex (use the simple single-input version)
    filter_str = _build_simple_filter(
        options, ass_path.name, has_subs,
        auto_crop_expr=auto_crop_expr,
    )

    # Determine the final output video label (used for -map). Stage order is
    # v_main -> v_sub (subs) -> v_out (title) -> v_broll{N} (b-rolls) -> v_wm (watermark).
    # In draft mode the watermark (and b-rolls) stages are skipped, so the
    # label must NOT point at [v_wm] — otherwise the -map / draft-downscale
    # step references a filtergraph label that was never produced and ffmpeg
    # aborts with "Output pad ... does not exist".
    is_draft = options.quality == "draft"
    if not is_draft and options.watermark_path and Path(options.watermark_path).exists():
        final_v = "[v_wm]"
    elif resolved_brolls:
        final_v = f"[v_broll{len(resolved_brolls) - 1}]"
    elif options.add_title and options.title_text:
        final_v = "[v_out]"
    elif has_subs:
        final_v = "[v_sub]"
    elif options.video_transform is not None and not options.video_transform.is_identity():
        final_v = "[v_main_t]"
    else:
        final_v = "[v_main]"

    # Determine which input has the audio we want. The watermark (if any)
    # is appended as the LAST input, so we count the other inputs.
    inputs_after_video: list[Path] = []
    if source_audio and source_audio.exists():
        inputs_after_video.append(Path(source_audio).resolve())
    if options.watermark_path and Path(options.watermark_path).exists():
        inputs_after_video.append(Path(options.watermark_path).resolve())
    audio_idx = 0  # default: audio comes from the video input
    if source_audio and source_audio.exists():
        audio_idx = 1  # audio is the first non-video input

    # Pass the ASS path. ffmpeg's filter parser splits arguments on `:`
    # for options like `original_size`, which breaks Windows paths like
    # "C:\...". The cleanest fix: write the ASS file next to the output
    # (in the same directory) and pass just the basename. ffmpeg runs with
    # cwd = output_path.parent, so a bare filename resolves correctly.
    ass_path_str = ass_path.name  # just the filename, no directory

    cmd = [
        _ffmpeg(), "-y", "-loglevel", "warning",
        "-i", str(Path(source_video).resolve()),
    ]
    if source_audio and source_audio.exists():
        cmd += ["-i", str(Path(source_audio).resolve())]
    # Watermark input (if any). The filter references it as [N:v] where N
    # is the index of this input. We count the number of -i occurrences so far.
    # In draft mode the watermark is skipped — the user is iterating quickly
    # and the watermark PNG decode is wasted work.
    watermark_input_idx: int | None = None
    if options.quality != "draft" and options.watermark_path and Path(options.watermark_path).exists():
        # Count "-i" in cmd; that's how many inputs we have so far.
        # The next input (this one) will be at that index (0-based).
        n_inputs_so_far = sum(1 for c in cmd if c == "-i")
        watermark_input_idx = n_inputs_so_far  # 0-based index
        cmd += ["-i", str(Path(options.watermark_path).resolve())]
    # B-roll inputs (Phase 3): one extra -i per resolved placement, in order.
    # Skipped entirely in draft mode — the download + the overlay both add
    # latency, and the user is still deciding what to keep.
    broll_inputs: list[tuple[int, BrollPlacement]] = []
    if options.quality != "draft":
        for local_path, bp in resolved_brolls:
            n_inputs_so_far = sum(1 for c in cmd if c == "-i")
            broll_inputs.append((n_inputs_so_far, bp))
            cmd += ["-i", str(local_path.resolve())]
    # Re-build filter with the escape-safe ASS path
    filter_str_abs = _build_simple_filter(
        options, ass_path_str, has_subs, watermark_input_idx,
        auto_crop_expr=auto_crop_expr, broll_inputs=broll_inputs,
    )
    # Draft mode: append a final downscale step so the encoder doesn't waste
    # cycles producing 1080p pixels the user is just going to glance at. We
    # rename the final output label to [v_final] after the scale so the -map
    # below can pick it up.
    if options.quality == "draft":
        filter_str_abs = filter_str_abs + f"{final_v}scale=480:854:flags=fast_bilinear[v_final];"
        final_v = "[v_final]"
    cmd += [
        "-filter_complex", filter_str_abs,
        # Map ONLY the final video output and the chosen audio. The combination
        # of "-map [v_out]" + "-map N:a:0?" can cause ffmpeg to also include
        # the source video stream as a second video track on some ffmpeg builds
        # (this is what produced the 1920x1080 second video stream we saw).
        # The -dn flag explicitly drops any data streams. The -map flags pin
        # exactly which streams go into the output, preventing duplicates.
        "-dn",
    ]
    # Video encoder: use GPU-accelerated encoder when available
    # (h264_nvenc on NVIDIA, h264_videotoolbox on macOS, h264_qsv on Intel)
    # for 5-10x faster encoding. Fall back to libx264 on CPU.
    from app.utils.hardware import detect_hardware
    hw = detect_hardware()
    encoder = hw.ffmpeg_encoder
    if options.quality == "draft":
        # Draft preview: prioritize speed over quality. Use ultrafast preset
        # and a high CRF so the encode takes seconds, not 20s. We still
        # pick the GPU encoder when available — on NVIDIA it can draft
        # a 30s clip in <2s.
        if encoder == "h264_nvenc":
            encoder_opts = ["-preset", "p1", "-rc", "vbr", "-cq", "30", "-b:v", "0"]
        else:
            encoder_opts = ["-preset", "ultrafast", "-crf", "30"]
    elif encoder == "h264_nvenc":
        # NVENC-specific options: preset for speed/quality tradeoff
        encoder_opts = ["-preset", "p4", "-rc", "vbr", "-cq", "22", "-b:v", "0"]
    elif encoder == "h264_videotoolbox":
        # macOS VideoToolbox: bitrate-based
        encoder_opts = ["-b:v", "5000k", "-allow_sw", "1"]
    elif encoder == "h264_qsv":
        # Intel QuickSync
        encoder_opts = ["-preset", "fast"]
    else:
        # CPU fallback
        encoder_opts = ["-preset", "veryfast", "-crf", "22"]
    cmd += [
        "-map", final_v,
        "-map", f"{audio_idx}:a:0?",
        "-c:v", encoder, *encoder_opts,
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-shortest",  # in case audio is shorter than video
        str(Path(output_path).resolve()),
    ]
    logger.info("vertical_encoder_chosen", encoder=encoder, hw=hw.os)

    # Run ffmpeg from the output directory so the relative ASS path works
    cwd = output_path.parent
    start = time.time()
    loop = asyncio.get_event_loop()
    logger.info("vertical_render_starting",
                source=str(source_video),
                output=str(output_path),
                layout=options.layout,
                bg=options.bg_style,
                sub=options.sub_style)

    def _run() -> subprocess.CompletedProcess:
        return subprocess.run(cmd, capture_output=True, text=True, cwd=str(cwd), timeout=300)

    result = await loop.run_in_executor(None, _run)
    elapsed = time.time() - start

    if result.returncode != 0:
        # Log the full stderr for debugging
        logger.error("vertical_render_failed", stderr=result.stderr[-2000:])
        raise RuntimeError(f"ffmpeg failed: {result.stderr[-1000:]}")

    # Verify the output
    if not output_path.exists() or output_path.stat().st_size < 1024:
        raise RuntimeError(f"Output file is missing or too small: {output_path}")

    # Probe for stats
    probe_cmd = [
        _ffmpeg().replace("ffmpeg", "ffprobe"), "-v", "error",
        "-show_entries", "format=duration,size:stream=codec_name,width,height",
        "-of", "csv=p=0",
        str(output_path),
    ]
    probe = await loop.run_in_executor(
        None, lambda: subprocess.run(probe_cmd, capture_output=True, text=True, timeout=10)
    )
    # Parse: lines alternate between video and audio stream, then format.
    # e.g.:
    #   h264,1080,1920
    #   aac
    #   29.4,5796480
    out_duration = 0.0
    width, height = 0, 0
    for line in probe.stdout.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        try:
            if len(parts) >= 3 and parts[0] == "h264":
                width = int(parts[1])
                height = int(parts[2])
            elif len(parts) == 2:
                # format line: duration,size
                out_duration = float(parts[0])
        except (ValueError, IndexError):
            continue
    file_size = output_path.stat().st_size

    if duration and abs(out_duration - duration) > 1.0:
        logger.warning("vertical_duration_mismatch",
                       expected=duration, actual=out_duration)

    logger.info("vertical_render_done",
                output=str(output_path),
                size_mb=round(file_size / 1024 / 1024, 2),
                duration=out_duration,
                width=width, height=height,
                processing_time=round(elapsed, 2))

    # Cleanup ASS file (no longer needed)
    try:
        ass_path.unlink()
    except OSError:
        pass

    return RenderResult(
        output_path=str(output_path),
        duration=out_duration,
        file_size=file_size,
        width=width,
        height=height,
        processing_time=elapsed,
    )


def _build_simple_filter(
    options: RenderOptions,
    ass_filename: str,
    has_subs: bool,
    watermark_input_idx: int | None = None,
    auto_crop_expr: str | None = None,
    broll_inputs: list[tuple[int, BrollPlacement]] | None = None,
) -> str:
    """Build a single-pass ffmpeg filter that converts 16:9 -> 9:16 with
    background, subtitles, and optional title.

    The filter is a `filter_complex` string. Each stage is a separate
    filter instance joined by `;` chains. Labels are introduced with
    `[label]` and consumed with the same label.

    For `fill` layout: no background, the source video is just cropped
    to 9:16 (center 1080x1920 of the 1920x1080 source, scaled to height).

    For `centered` and `split` layouts: a background is generated and the
    main video is overlaid on top.

    For `auto` layout (Phase 10): the source video is dynamically cropped
    following the speaker's face using the ``auto_crop_expr`` (a ffmpeg
    ``crop=`` expression with time-varying x/y). If ``auto_crop_expr`` is
    None or empty, falls back to ``fill``.
    """
    parts: list[str] = []

    # ── Stage 1: prepare the main video (always 1080x1920 vertical crop) ──
    if options.layout == "auto" and auto_crop_expr:
        # Auto-reframe: dynamic crop following the speaker's face, then
        # scale to 1080x1920. The crop expression is pre-built by
        # face_detection.trajectory_to_ffmpeg_crop().
        # We escape commas in the expression so they don't break ffmpeg's
        # filter chain parsing (commas separate filters in filter_complex).
        # Note: this ffmpeg build doesn't support eval=frame, but crop
        # evaluates expressions per-frame by default when they reference 't'.
        escaped_crop = auto_crop_expr.replace(",", "\\,")
        parts.append(
            f"[0:v]{escaped_crop},scale=1080:1920:flags=lanczos[v_main]"
        )
        main_label = "v_main"
    elif options.layout == "fill" or (options.layout == "auto" and not auto_crop_expr):
        # Fill: video takes the whole frame, just crop+scale to 9:16.
        # Source 1920x1080 -> scale to 3413x1920, crop center 1080x1920.
        # Also used as fallback when 'auto' has no trajectory.
        parts.append(
            "[0:v]scale=-1:1920:flags=lanczos,"
            "crop=1080:1920:(in_w-1080)/2:0[v_main]"
        )
        main_label = "v_main"
    elif options.layout == "centered":
        # Background: full 1080x1920
        bg_chain, bg_label = _build_background_filter(options, "vbg", 1080, 1920)
        parts.append(f"{bg_chain}[{bg_label}]")
        # Main: scale to 810x1440 (75% of frame), pad to 1080x1920 centered
        parts.append(
            "[0:v]scale=810:1440:force_original_aspect_ratio=decrease:flags=lanczos,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=#00000000[vmain_s]"
        )
        # Overlay main on background
        parts.append(f"[vbg][vmain_s]overlay=0:0[v_main]")
        main_label = "v_main"
    else:  # 'split' (default) — video takes top ~60% of frame
        # Background: full 1080x1920
        bg_chain, bg_label = _build_background_filter(options, "vbg", 1080, 1920)
        parts.append(f"{bg_chain}[{bg_label}]")
        # Main: scale to fit width 1080, top-aligned
        parts.append(
            "[0:v]scale=1080:-2:flags=lanczos,"
            "pad=1080:1920:0:0:color=#00000000[vmain_s]"
        )
        # Overlay main on background
        parts.append(f"[vbg][vmain_s]overlay=0:0[v_main]")
        main_label = "v_main"

    # ── Stage 1.5: optional video transform (translate / scale / rotate) ──
    # Operates on the already-prepared 1080x1920 [v_main]. We scale + rotate
    # the content, then composite it onto an opaque black 1080x1920 base at the
    # requested centre offset, so the output stays exactly 1080x1920.
    if options.video_transform is not None and not options.video_transform.is_identity():
        t = options.video_transform
        angle_rad = math.radians(t.rotation)
        scale_factor = max(0.1, t.scale / 100.0)
        parts.append(
            f"[{main_label}]format=rgba,"
            f"scale=iw*{scale_factor}:ih*{scale_factor}:flags=lanczos,"
            f"rotate={angle_rad}:fillcolor=black@0:ow=rotw:oh=roth[v_main_tx];"
            f"color=c=black:s=1080x1920:r=30,format=rgba[v_main_base];"
            f"[v_main_base][v_main_tx]overlay="
            f"x='(W-w)/2+({t.x})':y='(H-h)/2+({t.y})':shortest=1[v_main_t]"
        )
        main_label = "v_main_t"

    # ── Stage 2: burn subtitles using the 'ass' filter ──
    last_label = f"[{main_label}]"
    if has_subs:
        # ass= takes a path; ffmpeg runs in the output dir so the filename
        # is relative.
        parts.append(f"{last_label}ass={ass_filename}[v_sub]")
        last_label = "[v_sub]"

    # ── Stage 3: optional title with drawtext ──
    if options.add_title and options.title_text:
        # Escape for ffmpeg drawtext: \ ' :
        title_safe = (
            options.title_text
            .replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace(":", "\\:")
            .replace("%", "%%")
        )
        # Convert #RRGGBB to 0xBBGGRR (ffmpeg drawtext uses BGR)
        h = options.title_color.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        r, g, b = h[0:2], h[2:4], h[4:6]
        title_color_ffmpeg = f"0x{b}{g}{r}"
        # Resolve a real TTF for the drawtext filter (libass-style font name
        # is not enough; drawtext needs the literal file path).
        fontfile_for_drawtext = _detect_title_fontfile()
        if fontfile_for_drawtext:
            fontfile_escaped = fontfile_for_drawtext.replace("\\", "/").replace(":", "\\:")
            fontfile_part = f"fontfile='{fontfile_escaped}':"
        else:
            fontfile_part = f"font='{_detect_subtitle_font()}':"
        # Vertical placement of the title. drawtext exposes `h` (frame height)
        # and `text_h` (rendered text height) so the expression self-centers
        # regardless of font size / wrapping.
        title_y = {
            "center": "(h-text_h)/2",
            "bottom": "h-text_h-220",
        }.get(options.title_position, "140")  # default 'top'
        drawtext = (
            f"drawtext=text='{title_safe}':"
            f"fontcolor={title_color_ffmpeg}:"
            f"fontsize={options.title_size}:"
            f"{fontfile_part}"
            f"x=(w-text_w)/2:y={title_y}:"
            f"box=1:boxcolor=black@0.55:boxborderw=24"
        )
        parts.append(f"{last_label}{drawtext}[v_out]")
        last_label = "[v_out]"

    # ── Stage 3.5: optional B-roll image cutaways (full-bleed, time-windowed) ──
    if broll_inputs:
        for idx, (input_idx, bp) in enumerate(broll_inputs):
            opacity = max(0.0, min(1.0, bp.opacity))
            in_label = f"broll{idx}"
            out_label = f"v_broll{idx}"
            # Escape commas in the enable expression — commas separate
            # filters within a chain in ffmpeg's filtergraph syntax.
            enable_expr = f"between(t\\,{bp.start}\\,{bp.end})"
            parts.append(
                f"[{input_idx}:v]scale=1080:1920:force_original_aspect_ratio=increase,"
                f"crop=1080:1920,format=rgba,"
                f"colorchannelmixer=aa={opacity}[{in_label}];"
                f"{last_label}[{in_label}]overlay=0:0:enable='{enable_expr}'[{out_label}]"
            )
            last_label = f"[{out_label}]"

    # ── Stage 4: optional watermark image (PNG overlay) ──
    if options.watermark_path and Path(options.watermark_path).exists() and watermark_input_idx is not None:
        # Position calculations: 100px margin from the edge, watermark
        # is scaled to ~25% of the frame width to be visible but not intrusive.
        wm_size = 270  # pixels wide (1080 * 0.25)
        margin = 60
        pos_map = {
            "top_left":      f"x={margin}:y={margin}",
            "top_center":    f"x=(W-w)/2:y={margin}",
            "top_right":     f"x=W-w-{margin}:y={margin}",
            "center_left":   f"x={margin}:y=(H-h)/2",
            "center":        f"x=(W-w)/2:y=(H-h)/2",
            "center_right":  f"x=W-w-{margin}:y=(H-h)/2",
            "bottom_left":   f"x={margin}:y=H-h-{margin}",
            "bottom_center": f"x=(W-w)/2:y=H-h-{margin}",
            "bottom_right":  f"x=W-w-{margin}:y=H-h-{margin}",
        }
        position = pos_map.get(options.watermark_position, pos_map["bottom_right"])
        opacity = max(0.0, min(1.0, options.watermark_opacity))
        # Apply the overlay: scale the PNG, ensure RGBA, set its alpha, blend
        parts.append(
            f"[{watermark_input_idx}:v]scale={wm_size}:-1,"
            f"format=rgba,"
            f"colorchannelmixer=aa={opacity}[wm];"
            f"{last_label}[wm]overlay={position}[v_wm]"
        )
        last_label = "[v_wm]"

    # Join all stages with `;`
    return ";".join(parts) + ";"
