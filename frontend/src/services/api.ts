import axios from 'axios'
import type {
  Project, ProjectListItem, Transcription, Analysis, ChatMessage,
  TranscriptionProgress, SystemStatus, OllamaModel, Export, ExportFormat, AnalysisType,
  Clip, ClipPlatform, SearchResponse, CaptionWord, ClipCaptions,
  VerticalRender, VerticalRenderRequest, VerticalStylesResponse, VerticalRenderListResponse,
  VerticalBatchRenderResponse,
  VerticalPreset, VerticalPresetListResponse, WatermarkUploadResponse,
  ViralityScore, BrollSuggestions,
  SocialPlatform, SocialStatus, SocialPublishRequest, SocialPublishResponse, SocialPublication,
} from '../types'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 300_000,
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const msg = err.response?.data?.detail || err.response?.data?.error || err.message
    return Promise.reject(new Error(msg))
  }
)

// ── Projects ────────────────────────────────────────────────────────────────
export const projectsApi = {
  list: (skip = 0, limit = 50) =>
    api.get<ProjectListItem[]>('/projects', { params: { skip, limit } }).then(r => r.data),

  get: (id: number) =>
    api.get<Project>(`/projects/${id}`).then(r => r.data),

  create: (data: { name: string; description?: string }) =>
    api.post<Project>('/projects', data).then(r => r.data),

  update: (id: number, data: { name?: string; description?: string }) =>
    api.patch<Project>(`/projects/${id}`, data).then(r => r.data),

  delete: (id: number) =>
    api.delete(`/projects/${id}`).then(r => r.data),
}

// ── Upload ──────────────────────────────────────────────────────────────────
export const uploadApi = {
  upload: (projectId: number, file: File, onProgress?: (pct: number) => void) => {
    const form = new FormData()
    form.append('file', file)
    return api.post<Project>(`/projects/${projectId}/upload`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (e) => {
        if (onProgress && e.total) onProgress(Math.round((e.loaded * 100) / e.total))
      },
    }).then(r => r.data)
  },
}

// ── Transcription ────────────────────────────────────────────────────────────
export const transcriptionApi = {
  start: (projectId: number, opts: { language?: string; beam_size?: number; model?: string }) =>
    api.post(`/projects/${projectId}/transcribe`, opts).then(r => r.data),

  getProgress: (projectId: number) =>
    api.get<TranscriptionProgress>(`/projects/${projectId}/transcription/progress`).then(r => r.data),

  get: (projectId: number) =>
    api.get<Transcription>(`/projects/${projectId}/transcription`).then(r => r.data),

  delete: (projectId: number) =>
    api.delete(`/projects/${projectId}/transcription`).then(r => r.data),

  reset: (projectId: number) =>
    api.post(`/projects/${projectId}/transcription/reset`).then(r => r.data),

  // Search — returns hits with start/end ranges
  search: (projectId: number, params: { q: string; speaker?: string; limit?: number; context_words?: number }) =>
    api.get<SearchResponse>(`/projects/${projectId}/transcription/search`, { params }).then(r => r.data),

  // Speakers (only available if pyannote diarization ran)
  speakers: (projectId: number) =>
    api.get<{ diarization_available: boolean; speakers: { speaker: string; total_time: number; turns: number; words: number }[] }>(
      `/projects/${projectId}/speakers`
    ).then(r => r.data),
}

// ── Analysis ────────────────────────────────────────────────────────────────
export const analysisApi = {
  getTypes: () =>
    api.get<{ types: AnalysisType[] }>('/projects/analysis-types').then(r => r.data.types),

  startBatch: (projectId: number, types: AnalysisType[], model: string) =>
    api.post(`/projects/${projectId}/analyze`, { analysis_types: types, model }).then(r => r.data),

  runSingle: (projectId: number, type: AnalysisType, model: string) =>
    api.post<Analysis>(`/projects/${projectId}/analyze/single`, {
      analysis_type: type, model
    }).then(r => r.data),

  list: (projectId: number) =>
    api.get<Analysis[]>(`/projects/${projectId}/analyses`).then(r => r.data),

  delete: (projectId: number, analysisId: number) =>
    api.delete(`/projects/${projectId}/analyses/${analysisId}`).then(r => r.data),
}

