from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from typing import Any
from app.models.project import ProjectStatus, TranscriptionStatus, AnalysisType, ClipStatus, ClipPlatform


# ── Project schemas ──────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None


# Speaker + search + clip schemas (defined before TranscriptionOut because
# TranscriptionOut references SpeakerStat).
class SpeakerStat(BaseModel):
    speaker: str
    total_time: float
    turns: int
    words: int


class SearchHit(BaseModel):
    """A single search match with its time range in the source media."""
    segment_id: int | None = None
    start: float
    end: float
    text: str
    speaker: str | None = None
    context_before: str | None = None
    context_after: str | None = None


class SearchResponse(BaseModel):
    query: str
    total: int
    hits: list[SearchHit]


class ClipGenerationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    clip_id: int
    project_id: int
    platform: str
    hook: str
    caption: str
    hashtags: list[str] | None
    cta: str | None
    on_screen_text: str | None
    model_used: str | None
    processing_time: float | None
    error_message: str | None
    created_at: datetime


class ClipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    transcription_id: int
    project_id: int
    start: float
    end: float
    duration: float
    title: str
    description: str | None
    virality_score: int | None
    # Phase 8 — extended virality info
    virality_breakdown: str | None     # JSON string with 4 dimensions + reason
    virality_reason: str | None        # 1-sentence TL;DR
    category: str | None
    transcript_excerpt: str | None
    audio_clip_path: str | None
    video_clip_path: str | None
    status: str
    created_at: datetime
    platforms: list[ClipGenerationOut] = []


class TranscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    model_used: str | None
    language_detected: str | None
    text: str | None
    segments: Any | None
    word_count: int | None
    processing_time: float | None
    speaker_stats: list[SpeakerStat] | None = None
    txt_file: str | None
    json_file: str | None
    srt_file: str | None
    vtt_file: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class ClipDetectionRequest(BaseModel):
    """Ask the AI to find viral-worthy moments in the transcript."""
    num_clips: int = Field(default=8, ge=1, le=20)
    min_duration: int = Field(default=15, ge=10, le=60)   # seconds
    max_duration: int = Field(default=60, ge=20, le=120)   # seconds
    model: str = "qwen3:8b"


class ClipGenerationRequest(BaseModel):
    """Generate platform-specific publishing content for an existing clip."""
    clip_id: int
    platforms: list[str]  # e.g. ["instagram_reels", "tiktok", "youtube_shorts"]
    model: str = "qwen3:8b"


class ClipListResponse(BaseModel):
    clips: list[ClipOut]


class ClipTrimRequest(BaseModel):
    """Manually adjust a clip's [start, end] boundaries (timeline trim)."""
    start: float = Field(ge=0)
    end: float = Field(gt=0)


class CaptionWord(BaseModel):
    """One subtitle word, clip-relative seconds. Mirrors WordTimestamp
    in vertical_editor_service.py."""
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    word: str


class ClipCaptionsOut(BaseModel):
    clip_id: int
    words: list[CaptionWord]
    is_custom: bool  # True if these come from a manual override, False if auto-generated


class ClipCaptionsRequest(BaseModel):
    """Save a manually-edited caption word list for a clip."""
    words: list[CaptionWord]


class BrollPlacement(BaseModel):
    """A B-roll image overlaid full-bleed during [start, end] (clip-relative seconds)."""
    url: str
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)


class VideoTransform(BaseModel):
    """Translate/scale/rotate the main video. null on the request = layout defaults."""
    x: float = 0.0                                # px offset from frame center (±)
    y: float = 0.0                                # px offset from frame center (±)
    scale: float = Field(default=100.0, ge=10.0, le=400.0)   # 100 = original
    rotation: float = Field(default=0.0, ge=-180.0, le=180.0)  # degrees


# ── Vertical Render schemas ────────────────────────────────────────────────

