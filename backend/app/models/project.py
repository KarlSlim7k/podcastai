from datetime import datetime
from enum import Enum
from sqlalchemy import String, DateTime, Integer, Float, Text, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class ProjectStatus(str, Enum):
    CREATED = "created"
    UPLOADING = "uploading"
    EXTRACTING_AUDIO = "extracting_audio"
    TRANSCRIBING = "transcribing"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    ERROR = "error"


class TranscriptionStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"


class AnalysisType(str, Enum):
    EXECUTIVE_SUMMARY = "executive_summary"
    MAIN_TOPICS = "main_topics"
    KEY_IDEAS = "key_ideas"
    ACTION_ITEMS = "action_items"
    IMPORTANT_QUESTIONS = "important_questions"
    CHAPTERS = "chapters"
    TIMELINE = "timeline"
    LEARNING_POINTS = "learning_points"
    FACEBOOK_POST = "facebook_post"
    TWITTER_POST = "twitter_post"
    LINKEDIN_POST = "linkedin_post"
    BLOG_ARTICLE = "blog_article"
    YOUTUBE_DESCRIPTION = "youtube_description"
    SUGGESTED_TITLES = "suggested_titles"
    SUGGESTED_TAGS = "suggested_tags"
    FAQ = "faq"
    CONCLUSIONS = "conclusions"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default=ProjectStatus.CREATED)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # File paths
    original_file: Mapped[str | None] = mapped_column(String(500), nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    original_file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    original_mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    audio_file: Mapped[str | None] = mapped_column(String(500), nullable=True)
    audio_duration: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Error info
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    transcription: Mapped["Transcription | None"] = relationship(back_populates="project", uselist=False, cascade="all, delete-orphan")
    analyses: Mapped[list["Analysis"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    exports: Mapped[list["Export"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    chat_messages: Mapped[list["ChatMessage"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Transcription(Base):
    __tablename__ = "transcriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default=TranscriptionStatus.PENDING)
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    language_detected: Mapped[str | None] = mapped_column(String(20), nullable=True)
    language_requested: Mapped[str | None] = mapped_column(String(20), nullable=True)
    beam_size: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Content
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    segments: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    word_timestamps: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Files
    txt_file: Mapped[str | None] = mapped_column(String(500), nullable=True)
    json_file: Mapped[str | None] = mapped_column(String(500), nullable=True)
    srt_file: Mapped[str | None] = mapped_column(String(500), nullable=True)
    vtt_file: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Metadata
    processing_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    speaker_stats: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project: Mapped["Project"] = relationship(back_populates="transcription")
    clips: Mapped[list["Clip"]] = relationship(back_populates="transcription", cascade="all, delete-orphan")


class ClipStatus(str, Enum):
    PENDING = "pending"
    GENERATED = "generated"
    USED = "used"
    ARCHIVED = "archived"


class Clip(Base):
    """A short, self-contained moment (15-90s) selected from a transcript
    for use as a social-media Reel/Short/TikTok.

    The clip is defined by an [start, end] range in the source video/audio.
    Multiple ``ClipPlatform`` rows (one per platform) can be generated from
    the same clip.
    """

    __tablename__ = "clips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    transcription_id: Mapped[int] = mapped_column(Integer, ForeignKey("transcriptions.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"), nullable=False, index=True)

    # Time range in the source media
    start: Mapped[float] = mapped_column(Float, nullable=False)
    end: Mapped[float] = mapped_column(Float, nullable=False)
    duration: Mapped[float] = mapped_column(Float, nullable=False)  # end - start, denormalized for sorting

    # Why this clip is interesting (LLM-generated, ~1-2 sentences)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    virality_score: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0-100, LLM-assigned
    virality_breakdown: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON: {hook, pacing, emotional_pull, reason}
    virality_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)  # 1-sentence TL;DR
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)  # funny, insightful, controversial, emotional, etc.

    # Extracted media files (after ffmpeg cut)
    audio_clip_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    video_clip_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # The raw transcript text inside [start, end], for quick preview
    transcript_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Manual caption edits (Phase 2 of the vertical editor overhaul). When
    # set, this is a list of {start, end, word} (clip-relative seconds)
    # that overrides the words dynamically sliced from the transcription
    # at render time. Null means "use the auto-generated words".
    caption_overrides: Mapped[list | None] = mapped_column(JSON, nullable=True)

    status: Mapped[str] = mapped_column(String(50), default=ClipStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    transcription: Mapped["Transcription"] = relationship(back_populates="clips")
    platforms: Mapped[list["ClipGeneration"]] = relationship(back_populates="clip", cascade="all, delete-orphan")


class ClipPlatform(str, Enum):
    INSTAGRAM_REELS = "instagram_reels"
    TIKTOK = "tiktok"
    YOUTUBE_SHORTS = "youtube_shorts"
    FACEBOOK_REELS = "facebook_reels"
    TWITTER_VIDEO = "twitter_video"
    LINKEDIN_VIDEO = "linkedin_video"


class VerticalRenderStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"


class WatermarkPosition(str, Enum):
    TOP_LEFT = "top_left"
    TOP_RIGHT = "top_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_RIGHT = "bottom_right"
    CENTER = "center"


class VerticalPreset(Base):
    """A saved user configuration for the vertical editor.

    Users can save a "look" (layout, colors, sizes, sub style, watermark)
    and apply it to any clip in one click. The preset is a complete
    snapshot of the editor's visual configuration, so loading a preset
    is the same as setting all the form fields by hand.
    """

    __tablename__ = "vertical_presets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Layout + background
    layout: Mapped[str] = mapped_column(String(20), default="split")
    bg_style: Mapped[str] = mapped_column(String(20), default="blur")
    bg_color: Mapped[str] = mapped_column(String(9), default="#1a1a2e")
    bg_color2: Mapped[str] = mapped_column(String(9), default="#16213e")

    # Subtitles
    sub_style: Mapped[str] = mapped_column(String(20), default="karaoke")
    sub_color: Mapped[str] = mapped_column(String(9), default="#FFFFFF")
    sub_highlight: Mapped[str] = mapped_column(String(9), default="#FFD700")
    sub_outline: Mapped[str] = mapped_column(String(9), default="#000000")
    sub_size: Mapped[int] = mapped_column(Integer, default=64)
    sub_position: Mapped[int] = mapped_column(Integer, default=200)

    # Title
    add_title: Mapped[int] = mapped_column(Integer, default=1)
    title_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    title_color: Mapped[str] = mapped_column(String(9), default="#FFFFFF")
    title_size: Mapped[int] = mapped_column(Integer, default=72)
    title_position: Mapped[str] = mapped_column(String(10), default="top")  # top|center|bottom

    # Watermark (optional)
    watermark_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    watermark_position: Mapped[str] = mapped_column(String(20), default="bottom_right")
    watermark_opacity: Mapped[float] = mapped_column(Float, default=0.8)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class VerticalRender(Base):
    """A vertical (9:16) MP4 render generated from a Clip for short-form
    social platforms (Reels, TikTok, Shorts).

    Each render captures the full configuration used to produce it
    (layout, background style, subtitle style, colors, sizes) so the
    user can re-render or compare different presets.
    """

    __tablename__ = "vertical_renders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    clip_id: Mapped[int] = mapped_column(Integer, ForeignKey("clips.id"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"), nullable=False, index=True)

    # Configuration (so we can re-render or list presets)
    layout: Mapped[str] = mapped_column(String(20), default="split")
    bg_style: Mapped[str] = mapped_column(String(20), default="blur")
    bg_color: Mapped[str] = mapped_column(String(9), default="#1a1a2e")
    bg_color2: Mapped[str] = mapped_column(String(9), default="#16213e")
    sub_style: Mapped[str] = mapped_column(String(20), default="karaoke")
    sub_color: Mapped[str] = mapped_column(String(9), default="#FFFFFF")
    sub_highlight: Mapped[str] = mapped_column(String(9), default="#FFD700")
    sub_outline: Mapped[str] = mapped_column(String(9), default="#000000")
    sub_size: Mapped[int] = mapped_column(Integer, default=64)
    sub_position: Mapped[int] = mapped_column(Integer, default=200)
    add_title: Mapped[int] = mapped_column(Integer, default=1)  # SQLite: bool as 0/1
    title_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title_color: Mapped[str] = mapped_column(String(9), default="#FFFFFF")
    title_size: Mapped[int] = mapped_column(Integer, default=72)
    title_position: Mapped[str] = mapped_column(String(10), default="top")  # top|center|bottom

    # Output
    status: Mapped[str] = mapped_column(String(20), default=VerticalRenderStatus.PENDING)
    output_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    processing_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Watermark overlay (Phase 6): path to a PNG image and its position
    watermark_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    watermark_position: Mapped[str | None] = mapped_column(String(20), nullable=True)  # tl,tr,bl,br
    watermark_opacity: Mapped[float | None] = mapped_column(Float, nullable=True)
    # B-roll placements (Phase 3): list of {url, start, end, opacity}, clip-relative seconds
    broll_placements: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Video transform (Priority 1): {x, y, scale, rotation} of the main video,
    # or null to use the layout defaults.
    video_transform: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ClipGeneration(Base):
    """LLM-generated publishing package for a Clip on a given platform.

    One row per (clip, platform) pair. Holds the caption, hashtags, hook
    text, and a CTA suggestion tailored to the platform's best practices.
    """

    __tablename__ = "clip_generations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    clip_id: Mapped[int] = mapped_column(Integer, ForeignKey("clips.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)

    # Generated content
    hook: Mapped[str] = mapped_column(String(500), nullable=False)       # opening line
    caption: Mapped[str] = mapped_column(Text, nullable=False)           # full post body
    hashtags: Mapped[dict | None] = mapped_column(JSON, nullable=True)   # list[str]
    cta: Mapped[str | None] = mapped_column(String(255), nullable=True)  # call to action
    on_screen_text: Mapped[str | None] = mapped_column(String(500), nullable=True)  # text overlay

    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    processing_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    clip: Mapped["Clip"] = relationship(back_populates="platforms")


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"), nullable=False)
    analysis_type: Mapped[str] = mapped_column(String(100), nullable=False)
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped["Project"] = relationship(back_populates="analyses")


class Export(Base):
    __tablename__ = "exports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"), nullable=False)
    export_type: Mapped[str] = mapped_column(String(50), nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped["Project"] = relationship(back_populates="exports")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user / assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    context_used: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped["Project"] = relationship(back_populates="chat_messages")


# ── Social media publishing (Phase 12) ───────────────────────────────────

class SocialAccount(Base):
    """An OAuth-connected social media account (one row per platform).

    Stores the access/refresh tokens so the user only has to authorize
    once. Tokens are NEVER sent to the frontend — only the public
    ``account_handle`` and ``platform`` are exposed via the API.
    """

    __tablename__ = "social_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    platform: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # Tokens — encrypted at rest is a future improvement
    access_token: Mapped[str] = mapped_column(String(2000), nullable=False)
    refresh_token: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    expires_at: Mapped[float] = mapped_column(Float, default=0.0)
    # Public info
    open_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    account_handle: Mapped[str | None] = mapped_column(String(100), nullable=True)
    scope: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Status
    is_mock: Mapped[int] = mapped_column(Integer, default=0)  # 1 = mock account
    connected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SocialPublication(Base):
    """A log entry for each publish attempt (success or failure).

    Used for:
      - Showing the user a history of what was published
      - Debugging failed publishes
      - Avoiding duplicate publishes (one publish per render per platform)
    """

    __tablename__ = "social_publications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id"), nullable=False, index=True
    )
    clip_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clips.id"), nullable=False, index=True
    )
    vertical_render_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("vertical_renders.id"), nullable=True
    )
    platform: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # Publish payload (for re-publishing or audit)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    hashtags_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Result
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    post_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    post_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_mock: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
