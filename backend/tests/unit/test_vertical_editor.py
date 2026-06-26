"""Unit tests for the pure (no ffmpeg/filesystem) logic in
``app.services.vertical_editor_service``: ASS subtitle generation, color/time
conversion, word grouping, and ffmpeg filter string building.

``render_vertical()`` itself (real ffmpeg invocation) is intentionally NOT
covered here — see ``tests/qa_vertical_editor_matrix.py`` for that.
"""
import pytest

import asyncio

import app.services.vertical_editor_service as vertical_editor_service
from app.services.vertical_editor_service import (
    BrollPlacement,
    RenderOptions,
    SubtitleEntry,
    WordTimestamp,
    _ass_time,
    _build_background_filter,
    _build_simple_filter,
    _escape_ass_text,
    _get_render_semaphore,
    _hex_to_ass,
    _style_line_hormozi,
    _style_line_mrbeast,
    _style_line_neon,
    _style_line_standard,
    _style_line_tiktok_classic,
    build_ass_karaoke_from_words,
    build_ass_style_line,
    build_ass_subtitles,
    extract_words_for_clip,
    group_words_into_lines,
)


# ── _ass_time ────────────────────────────────────────────────────────────────

class TestAssTime:
    def test_zero(self):
        assert _ass_time(0) == "0:00:00.00"

    def test_seconds_and_centiseconds(self):
        assert _ass_time(65.5) == "0:01:05.50"

    def test_hours(self):
        assert _ass_time(3661.25) == "1:01:01.25"

    def test_negative_clamps_to_zero(self):
        assert _ass_time(-5) == "0:00:00.00"

    def test_centisecond_rounding_clamped_to_99(self):
        # (1.999 - 1) * 100 rounds to 100, which must clamp to 99 (not roll
        # over into a fake "100" centisecond field).
        assert _ass_time(1.999) == "0:00:01.99"


# ── _hex_to_ass ──────────────────────────────────────────────────────────────

class TestHexToAss:
    def test_white(self):
        assert _hex_to_ass("#FFFFFF") == "&H00FFFFFF"

    def test_red_is_bgr_ordered(self):
        assert _hex_to_ass("#FF0000") == "&H000000FF"

    def test_black(self):
        assert _hex_to_ass("#000000") == "&H00000000"

    def test_short_hex_expands(self):
        assert _hex_to_ass("#FFF") == "&H00FFFFFF"

    def test_lowercase_input_uppercased_output(self):
        assert _hex_to_ass("#ffd700") == "&H0000D7FF"


# ── _escape_ass_text ─────────────────────────────────────────────────────────

class TestEscapeAssText:
    def test_plain_text_unchanged(self):
        assert _escape_ass_text("hello world") == "hello world"

    def test_escapes_backslash(self):
        assert _escape_ass_text("a\\b") == "a\\\\b"

    def test_escapes_braces(self):
        assert _escape_ass_text("{tag}") == "\\{tag\\}"

    def test_escapes_combined(self):
        assert _escape_ass_text("\\{x}") == "\\\\\\{x\\}"


# ── ASS style line builders ───────────────────────────────────────────────────

class TestStyleLineBuilders:
    """Every builder must emit a well-formed 23-field ASS Style line with the
    primary color in field index 3 (per the [V4+ Styles] Format header)."""

    @pytest.mark.parametrize("builder", [
        _style_line_standard, _style_line_neon, _style_line_mrbeast,
        _style_line_hormozi, _style_line_tiktok_classic,
    ])
    def test_well_formed_23_fields(self, builder):
        line = builder(64, "&H00FFFFFF", "&H00000000", 200)
        assert line.startswith("Style: Default,")
        fields = line.split(",")
        assert len(fields) == 23
        assert fields[3] == "&H00FFFFFF"  # PrimaryColour

    def test_standard_uses_outline_param_as_outline_colour(self):
        line = _style_line_standard(64, "&H00FFFFFF", "&H00ABCDEF", 200)
        assert line.split(",")[5] == "&H00ABCDEF"

    def test_mrbeast_uses_outline_param_as_outline_colour(self):
        line = _style_line_mrbeast(64, "&H00FFFFFF", "&H00ABCDEF", 200)
        assert line.split(",")[5] == "&H00ABCDEF"

    def test_tiktok_classic_uses_outline_param_as_outline_colour(self):
        line = _style_line_tiktok_classic(64, "&H00FFFFFF", "&H00ABCDEF", 200)
        assert line.split(",")[5] == "&H00ABCDEF"

    def test_hormozi_hardcodes_white_outline_regardless_of_param(self):
        # By design (see docstring): Hormozi always uses a thick white
        # outline, ignoring the caller's outline color.
        line = _style_line_hormozi(64, "&H00FFFFFF", "&H00ABCDEF", 200)
        assert line.split(",")[5] == "&H00FFFFFF"

    def test_bottom_margin_is_last_numeric_field(self):
        line = _style_line_standard(64, "&H00FFFFFF", "&H00000000", 321)
        assert line.split(",")[21] == "321"