class VerticalRenderRequest(BaseModel):
    """Request body to render a vertical video from a clip."""
    layout: str = Field(default="split", pattern="^(split|centered|fill|auto)$")
    bg_style: str = Field(default="blur", pattern="^(blur|solid|gradient|zoom)$")
    bg_color: str = "#1a1a2e"
    bg_color2: str = "#16213e"
    sub_style: str = Field(default="karaoke", pattern="^(standard|karaoke|neon|mrbeast|hormozi|tiktok_classic)$")
    sub_color: str = "#FFFFFF"
    sub_highlight: str = "#FFD700"
    sub_outline: str = "#000000"
    sub_size: int = Field(default=64, ge=24, le=160)
    sub_position: int = Field(default=200, ge=0, le=1800)
    add_title: bool = True
    title_text: str | None = None
    title_color: str = "#FFFFFF"
    title_size: int = Field(default=72, ge=24, le=200)
    title_position: str = Field(default="top", pattern="^(top|center|bottom)$")
    # Watermark (Phase 6)
    watermark_path: str | None = None
    watermark_position: str = "bottom_right"
    watermark_opacity: float = Field(default=0.8, ge=0.0, le=1.0)
    # B-roll placements (Phase 3)
    broll_placements: list[BrollPlacement] | None = None
    # Video transform (Priority 1): null = use layout defaults
    video_transform: VideoTransform | None = None
    # Phase 15 — render quality. 'final' is the full-quality persisted
    # render (default). 'draft' is a fast 480p preview that skips subs,
    # watermark, and B-roll downloads; the /vertical/draft endpoint uses
    # this and returns the MP4 inline.
    quality: str = Field(default="final", pattern="^(final|draft)$")


class VerticalRenderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    clip_id: int
    project_id: int
    layout: str
    bg_style: str
    bg_color: str
    bg_color2: str
    sub_style: str
    sub_color: str
    sub_highlight: str
    sub_outline: str
    sub_size: int
    sub_position: int
    add_title: int
    title_text: str | None
    title_color: str
    title_size: int
    title_position: str = "top"
    status: str
    output_path: str | None
    file_size: int | None
    width: int | None
    height: int | None
    duration: float | None
    processing_time: float | None
    error_message: str | None
    model_used: str | None
    watermark_path: str | None
    watermark_position: str | None
    watermark_opacity: float | None
    broll_placements: list[BrollPlacement] | None
    video_transform: VideoTransform | None = None
    created_at: datetime
    updated_at: datetime


class VerticalRenderListResponse(BaseModel):
    renders: list[VerticalRenderOut]


# ── Vertical Batch Render schemas ───────────────────────────────────────────

class VerticalBatchRenderRequest(BaseModel):
    """Render the same configuration across several clips at once."""
    clip_ids: list[int] = Field(min_length=1, max_length=50)
    request: VerticalRenderRequest


class VerticalBatchRenderError(BaseModel):
    clip_id: int
    detail: str


class VerticalBatchRenderResponse(BaseModel):
    render_ids: list[int]          # one VerticalRender id per successfully queued clip
    errors: list[VerticalBatchRenderError]  # clips that failed validation (404/400)


# ── Vertical Preset schemas ────────────────────────────────────────────────

class VerticalPresetRequest(BaseModel):
    """Create or update a vertical preset. The form fields of the editor."""
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    layout: str = Field(default="split", pattern="^(split|centered|fill|auto)$")
    bg_style: str = Field(default="blur", pattern="^(blur|solid|gradient|zoom)$")
    bg_color: str = "#1a1a2e"
    bg_color2: str = "#16213e"
    sub_style: str = Field(default="karaoke", pattern="^(standard|karaoke|neon|mrbeast|hormozi|tiktok_classic)$")
    sub_color: str = "#FFFFFF"
    sub_highlight: str = "#FFD700"
    sub_outline: str = "#000000"
    sub_size: int = Field(default=64, ge=24, le=160)
    sub_position: int = Field(default=200, ge=0, le=1800)
    add_title: bool = True
    title_text: str | None = None
    title_color: str = "#FFFFFF"
    title_size: int = Field(default=72, ge=24, le=200)
    title_position: str = Field(default="top", pattern="^(top|center|bottom)$")
    # Watermark: path can be the file_id from the upload endpoint, or null
    watermark_path: str | None = None
    watermark_position: str = "bottom_right"
    watermark_opacity: float = Field(default=0.8, ge=0.0, le=1.0)


class VerticalPresetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    layout: str
    bg_style: str
    bg_color: str
    bg_color2: str
    sub_style: str
    sub_color: str
    sub_highlight: str
    sub_outline: str
    sub_size: int
    sub_position: int
    add_title: int
    title_text: str | None
    title_color: str
    title_size: int
    title_position: str = "top"
    watermark_path: str | None
    watermark_position: str
    watermark_opacity: float
    created_at: datetime
    updated_at: datetime


class VerticalPresetListResponse(BaseModel):
    presets: list[VerticalPresetOut]


# ── Watermark upload schema ────────────────────────────────────────────────

class WatermarkUploadResponse(BaseModel):
    file_id: str           # unique id, used to reference the file
    filename: str          # original filename
    url: str               # relative URL to serve the file (for preview in the UI)
    path: str              # absolute path on disk, passed to render as watermark_path
    size: int
    width: int | None
    height: int | None


# ── Virality score schemas (Phase 8) ───────────────────────────────────────

class ViralityBreakdownOut(BaseModel):
    """The 4 sub-dimensions of the virality score, 1-5 each."""
    hook: int              # 1-5: first-3-seconds impact
    pacing: int            # 1-5: rhythm / dynamism
    emotional_pull: int    # 1-5: emotional resonance
    shareability: int      # 1-5: would someone send this?


class ViralityScoreOut(BaseModel):
    """The virality score for a single clip, returned to the frontend."""
    clip_id: int
    score: int | None                          # 0-100, or None if not yet computed
    reason: str | None                         # 1-sentence TL;DR (Spanish)
    breakdown: ViralityBreakdownOut | None     # None if not yet computed
    category: str | None                       # funny | insightful | ...
    model_used: str | None
    computed: bool                             # True if the score is present


class ViralityScoreRequest(BaseModel):
    """Request body for the recompute endpoint (optional model override)."""
    model: str | None = None                   # default = settings.ollama_default_model


# ── B-roll schemas (Phase 11) ───────────────────────────────────────────

class BrollSuggestionOut(BaseModel):
    """One stock image or video suggestion for the b-roll panel."""
    id: str
    kind: str                # "photo" or "video"
    keyword: str             # the search phrase that produced this
    thumb_url: str           # small preview
    full_url: str            # full-resolution
    photographer: str        # credit string
    source: str              # "pexels" or "mock"
    duration_s: float = 0.0  # for videos


class BrollSuggestionListResponse(BaseModel):
    """List of b-roll suggestions for a clip."""
    clip_id: int
    keywords: list[str]            # the AI-generated search keywords
    suggestions: list[BrollSuggestionOut]
    source: str                    # "pexels" if real API used, "mock" otherwise
    total: int                     # number of suggestions returned


# ── Social publishing schemas (Phase 12) ──────────────────────────────────

class SocialPlatformInfo(BaseModel):
    """Info about a single social platform's status."""
    platform: str                # "tiktok" / "youtube" / "instagram"
    label: str                   # "TikTok" / "YouTube Shorts" / "Instagram Reels"
    icon: str                    # emoji for the UI
    configured: bool             # True if real OAuth credentials are set
    connected: bool              # True if the user has linked an account
    account_handle: str | None   # @username if connected
    is_mock_account: bool        # True if this is a mock account (for demos)


