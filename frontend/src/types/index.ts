export type ProjectStatus =
  | 'created'
  | 'uploading'
  | 'extracting_audio'
  | 'transcribing'
  | 'analyzing'
  | 'completed'
  | 'error'

export type TranscriptionStatus = 'pending' | 'processing' | 'completed' | 'error'

export type ClipStatus = 'pending' | 'generated' | 'used' | 'archived'

export type ClipPlatform =
  | 'instagram_reels'
  | 'tiktok'
  | 'youtube_shorts'
  | 'facebook_reels'
  | 'twitter_video'
  | 'linkedin_video'

export type AnalysisType =
  | 'executive_summary'
  | 'main_topics'
  | 'key_ideas'
  | 'action_items'
  | 'important_questions'
  | 'chapters'
  | 'timeline'
  | 'learning_points'
  | 'facebook_post'
  | 'twitter_post'
  | 'linkedin_post'
  | 'blog_article'
  | 'youtube_description'
  | 'suggested_titles'
  | 'suggested_tags'
  | 'faq'
  | 'conclusions'
  | 'viral_moments'
  | 'best_quotes'
  | 'seo_timestamps'

export type ExportFormat = 'txt' | 'docx' | 'pdf' | 'markdown' | 'json' | 'srt' | 'vtt'

export interface SpeakerStat {
  speaker: string
  total_time: number
  turns: number
  words: number
}

export interface Transcription {
  id: number
  status: TranscriptionStatus
  model_used: string | null
  language_detected: string | null
  text: string | null
  segments: Segment[] | null
  word_count: number | null
  processing_time: number | null
  speaker_stats: SpeakerStat[] | null
  txt_file: string | null
  json_file: string | null
  srt_file: string | null
  vtt_file: string | null
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface Segment {
  id: number
  start: number
  end: number
  text: string
  speaker?: string | null
  words?: Word[]
}

export interface Word {
  word: string
  start: number
  end: number
  probability: number
}

export interface Analysis {
  id: number
  analysis_type: AnalysisType
  model_used: string | null
  content: string | null
  processing_time: number | null
  error_message: string | null
  created_at: string
}

export interface Export {
  id: number
  export_type: ExportFormat
  file_path: string | null
  file_size: number | null
  created_at: string
}

export interface Clip {
  id: number
  transcription_id: number
  project_id: number
  start: number
  end: number
  duration: number
  title: string
  description: string | null
  virality_score: number | null
  // Phase 8 — extended virality info
  virality_breakdown: string | null
  virality_reason: string | null
  category: string | null
  transcript_excerpt: string | null
  audio_clip_path: string | null
  video_clip_path: string | null
  status: ClipStatus
  created_at: string
  platforms: ClipGeneration[]
}

// ── Caption editing (Vertical Editor Phase 2) ─────────────────────────────

export interface CaptionWord {
  start: number  // clip-relative seconds
  end: number
  word: string
}

export interface ClipCaptions {
  clip_id: number
  words: CaptionWord[]
  is_custom: boolean
}

// ── Virality score types (Phase 8) ───────────────────────────────────────

export interface ViralityBreakdown {
  hook: number              // 1-5
  pacing: number            // 1-5
  emotional_pull: number    // 1-5
  shareability: number      // 1-5
}

export interface ViralityScore {
  clip_id: number
  score: number | null                // 0-100
  reason: string | null               // 1-sentence TL;DR
  breakdown: ViralityBreakdown | null
  category: string | null
  model_used: string | null
  computed: boolean                    // true once score is present
}

// ── B-roll types (Phase 11) ────────────────────────────────────────────

export interface BrollSuggestion {
  id: string
  kind: 'photo' | 'video'
  keyword: string
  thumb_url: string
  full_url: string
  photographer: string
  source: 'pexels' | 'mock'
  duration_s: number
}

export interface BrollSuggestions {
  clip_id: number
  keywords: string[]                    // AI-generated search keywords
  suggestions: BrollSuggestion[]
  source: 'pexels' | 'mock'             // which provider was used
  total: number
}

/** Where (in the clip's timeline) a B-roll image will be composited onto the render. */
export interface BrollPlacement {
  /** Source URL — currently a Pexels image, but kept generic. */
  url: string
  /** Start time, in seconds, relative to the clip's start. */
  start: number
  /** End time, in seconds, relative to the clip's start. */
  end: number
  /** 0.0..1.0 — alpha multiplier for the overlay. Defaults to 1.0. */
  opacity: number
}

// ── Multi-track timeline types (Vertical Editor — CapCut-style) ──────────

/** The kinds of tracks rendered by the multi-track timeline (TimeLineV2). */
export type TimelineTrackType = 'video' | 'broll' | 'caption' | 'title'

/** Zoom is expressed as a multiplier; 1x means BASE_PPS (50) pixels per second. */
export type TimelineZoom = number

// ── Social publishing types (Phase 12) ──────────────────────────────────

export type SocialPlatform = 'tiktok' | 'youtube' | 'instagram'

export interface SocialPlatformInfo {
  platform: SocialPlatform
  label: string                         // "TikTok" / "YouTube Shorts" / "Instagram Reels"
  icon: string                          // emoji
  configured: boolean                   // True if real OAuth credentials are set
  connected: boolean                    // True if user has linked an account
  account_handle: string | null         // @username
  is_mock_account: boolean
}

export interface SocialStatus {
  platforms: SocialPlatformInfo[]
}

export interface SocialPublishRequest {
  vertical_render_id: number
  title: string
  description: string
  hashtags: string[]
}

export interface SocialPublishResponse {
  success: boolean
  publication_id: number | null
  platform: SocialPlatform
  post_id: string | null
  post_url: string | null
  status: 'published' | 'failed' | 'pending'
  error_message: string | null
  is_mock: boolean
}

export interface SocialPublication {
  id: number
  platform: SocialPlatform
  title: string
  status: 'published' | 'failed' | 'pending'
  post_id: string | null
  post_url: string | null
  is_mock: boolean
  error_message: string | null
  created_at: string
  published_at: string | null
}

export interface ClipGeneration {
  id: number
  clip_id: number
  project_id: number
  platform: ClipPlatform
  hook: string
  caption: string
  hashtags: string[] | null
  cta: string | null
  on_screen_text: string | null
  model_used: string | null
  processing_time: number | null
  error_message: string | null
  created_at: string
}

export interface SearchHit {
  segment_id: number | null
  start: number
  end: number
  text: string
  speaker: string | null
  context_before: string | null
  context_after: string | null
}

export interface SearchResponse {
  query: string
  total: number
  hits: SearchHit[]
}

export interface Project {
  id: number
  name: string
  description: string | null
  status: ProjectStatus
  original_filename: string | null
  original_file_size: number | null
  original_mime_type: string | null
  audio_duration: number | null
  error_message: string | null
  created_at: string
  updated_at: string
  transcription: Transcription | null
  analyses: Analysis[]
  exports: Export[]
  clips: Clip[]
}

export interface ProjectListItem {
  id: number
  name: string
  description: string | null
  status: ProjectStatus
  original_filename: string | null
  audio_duration: number | null
  created_at: string
  updated_at: string
}

export interface ChatMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  context_used: string | null
  model_used: string | null
  created_at: string
}