class TestBuildAssStyleLine:
    def test_dispatches_to_correct_builder(self):
        line = build_ass_style_line("mrbeast", 64, "#FFFFFF", "#000000")
        assert line == _style_line_mrbeast(64, "&H00FFFFFF", "&H00000000", 200)

    def test_unknown_style_falls_back_to_standard(self):
        line = build_ass_style_line("not-a-real-style", 64, "#FFFFFF", "#000000")
        assert line == _style_line_standard(64, "&H00FFFFFF", "&H00000000", 200)

    def test_custom_bottom_margin_propagates(self):
        line = build_ass_style_line("standard", 64, "#FFFFFF", "#000000", bottom_margin=500)
        assert line.split(",")[21] == "500"


# ── build_ass_subtitles ───────────────────────────────────────────────────────

class TestBuildAssSubtitles:
    def test_header_contains_playres(self):
        ass = build_ass_subtitles([], width=1080, height=1920)
        assert "PlayResX: 1080" in ass
        assert "PlayResY: 1920" in ass

    def test_empty_entries_no_dialogue_lines(self):
        ass = build_ass_subtitles([])
        assert "Dialogue:" not in ass

    def test_entry_produces_dialogue_line(self):
        ass = build_ass_subtitles([SubtitleEntry(start=1.0, end=2.0, text="hola mundo")])
        assert "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,hola mundo" in ass

    def test_zero_or_negative_duration_entry_skipped(self):
        ass = build_ass_subtitles([SubtitleEntry(start=2.0, end=2.0, text="skip me")])
        assert "skip me" not in ass

    def test_blank_text_entry_skipped(self):
        ass = build_ass_subtitles([SubtitleEntry(start=1.0, end=2.0, text="   ")])
        assert "Dialogue:" not in ass

    def test_text_is_escaped(self):
        ass = build_ass_subtitles([SubtitleEntry(start=0.0, end=1.0, text="{weird}")])
        assert "\\{weird\\}" in ass

    @pytest.mark.parametrize("style,expected_fragment", [
        ("mrbeast", "\\t(0,80,"),
        ("hormozi", "\\fad(120,80)"),
        ("tiktok_classic", "\\fad(200,0)"),
    ])
    def test_animated_styles_add_effect_prefix(self, style, expected_fragment):
        ass = build_ass_subtitles([SubtitleEntry(start=0.0, end=1.0, text="hi")], style=style)
        assert expected_fragment in ass

    def test_standard_style_has_no_effect_prefix(self):
        ass = build_ass_subtitles([SubtitleEntry(start=0.0, end=1.0, text="hi")], style="standard")
        assert "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,hi" in ass


# ── build_ass_karaoke_from_words ──────────────────────────────────────────────