class SocialStatusResponse(BaseModel):
    """Connection status for all 3 platforms."""
    platforms: list[SocialPlatformInfo]


class SocialPublishRequest(BaseModel):
    """Request body for publishing a vertical render to a social platform."""
    vertical_render_id: int
    title: str
    description: str
    hashtags: list[str] = []


class SocialPublishResponse(BaseModel):
    """Result of a publish attempt."""
    success: bool
    publication_id: int | None
    platform: str
    post_id: str | None
    post_url: str | None
    status: str                     # "published" / "failed" / "pending"
    error_message: str | None
    is_mock: bool                   # True if published via MOCK provider


class SocialPublicationOut(BaseModel):
    """One row from the social_publications log."""
    id: int
    platform: str
    title: str
    status: str
    post_id: str | None
    post_url: str | None
    is_mock: bool
    error_message: str | None
    created_at: datetime
    published_at: datetime | None


class SocialPublicationListResponse(BaseModel):
    publications: list[SocialPublicationOut]


class VerticalStyleInfo(BaseModel):
    """Describes one of the available presets for the UI."""
    id: str
    label: str
    description: str
    preview_color: str | None = None  # hex color for UI swatch


class VerticalStylesResponse(BaseModel):
    layouts: list[VerticalStyleInfo]
    backgrounds: list[VerticalStyleInfo]
    subtitle_styles: list[VerticalStyleInfo]


class AnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    analysis_type: str
    model_used: str | None
    content: str | None
    processing_time: float | None
    error_message: str | None
    created_at: datetime


class ExportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    export_type: str
    file_path: str | None
    file_size: int | None
    created_at: datetime


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    context_used: str | None
    model_used: str | None
    created_at: datetime


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    status: str
    original_filename: str | None
    original_file_size: int | None
    original_mime_type: str | None
    audio_duration: float | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    transcription: TranscriptionOut | None = None
    analyses: list[AnalysisOut] = []
    exports: list[ExportOut] = []
    clips: list[ClipOut] = []


class ProjectListOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    status: str
    original_filename: str | None
    audio_duration: float | None
    created_at: datetime
    updated_at: datetime


# ── Transcription schemas ────────────────────────────────────────────────────

class TranscriptionRequest(BaseModel):
    language: str | None = None
    beam_size: int = Field(default=5, ge=1, le=10)
    model: str = "large-v3"


class TranscriptionProgress(BaseModel):
    status: str
    progress: float = 0.0
    current_step: str = ""
    estimated_remaining: float | None = None


# ── Analysis schemas ─────────────────────────────────────────────────────────

class AnalysisRequest(BaseModel):
    analysis_types: list[str]
    model: str = "qwen3:14b"


class AnalysisSingleRequest(BaseModel):
    analysis_type: str
    model: str = "qwen3:14b"


# ── Chat schemas ─────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    model: str = "qwen3:14b"


class ChatResponse(BaseModel):
    response: str
    context_used: str | None
    model_used: str
    message_id: int


# ── Export schemas ───────────────────────────────────────────────────────────

class ExportRequest(BaseModel):
    format: str = Field(..., pattern="^(txt|docx|pdf|markdown|json|srt|vtt)$")
    include_transcription: bool = True
    include_analyses: bool = True


# ── System schemas ───────────────────────────────────────────────────────────

class SystemStatus(BaseModel):
    status: str
    whisper_available: bool
    whisper_model_cached: bool = False
    whisper_model_name: str = ""
    ollama_available: bool
    ollama_models: list[str]
    llamacpp_available: bool = False
    llamacpp_models: list[str] = []
    cuda_available: bool
    vram_total_gb: float | None
    vram_free_gb: float | None


class OllamaModel(BaseModel):
    name: str
    size: int | None
    modified_at: str | None


# ── Generic response ─────────────────────────────────────────────────────────

class MessageResponse(BaseModel):
    message: str
    detail: str | None = None


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    code: str | None = None