// ── Vertical Render types ────────────────────────────────────────────────

export type VerticalLayout = 'split' | 'centered' | 'fill' | 'auto'
export type VerticalBgStyle = 'blur' | 'solid' | 'gradient' | 'zoom'
// Phase 9: added 3 OpusClips-style animated word-by-word styles
export type VerticalSubStyle = 'standard' | 'karaoke' | 'neon' | 'mrbeast' | 'hormozi' | 'tiktok_classic'

export type VerticalRenderStatus = 'pending' | 'processing' | 'completed' | 'error'
// Where the title overlay is placed vertically in the 9:16 frame.
export type VerticalTitlePosition = 'top' | 'center' | 'bottom'
// The 9 watermark anchor points the editor exposes (must match the backend pos_map).
export type WatermarkPosition =
  | 'top_left' | 'top_center' | 'top_right'
  | 'center_left' | 'center' | 'center_right'
  | 'bottom_left' | 'bottom_center' | 'bottom_right'

/** Translate/scale/rotate the main video. null = use layout defaults. */
export interface VideoTransform {
  x: number        // px from frame center, can be negative
  y: number        // px from frame center, can be negative
  scale: number    // 100 = original, <100 smaller, >100 larger
  rotation: number // degrees, -180..180
}

export const IDENTITY_TRANSFORM: VideoTransform = { x: 0, y: 0, scale: 100, rotation: 0 }

export function isIdentityTransform(t: VideoTransform | null | undefined): boolean {
  if (!t) return true
  return t.x === 0 && t.y === 0 && t.scale === 100 && t.rotation === 0
}