class TestBuildAssKaraokeFromWords:
    def test_empty_words_no_dialogue(self):
        ass = build_ass_karaoke_from_words([])
        assert "Dialogue:" not in ass

    def test_single_word_chunk_emits_one_dialogue_line(self):
        words = [WordTimestamp(start=0.0, end=0.5, word="hola")]
        ass = build_ass_karaoke_from_words(words, chunk_size=5)
        dialogue_lines = [l for l in ass.splitlines() if l.startswith("Dialogue:")]
        assert len(dialogue_lines) == 1
        assert "hola" in dialogue_lines[0]

    def test_multi_word_chunk_emits_one_dialogue_per_word(self):
        words = [
            WordTimestamp(start=0.0, end=0.3, word="uno"),
            WordTimestamp(start=0.3, end=0.6, word="dos"),
            WordTimestamp(start=0.6, end=0.9, word="tres"),
        ]
        ass = build_ass_karaoke_from_words(words, chunk_size=5)
        dialogue_lines = [l for l in ass.splitlines() if l.startswith("Dialogue:")]
        assert len(dialogue_lines) == 3
        # The last line (active word = "tres") must show all 3 words.
        assert all(w in dialogue_lines[-1] for w in ("uno", "dos", "tres"))

    def test_clip_offset_makes_times_relative(self):
        words = [WordTimestamp(start=100.0, end=100.5, word="hola")]
        ass = build_ass_karaoke_from_words(words, chunk_size=5, clip_offset=100.0)
        assert "0:00:00.00" in ass

    def test_chunking_splits_into_multiple_groups(self):
        words = [WordTimestamp(start=i * 0.2, end=i * 0.2 + 0.1, word=f"w{i}") for i in range(7)]
        ass = build_ass_karaoke_from_words(words, chunk_size=5)
        # 7 words / chunk_size=5 -> chunks of 5 and 2 -> 5 + 2 = 7 dialogue lines
        dialogue_lines = [l for l in ass.splitlines() if l.startswith("Dialogue:")]
        assert len(dialogue_lines) == 7

    @pytest.mark.parametrize("style,fragment", [
        ("mrbeast", "\\1c&H000000FF&"),
        ("tiktok_classic", "\\1c&H0000FFFF&"),
    ])
    def test_style_specific_active_word_tag(self, style, fragment):
        words = [WordTimestamp(start=0.0, end=0.5, word="hola")]
        ass = build_ass_karaoke_from_words(words, sub_style=style)
        assert fragment in ass


# ── extract_words_for_clip ────────────────────────────────────────────────────

class TestExtractWordsForClip:
    def test_word_fully_outside_clip_excluded(self):
        segments = [{"words": [{"start": 50.0, "end": 50.5, "word": "afuera"}]}]
        assert extract_words_for_clip(segments, 0.0, 10.0) == []

    def test_word_inside_clip_made_relative(self):
        segments = [{"words": [{"start": 12.0, "end": 12.5, "word": "hola"}]}]
        out = extract_words_for_clip(segments, 10.0, 20.0)
        assert len(out) == 1
        assert out[0].start == pytest.approx(2.0)
        assert out[0].end == pytest.approx(2.5)
        assert out[0].word == "hola"

    def test_word_partially_overlapping_start_is_clipped(self):
        segments = [{"words": [{"start": 8.0, "end": 11.0, "word": "mundo"}]}]
        out = extract_words_for_clip(segments, 10.0, 20.0)
        assert len(out) == 1
        assert out[0].start == pytest.approx(0.0)
        assert out[0].end == pytest.approx(1.0)

    def test_tiny_sliver_skipped(self):
        segments = [{"words": [{"start": 9.99, "end": 10.005, "word": "x"}]}]
        assert extract_words_for_clip(segments, 10.0, 20.0) == []

    def test_multiple_segments_aggregated(self):
        segments = [
            {"words": [{"start": 1.0, "end": 1.5, "word": "a"}]},
            {"words": [{"start": 2.0, "end": 2.5, "word": "b"}]},
        ]
        out = extract_words_for_clip(segments, 0.0, 10.0)
        assert [w.word for w in out] == ["a", "b"]

    def test_segment_without_words_key_handled(self):
        segments = [{"text": "no words here"}]
        assert extract_words_for_clip(segments, 0.0, 10.0) == []


# ── group_words_into_lines ────────────────────────────────────────────────────

class TestGroupWordsIntoLines:
    def test_empty_returns_empty(self):
        assert group_words_into_lines([]) == []

    def test_short_list_becomes_one_line(self):
        words = [WordTimestamp(start=0.0, end=0.5, word="hola"),
                  WordTimestamp(start=0.5, end=1.0, word="mundo")]
        lines = group_words_into_lines(words)
        assert len(lines) == 1
        assert lines[0].text == "hola mundo"
        assert lines[0].start == 0.0
        assert lines[0].end == 1.0

    def test_breaks_on_max_words(self):
        words = [WordTimestamp(start=i * 0.1, end=i * 0.1 + 0.05, word=f"w{i}") for i in range(8)]
        lines = group_words_into_lines(words, max_words=6, max_duration=999)
        assert len(lines) == 2
        assert len(lines[0].text.split()) == 6
        assert len(lines[1].text.split()) == 2

    def test_breaks_on_max_duration(self):
        words = [
            WordTimestamp(start=0.0, end=0.5, word="a"),
            WordTimestamp(start=4.0, end=4.5, word="b"),
        ]
        lines = group_words_into_lines(words, max_words=999, max_duration=3.5)
        assert len(lines) == 2

    def test_breaks_on_sentence_end_punctuation(self):
        words = [
            WordTimestamp(start=0.0, end=0.5, word="Hola."),
            WordTimestamp(start=0.5, end=1.0, word="Mundo"),
        ]
        lines = group_words_into_lines(words, max_words=999, max_duration=999)
        assert len(lines) == 2
        assert lines[0].text == "Hola."
        assert lines[1].text == "Mundo"