// ── Chat ─────────────────────────────────────────────────────────────────────
export const chatApi = {
  send: (projectId: number, message: string, model: string) =>
    api.post(`/projects/${projectId}/chat`, { message, model }).then(r => r.data),

  history: (projectId: number, limit = 50) =>
    api.get<ChatMessage[]>(`/projects/${projectId}/chat/history`, { params: { limit } }).then(r => r.data),

  clear: (projectId: number) =>
    api.delete(`/projects/${projectId}/chat/history`).then(r => r.data),
}

// ── Export ───────────────────────────────────────────────────────────────────
export const exportApi = {
  create: (projectId: number, format: ExportFormat) =>
    api.post<Export>(`/projects/${projectId}/export`, {
      format,
      include_transcription: true,
      include_analyses: true,
    }).then(r => r.data),

  list: (projectId: number) =>
    api.get<Export[]>(`/projects/${projectId}/exports`).then(r => r.data),

  downloadUrl: (projectId: number, exportId: number) =>
    `/api/v1/projects/${projectId}/export/${exportId}/download`,
}

// ── Clips & Social Media ────────────────────────────────────────────────────
export const clipsApi = {
  list: (projectId: number) =>
    api.get<{ clips: Clip[] }>(`/projects/${projectId}/clips`).then(r => r.data.clips),

  get: (projectId: number, clipId: number) =>
    api.get<Clip>(`/projects/${projectId}/clips/${clipId}`).then(r => r.data),

  detect: (projectId: number, opts: { num_clips?: number; min_duration?: number; max_duration?: number; model: string }) =>
    api.post(`/projects/${projectId}/clips/detect`, opts).then(r => r.data),

  generate: (projectId: number, clipId: number, opts: { platforms: ClipPlatform[]; model: string }) =>
    api.post(`/projects/${projectId}/clips/${clipId}/generate`, { clip_id: clipId, ...opts }).then(r => r.data),

  extract: (projectId: number, clipId: number, withVideo = true) =>
    api.post(`/projects/${projectId}/clips/${clipId}/extract`, null, { params: { with_video: withVideo } }).then(r => r.data),

  delete: (projectId: number, clipId: number) =>
    api.delete(`/projects/${projectId}/clips/${clipId}`).then(r => r.data),

  trim: (projectId: number, clipId: number, start: number, end: number) =>
    api.patch<Clip>(`/projects/${projectId}/clips/${clipId}`, { start, end }).then(r => r.data),

  getCaptions: (projectId: number, clipId: number) =>
    api.get<ClipCaptions>(`/projects/${projectId}/clips/${clipId}/captions`).then(r => r.data),

  saveCaptions: (projectId: number, clipId: number, words: CaptionWord[]) =>
    api.put<ClipCaptions>(`/projects/${projectId}/clips/${clipId}/captions`, { words }).then(r => r.data),

  resetCaptions: (projectId: number, clipId: number) =>
    api.delete<ClipCaptions>(`/projects/${projectId}/clips/${clipId}/captions`).then(r => r.data),

  audioDownloadUrl: (projectId: number, clipId: number) =>
    `/api/v1/projects/${projectId}/clips/${clipId}/download/audio`,

  videoDownloadUrl: (projectId: number, clipId: number) =>
    `/api/v1/projects/${projectId}/clips/${clipId}/download/video`,

  // Phase 8 — virality score
  getViralityScore: (projectId: number, clipId: number) =>
    api.get<ViralityScore>(`/projects/${projectId}/clips/${clipId}/virality-score`)
      .then(r => r.data),

  recomputeViralityScore: (projectId: number, clipId: number, model?: string) =>
    api.post<{ message: string }>(
      `/projects/${projectId}/clips/${clipId}/virality-score`,
      { model: model ?? null },
    ).then(r => r.data),

  // Phase 11 — AI b-rolls
  getBrollSuggestions: (projectId: number, clipId: number) =>
    api.get<BrollSuggestions>(`/projects/${projectId}/clips/${clipId}/brolls`)
      .then(r => r.data),
}

// ── Social publishing (Phase 12) ───────────────────────────────────────