export interface VerticalRenderRequest {
  layout: VerticalLayout
  bg_style: VerticalBgStyle
  bg_color: string
  bg_color2: string
  sub_style: VerticalSubStyle
  sub_color: string
  sub_highlight: string
  sub_outline: string
  sub_size: number
  sub_position: number
  add_title: boolean
  title_text: string | null
  title_color: string
  title_size: number
  title_position: VerticalTitlePosition
  // Phase 6 — watermark
  watermark_path: string | null
  watermark_position: string
  watermark_opacity: number
  // Phase 14 — B-roll placements (Phase 3 of vertical-editor plan)
  // Time-windowed image overlays. Empty array = no B-rolls.
  broll_placements: BrollPlacement[]
  // Priority 1 — main-video transform. null = layout defaults.
  video_transform: VideoTransform | null
}

export interface VerticalRender {
  id: number
  clip_id: number
  project_id: number
  layout: VerticalLayout
  bg_style: VerticalBgStyle
  bg_color: string
  bg_color2: string
  sub_style: VerticalSubStyle
  sub_color: string
  sub_highlight: string
  sub_outline: string
  sub_size: number
  sub_position: number
  add_title: number
  title_text: string | null
  title_color: string
  title_size: number
  title_position: VerticalTitlePosition
  status: VerticalRenderStatus
  output_path: string | null
  file_size: number | null
  width: number | null
  height: number | null
  duration: number | null
  processing_time: number | null
  error_message: string | null
  model_used: string | null
  // Phase 14 — B-roll placements persisted at render-time.
  // Returned by the API; can be null for legacy renders created before
  // the column existed, in which case the editor treats it as an empty list.
  broll_placements: BrollPlacement[] | null
  video_transform: VideoTransform | null
  created_at: string
  updated_at: string
}

export interface VerticalStyleInfo {
  id: string
  label: string
  description: string
  preview_color: string | null
}

export interface VerticalStylesResponse {
  layouts: VerticalStyleInfo[]
  backgrounds: VerticalStyleInfo[]
  subtitle_styles: VerticalStyleInfo[]
}

export interface VerticalRenderListResponse {
  renders: VerticalRender[]
}

// ── Vertical Batch Render types ───────────────────────────────────────────

export interface VerticalBatchRenderRequest {
  clip_ids: number[]
  request: VerticalRenderRequest
}

export interface VerticalBatchRenderError {
  clip_id: number
  detail: string
}

export interface VerticalBatchRenderResponse {
  render_ids: number[]
  errors: VerticalBatchRenderError[]
}

// ── Vertical Preset types ─────────────────────────────────────────────────

export interface VerticalPreset {
  id: number
  name: string
  description: string | null
  layout: VerticalLayout
  bg_style: VerticalBgStyle
  bg_color: string
  bg_color2: string
  sub_style: VerticalSubStyle
  sub_color: string
  sub_highlight: string
  sub_outline: string
  sub_size: number
  sub_position: number
  add_title: number
  title_text: string | null
  title_color: string
  title_size: number
  title_position: VerticalTitlePosition
  watermark_path: string | null
  watermark_position: string
  watermark_opacity: number
  created_at: string
  updated_at: string
}

export interface VerticalPresetListResponse {
  presets: VerticalPreset[]
}

export interface WatermarkUploadResponse {
  file_id: string
  filename: string
  url: string
  // Absolute path on disk — passed to the render endpoint as watermark_path
  path: string
  size: number
  width: number | null
  height: number | null
}

export interface TranscriptionProgress {
  status: string
  progress: number
  current_step: string
  estimated_remaining: number | null
}

export interface SystemStatus {
  status: string
  whisper_available: boolean
  whisper_model_cached: boolean
  whisper_model_name: string
  ollama_available: boolean
  ollama_models: string[]
  llamacpp_available: boolean
  llamacpp_models: string[]
  cuda_available: boolean
  vram_total_gb: number | null
  vram_free_gb: number | null
}

export interface OllamaModel {
  name: string
  size: number | null
  modified_at: string | null
}

// Labels for the new clip platforms (used in ClipsPanel UI)
export const CLIP_PLATFORM_LABELS: Record<ClipPlatform, string> = {
  instagram_reels: 'Instagram Reels',
  tiktok: 'TikTok',
  youtube_shorts: 'YouTube Shorts',
  facebook_reels: 'Facebook Reels',
  twitter_video: 'X / Twitter',
  linkedin_video: 'LinkedIn',
}

export const CLIP_PLATFORM_COLORS: Record<ClipPlatform, string> = {
  instagram_reels: 'from-pink-500 to-purple-600',
  tiktok: 'from-cyan-400 to-pink-500',
  youtube_shorts: 'from-red-500 to-red-700',
  facebook_reels: 'from-blue-500 to-blue-700',
  twitter_video: 'from-slate-700 to-slate-900',
  linkedin_video: 'from-sky-600 to-blue-800',
}