# ── _build_background_filter ──────────────────────────────────────────────────

class TestBuildBackgroundFilter:
    def test_blur(self):
        opts = RenderOptions(bg_style="blur")
        chain, label = _build_background_filter(opts, "vbg", 1080, 1920)
        assert label == "vbg"
        assert "boxblur=30:1" in chain

    def test_solid_color_conversion(self):
        opts = RenderOptions(bg_style="solid", bg_color="#1a1a2e")
        chain, _ = _build_background_filter(opts, "vbg")
        assert "color=c=0x2E1A1A" in chain

    def test_gradient_color_conversion(self):
        opts = RenderOptions(bg_style="gradient", bg_color="#1a1a2e", bg_color2="#16213e")
        chain, _ = _build_background_filter(opts, "vbg")
        assert "c0=0x2e1a1a" in chain
        assert "c1=0x3e2116" in chain

    def test_zoom(self):
        opts = RenderOptions(bg_style="zoom")
        chain, _ = _build_background_filter(opts, "vbg")
        assert "zoompan" in chain
        assert "boxblur=15:1" in chain

    def test_unknown_style_falls_back_to_black(self):
        opts = RenderOptions()
        opts.bg_style = "not-a-real-style"  # bypass the Literal type at runtime
        chain, label = _build_background_filter(opts, "vbg")
        assert chain == "color=c=black:s=1080x1920:r=25"
        assert label == "vbg"


# ── _build_simple_filter ───────────────────────────────────────────────────────