export const socialApi = {
  status: () =>
    api.get<SocialStatus>('/social/status').then(r => r.data),

  publish: (platform: SocialPlatform, request: SocialPublishRequest) =>
    api.post<SocialPublishResponse>(
      `/social/${platform}/publish`,
      request,
    ).then(r => r.data),

  disconnect: (platform: SocialPlatform) =>
    api.post<{ message: string }>(`/social/${platform}/disconnect`, {})
      .then(r => r.data),

  listPublications: (projectId: number, platform?: SocialPlatform) =>
    api.get<{ publications: SocialPublication[] }>(
      `/social/${projectId}/publications`,
      { params: platform ? { platform } : {} },
    ).then(r => r.data.publications),

  // Returns the URL the user should visit to start the OAuth flow.
  // The router will redirect to the platform's authorization page.
  authUrl: (platform: SocialPlatform) =>
    `/api/v1/social/${platform}/auth`,
}

// ── Vertical Renders ───────────────────────────────────────────────────────
export const verticalApi = {
  listStyles: () =>
    api.get<VerticalStylesResponse>('/vertical/styles').then(r => r.data),

  // Trigger a render (returns immediately, the actual encoding happens in background)
  render: (projectId: number, clipId: number, request: VerticalRenderRequest) =>
    api.post(`/projects/${projectId}/clips/${clipId}/vertical`, request).then(r => r.data),

  // Trigger the same render config for several clips at once. Each clip is
  // queued as its own background task; clips that fail validation come back
  // in `errors` instead of failing the whole batch.
  renderBatch: (projectId: number, clipIds: number[], request: VerticalRenderRequest) =>
    api.post<VerticalBatchRenderResponse>(`/projects/${projectId}/vertical/batch`, { clip_ids: clipIds, request })
      .then(r => r.data),

  // Phase 15 — render a low-res draft synchronously and return the MP4 as a Blob.
  // Used by the live-preview panel; debounced on the frontend to avoid hammering
  // the server on every keystroke. The server forces quality='draft' regardless
  // of what's in `request`.
  renderDraft: async (projectId: number, clipId: number, request: VerticalRenderRequest): Promise<Blob> => {
    const r = await api.post(
      `/projects/${projectId}/clips/${clipId}/vertical/draft`,
      request,
      { responseType: 'blob', timeout: 120_000 },
    )
    return r.data as Blob
  },

  listForProject: (projectId: number) =>
    api.get<VerticalRenderListResponse>(`/projects/${projectId}/vertical`).then(r => r.data.renders),

  listForClip: (projectId: number, clipId: number) =>
    api.get<VerticalRenderListResponse>(`/projects/${projectId}/clips/${clipId}/vertical`).then(r => r.data.renders),

  get: (projectId: number, renderId: number) =>
    api.get<VerticalRender>(`/projects/${projectId}/vertical/${renderId}`).then(r => r.data),

  delete: (projectId: number, renderId: number) =>
    api.delete(`/projects/${projectId}/vertical/${renderId}`).then(r => r.data),

  downloadUrl: (projectId: number, renderId: number) =>
    `/api/v1/projects/${projectId}/vertical/${renderId}/download`,
}

// ── Vertical Presets & Watermark ───────────────────────────────────────────
export const verticalPresetsApi = {
  list: () =>
    api.get<VerticalPresetListResponse>('/vertical/presets').then(r => r.data.presets),
  get: (id: number) =>
    api.get<VerticalPreset>(`/vertical/presets/${id}`).then(r => r.data),
  create: (preset: Omit<VerticalPreset, 'id' | 'created_at' | 'updated_at'>) =>
    api.post<VerticalPreset>('/vertical/presets', preset).then(r => r.data),
  update: (id: number, preset: Omit<VerticalPreset, 'id' | 'created_at' | 'updated_at'>) =>
    api.put<VerticalPreset>(`/vertical/presets/${id}`, preset).then(r => r.data),
  delete: (id: number) =>
    api.delete(`/vertical/presets/${id}`).then(r => r.data),
}

export const watermarkApi = {
  upload: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post<WatermarkUploadResponse>('/vertical/watermark/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data)
  },
  // The file URL is relative; the API base is set on the axios instance.
  fileUrl: (fileId: string) => `/api/v1/vertical/watermark/file/${fileId}`,
}

// ── System ───────────────────────────────────────────────────────────────────
export const systemApi = {
  status: () =>
    api.get<SystemStatus>('/system/status').then(r => r.data),

  models: () =>
    api.get<OllamaModel[]>('/system/models').then(r => r.data),

  health: () =>
    api.get('/system/health'),

  hardware: () =>
    api.get('/system/hardware').then(r => r.data),
}