class TestBuildSimpleFilter:
    def test_fill_layout_no_background(self):
        opts = RenderOptions(layout="fill")
        f = _build_simple_filter(opts, "subs.ass", has_subs=False)
        assert "[0:v]scale=-1:1920" in f
        assert "crop=1080:1920:(in_w-1080)/2:0[v_main]" in f

    def test_centered_layout_has_background_and_overlay(self):
        opts = RenderOptions(layout="centered", bg_style="blur")
        f = _build_simple_filter(opts, "subs.ass", has_subs=False)
        assert "boxblur=30:1" in f
        assert "overlay=0:0[v_main]" in f

    def test_split_layout_has_background_and_overlay(self):
        opts = RenderOptions(layout="split", bg_style="solid")
        f = _build_simple_filter(opts, "subs.ass", has_subs=False)
        assert "color=c=0x" in f
        assert "overlay=0:0[v_main]" in f

    def test_auto_layout_with_crop_expr_uses_it(self):
        opts = RenderOptions(layout="auto")
        f = _build_simple_filter(opts, "subs.ass", has_subs=False, auto_crop_expr="crop=800:1920:10,20")
        assert "crop=800:1920:10\\,20" in f  # commas escaped for filter_complex

    def test_auto_layout_without_crop_expr_falls_back_to_fill(self):
        opts = RenderOptions(layout="auto")
        f = _build_simple_filter(opts, "subs.ass", has_subs=False, auto_crop_expr=None)
        assert "crop=1080:1920:(in_w-1080)/2:0[v_main]" in f

    def test_has_subs_appends_ass_filter(self):
        opts = RenderOptions(layout="fill")
        f = _build_simple_filter(opts, "my_subs.ass", has_subs=True)
        assert "ass=my_subs.ass[v_sub]" in f

    def test_no_subs_no_ass_filter(self):
        opts = RenderOptions(layout="fill")
        f = _build_simple_filter(opts, "my_subs.ass", has_subs=False)
        assert "ass=" not in f

    def test_title_adds_drawtext(self):
        opts = RenderOptions(layout="fill", add_title=True, title_text="Hello: World")
        f = _build_simple_filter(opts, "subs.ass", has_subs=False)
        assert "drawtext=text='Hello\\: World'" in f

    def test_no_title_text_skips_drawtext(self):
        opts = RenderOptions(layout="fill", add_title=True, title_text="")
        f = _build_simple_filter(opts, "subs.ass", has_subs=False)
        assert "drawtext=" not in f

    @pytest.mark.parametrize("position,expected_y", [
        ("top",    "y=140"),
        ("center", "y=(h-text_h)/2"),
        ("bottom", "y=h-text_h-220"),
    ])
    def test_title_position_sets_drawtext_y(self, position, expected_y):
        opts = RenderOptions(
            layout="fill", add_title=True, title_text="Hi", title_position=position,
        )
        f = _build_simple_filter(opts, "subs.ass", has_subs=False)
        assert expected_y in f

    def test_broll_inputs_add_time_windowed_overlay(self):
        opts = RenderOptions(layout="fill")
        bp = BrollPlacement(url="http://x/img.jpg", start=1.0, end=2.0, opacity=0.5)
        f = _build_simple_filter(opts, "subs.ass", has_subs=False, broll_inputs=[(1, bp)])
        assert "between(t\\,1.0\\,2.0)" in f
        assert "colorchannelmixer=aa=0.5" in f

    def test_watermark_overlay_when_path_exists(self, tmp_path):
        wm = tmp_path / "logo.png"
        wm.write_bytes(b"fake png bytes")
        opts = RenderOptions(layout="fill", watermark_path=str(wm), watermark_position="top_left")
        f = _build_simple_filter(opts, "subs.ass", has_subs=False, watermark_input_idx=1)
        assert "[1:v]scale=270:-1" in f
        assert "overlay=x=60:y=60[v_wm]" in f

    def test_no_watermark_overlay_when_path_missing(self, tmp_path):
        opts = RenderOptions(layout="fill", watermark_path=str(tmp_path / "missing.png"))
        f = _build_simple_filter(opts, "subs.ass", has_subs=False, watermark_input_idx=1)
        assert "[v_wm]" not in f

    @pytest.mark.parametrize("position,expected", [
        ("top_left",      "overlay=x=60:y=60[v_wm]"),
        ("top_center",    "overlay=x=(W-w)/2:y=60[v_wm]"),
        ("top_right",     "overlay=x=W-w-60:y=60[v_wm]"),
        ("center_left",   "overlay=x=60:y=(H-h)/2[v_wm]"),
        ("center",        "overlay=x=(W-w)/2:y=(H-h)/2[v_wm]"),
        ("center_right",  "overlay=x=W-w-60:y=(H-h)/2[v_wm]"),
        ("bottom_left",   "overlay=x=60:y=H-h-60[v_wm]"),
        ("bottom_center", "overlay=x=(W-w)/2:y=H-h-60[v_wm]"),
        ("bottom_right",  "overlay=x=W-w-60:y=H-h-60[v_wm]"),
    ])
    def test_watermark_all_nine_positions(self, tmp_path, position, expected):
        """Every position offered by the UI must map to a distinct overlay
        expression — previously only 5 of the 9 were handled and the other 4
        silently fell back to bottom_right."""
        wm = tmp_path / "logo.png"
        wm.write_bytes(b"fake png bytes")
        opts = RenderOptions(layout="fill", watermark_path=str(wm), watermark_position=position)
        f = _build_simple_filter(opts, "subs.ass", has_subs=False, watermark_input_idx=1)
        assert expected in f


# ── Render concurrency semaphore ───────────────────────────────────────────────

class TestGetRenderSemaphore:
    def setup_method(self):
        vertical_editor_service._render_semaphore = None

    def teardown_method(self):
        vertical_editor_service._render_semaphore = None

    def test_returns_same_instance_across_calls(self):
        first = _get_render_semaphore()
        second = _get_render_semaphore()
        assert first is second

    def test_respects_configured_concurrency(self, monkeypatch):
        monkeypatch.setattr("app.config.settings.vertical_render_concurrency", 3)
        sem = _get_render_semaphore()
        assert sem._value == 3

    def test_clamps_to_at_least_one(self, monkeypatch):
        monkeypatch.setattr("app.config.settings.vertical_render_concurrency", 0)
        sem = _get_render_semaphore()
        assert sem._value == 1

    @pytest.mark.asyncio
    async def test_bounds_concurrent_acquirers(self, monkeypatch):
        monkeypatch.setattr("app.config.settings.vertical_render_concurrency", 2)
        sem = _get_render_semaphore()
        concurrent = 0
        max_concurrent = 0

        async def task():
            nonlocal concurrent, max_concurrent
            async with sem:
                concurrent += 1
                max_concurrent = max(max_concurrent, concurrent)
                await asyncio.sleep(0.05)
                concurrent -= 1

        await asyncio.gather(*(task() for _ in range(5)))
        assert max_concurrent == 2
