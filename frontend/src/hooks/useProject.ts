import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  projectsApi, transcriptionApi, analysisApi, chatApi, exportApi, uploadApi,
  systemApi, clipsApi, verticalApi, verticalPresetsApi, watermarkApi,
} from '../services/api'
import type {
  AnalysisType, ExportFormat, ClipPlatform, SearchResponse,
  VerticalRender, VerticalRenderRequest, VerticalStylesResponse, VerticalPreset,
  ViralityScore, BrollSuggestions, CaptionWord,
  SocialPlatform, SocialStatus, SocialPublishRequest, SocialPublishResponse, SocialPublication,
} from '../types'
import toast from 'react-hot-toast'

export function useProjects() {
  return useQuery({
    queryKey: ['projects'],
    queryFn: () => projectsApi.list(),
    refetchInterval: 5000,
  })
}

export function useProject(id: number) {
  return useQuery({
    queryKey: ['project', id],
    queryFn: () => projectsApi.get(id),
    refetchInterval: (data) => {
      const status = data?.state?.data?.status
      if (status === 'transcribing' || status === 'extracting_audio' || status === 'uploading') return 2000
      return 5000
    },
    enabled: !!id,
  })
}

export function useCreateProject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: { name: string; description?: string }) => projectsApi.create(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['projects'] })
      toast.success('Proyecto creado')
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

export function useDeleteProject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => projectsApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['projects'] })
      toast.success('Proyecto eliminado')
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

export function useUploadFile(projectId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ file, onProgress }: { file: File; onProgress?: (pct: number) => void }) =>
      uploadApi.upload(projectId, file, onProgress),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['project', projectId] })
      toast.success('Archivo subido correctamente')
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

export function useStartTranscription(projectId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (opts: { language?: string; beam_size?: number; model?: string }) =>
      transcriptionApi.start(projectId, opts),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['project', projectId] })
      toast.success('Transcripción iniciada')
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

export function useResetTranscription(projectId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => transcriptionApi.reset(projectId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['project', projectId] })
      qc.invalidateQueries({ queryKey: ['transcription-progress', projectId] })
      toast.success('Estado de transcripción reseteado')
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

export function useTranscriptionProgress(projectId: number, enabled: boolean) {
  return useQuery({
    queryKey: ['transcription-progress', projectId],
    queryFn: () => transcriptionApi.getProgress(projectId),
    refetchInterval: enabled ? 1500 : false,
    enabled,
  })
}

export function useStartAnalysis(projectId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ types, model }: { types: AnalysisType[]; model: string }) =>
      analysisApi.startBatch(projectId, types, model),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['project', projectId] })
      toast.success('Análisis iniciado en segundo plano')
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

export function useRunSingleAnalysis(projectId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ type, model }: { type: AnalysisType; model: string }) =>
      analysisApi.runSingle(projectId, type, model),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['project', projectId] })
      toast.success('Análisis completado')
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

export function useChatHistory(projectId: number) {
  return useQuery({
    queryKey: ['chat-history', projectId],
    queryFn: () => chatApi.history(projectId),
  })
}

export function useSendMessage(projectId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ message, model }: { message: string; model: string }) =>
      chatApi.send(projectId, message, model),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['chat-history', projectId] })
    },
  })
}

export function useCreateExport(projectId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (format: ExportFormat) => exportApi.create(projectId, format),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['project', projectId] })
      toast.success('Exportación generada')
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

export function useSystemStatus() {
  return useQuery({
    queryKey: ['system-status'],
    queryFn: () => systemApi.status(),
    refetchInterval: 30_000,
    staleTime: 10_000,
  })
}

export interface HardwareInfo {
  os: string
  is_apple_silicon: boolean
  has_cuda: boolean
  has_metal: boolean
  has_ffmpeg_nvenc: boolean
  has_ffmpeg_videotoolbox: boolean
  has_ffmpeg_qsv: boolean
  compute_backend: string
  whisper_backend: string
  ffmpeg_encoder: string
  ffmpeg_path: string
  summary: string
}

export function useHardwareInfo() {
  return useQuery({
    queryKey: ['system-hardware'],
    queryFn: () => systemApi.hardware() as Promise<HardwareInfo>,
    staleTime: 60_000,
  })
}

// ── Search ──────────────────────────────────────────────────────────────────

export function useTranscriptionSearch(
  projectId: number,
  params: { q: string; speaker?: string | null },
  enabled = true
) {
  return useQuery<SearchResponse>({
    queryKey: ['transcription-search', projectId, params.q, params.speaker],
    queryFn: () => transcriptionApi.search(projectId, { q: params.q, speaker: params.speaker || undefined, limit: 50 }),
    enabled: enabled && params.q.trim().length > 0,
    staleTime: 5_000,
  })
}

export function useSpeakers(projectId: number, enabled: boolean) {
  return useQuery({
    queryKey: ['speakers', projectId],
    queryFn: () => transcriptionApi.speakers(projectId),
    enabled,
    staleTime: 60_000,
  })
}

// ── Clips ───────────────────────────────────────────────────────────────────

export function useClips(projectId: number, enabled = true) {
  return useQuery({
    queryKey: ['clips', projectId],
    queryFn: () => clipsApi.list(projectId),
    enabled,
    refetchInterval: (data) => {
      // Poll every 3s while at least one clip has no platforms yet (still generating)
      const clips = data?.state?.data as any[] | undefined
      if (Array.isArray(clips) && clips.some((c) => c.platforms.length === 0)) return 3000
      return false
    },
    staleTime: 5_000,
  })
}

export function useClip(projectId: number, clipId: number | null) {
  return useQuery({
    queryKey: ['clip', projectId, clipId],
    queryFn: () => clipsApi.get(projectId, clipId!),
    enabled: !!clipId,
    staleTime: 5_000,
  })
}

export function useDetectClips(projectId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (opts: { num_clips?: number; min_duration?: number; max_duration?: number; model: string }) =>
      clipsApi.detect(projectId, opts),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['clips', projectId] })
      qc.invalidateQueries({ queryKey: ['project', projectId] })
      toast.success('Búsqueda de clips iniciada. Esto puede tardar varios minutos.')
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

export function useGenerateClipContent(projectId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ clipId, platforms, model }: { clipId: number; platforms: ClipPlatform[]; model: string }) =>
      clipsApi.generate(projectId, clipId, { platforms, model }),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ['clips', projectId] })
      qc.invalidateQueries({ queryKey: ['clip', projectId, vars.clipId] })
      toast.success(`Generando contenido para ${vars.platforms.length} plataforma(s)`)
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

export function useExtractClip(projectId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ clipId, withVideo }: { clipId: number; withVideo?: boolean }) =>
      clipsApi.extract(projectId, clipId, withVideo ?? true),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ['clips', projectId] })
      qc.invalidateQueries({ queryKey: ['clip', projectId, vars.clipId] })
      toast.success('Extracción de clip iniciada')
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

export function useTrimClip(projectId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ clipId, start, end }: { clipId: number; start: number; end: number }) =>
      clipsApi.trim(projectId, clipId, start, end),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ['clips', projectId] })
      qc.invalidateQueries({ queryKey: ['clip', projectId, vars.clipId] })
      qc.invalidateQueries({ queryKey: ['vertical-renders', projectId, vars.clipId] })
      toast.success('Clip recortado. Re-extrayendo audio/video...')
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

export function useClipCaptions(projectId: number, clipId: number | null) {
  return useQuery({
    queryKey: ['clip-captions', projectId, clipId],
    queryFn: () => clipsApi.getCaptions(projectId, clipId!),
    enabled: !!clipId,
    staleTime: 5_000,
  })
}

// No success toast here — this mutation is shared by the explicit "Guardar
// subtítulos" button (CaptionEditor, which toasts itself) AND by every
// inline word edit/delete from the timeline inspector, where a toast per
// keystroke/debounce would be noise.
export function useSaveClipCaptions(projectId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ clipId, words }: { clipId: number; words: CaptionWord[] }) =>
      clipsApi.saveCaptions(projectId, clipId, words),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ['clip-captions', projectId, vars.clipId] })
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

export function useResetClipCaptions(projectId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (clipId: number) => clipsApi.resetCaptions(projectId, clipId),
    onSuccess: (_, clipId) => {
      qc.invalidateQueries({ queryKey: ['clip-captions', projectId, clipId] })
      toast.success('Subtítulos restaurados a los detectados automáticamente')
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

export function useDeleteClip(projectId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (clipId: number) => clipsApi.delete(projectId, clipId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['clips', projectId] })
      qc.invalidateQueries({ queryKey: ['project', projectId] })
      toast.success('Clip eliminado')
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

// ── Vertical Renders ──────────────────────────────────────────────────────

export function useVerticalStyles() {
  return useQuery({
    queryKey: ['vertical-styles'],
    queryFn: () => verticalApi.listStyles(),
    staleTime: 60 * 60 * 1000, // styles don't change, cache 1h
  })
}

export function useVerticalRenders(projectId: number, clipId: number | null, enabled = true) {
  return useQuery({
    queryKey: ['vertical-renders', projectId, clipId],
    queryFn: () => verticalApi.listForClip(projectId, clipId!),
    enabled: enabled && !!clipId,
    // Poll every 2s while any render is still pending/processing
    refetchInterval: (data) => {
      const renders = data?.state?.data as VerticalRender[] | undefined
      if (Array.isArray(renders) && renders.some(r => r.status === 'pending' || r.status === 'processing')) return 2000
      return false
    },
    staleTime: 5_000,
  })
}

export function useVerticalRender(projectId: number, renderId: number | null) {
  return useQuery({
    queryKey: ['vertical-render', projectId, renderId],
    queryFn: () => verticalApi.get(projectId, renderId!),
    enabled: !!renderId,
    refetchInterval: (data) => {
      if (data?.state?.data && (data.state.data as VerticalRender).status === 'pending') return 1500
      if (data?.state?.data && (data.state.data as VerticalRender).status === 'processing') return 2000
      return false
    },
  })
}

export function useCreateVerticalRender(projectId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ clipId, request }: { clipId: number; request: VerticalRenderRequest }) =>
      verticalApi.render(projectId, clipId, request),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ['vertical-renders', projectId, vars.clipId] })
      qc.invalidateQueries({ queryKey: ['project', projectId] })
      toast.success('Render vertical iniciado. Esto puede tardar 10-30s.')
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

// Polls ALL renders of a project (not scoped to one clip) — used by the
// batch-export queue view. Same dynamic refetchInterval pattern as
// useVerticalRenders: poll every 2s while anything is still in flight.
export function useProjectVerticalRenders(projectId: number, enabled = true) {
  return useQuery({
    queryKey: ['vertical-renders', projectId, 'all'],
    queryFn: () => verticalApi.listForProject(projectId),
    enabled,
    refetchInterval: (data) => {
      const renders = data?.state?.data as VerticalRender[] | undefined
      if (Array.isArray(renders) && renders.some(r => r.status === 'pending' || r.status === 'processing')) return 2000
      return false
    },
    staleTime: 5_000,
  })
}

export function useBatchCreateVerticalRender(projectId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ clipIds, request }: { clipIds: number[]; request: VerticalRenderRequest }) =>
      verticalApi.renderBatch(projectId, clipIds, request),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['vertical-renders', projectId] })
      qc.invalidateQueries({ queryKey: ['project', projectId] })
      if (data.errors.length === 0) {
        toast.success(`${data.render_ids.length} render(s) iniciados. Esto puede tardar varios minutos.`)
      } else {
        toast.error(`${data.render_ids.length} iniciados, ${data.errors.length} con error (ver detalle)`)
      }
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

export function useDeleteVerticalRender(projectId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ renderId, clipId }: { renderId: number; clipId: number }) =>
      verticalApi.delete(projectId, renderId),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ['vertical-renders', projectId, vars.clipId] })
      qc.invalidateQueries({ queryKey: ['project', projectId] })
      toast.success('Render eliminado')
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

// Phase 15 — live preview. useDraftPreview triggers a debounced 480p draft
// render whenever `formKey` changes (typically a JSON.stringify of the form
// state). It returns a Blob URL that's safe to assign to a <video src=...>.
//
// The debounce is done in the component, NOT here, so that React Query can
// treat each new request as a fresh fetch and cancel in-flight ones cleanly
// via the AbortController. This hook is a thin wrapper around verticalApi.
export function useDraftPreview(projectId: number, clipId: number | null) {
  return useMutation({
    mutationFn: (request: VerticalRenderRequest) => {
      if (clipId == null) throw new Error('clipId is null')
      return verticalApi.renderDraft(projectId, clipId, request)
    },
  })
}

// ── Vertical Presets (Phase 6) ───────────────────────────────────────────

export function useVerticalPresets() {
  return useQuery({
    queryKey: ['vertical-presets'],
    queryFn: () => verticalPresetsApi.list(),
    staleTime: 30_000,
  })
}

export function useCreateVerticalPreset() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (preset: Omit<VerticalPreset, 'id' | 'created_at' | 'updated_at'>) =>
      verticalPresetsApi.create(preset),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['vertical-presets'] })
      toast.success('Preset guardado')
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

export function useDeleteVerticalPreset() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => verticalPresetsApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['vertical-presets'] })
      toast.success('Preset eliminado')
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

export function useUploadWatermark() {
  return useMutation({
    mutationFn: (file: File) => watermarkApi.upload(file),
    onError: (e: Error) => toast.error(e.message),
  })
}

// ── Virality score (Phase 8) ────────────────────────────────────────────────

/** Poll the virality score for a clip every 3 seconds. */
export function useClipViralityScore(
  projectId: number, clipId: number | null, enabled = true
) {
  return useQuery({
    queryKey: ['virality-score', projectId, clipId],
    queryFn: () => clipsApi.getViralityScore(projectId, clipId!),
    enabled: enabled && clipId != null,
    refetchInterval: (q) => {
      const data = q.state.data as ViralityScore | undefined
      // Once computed, stop polling. The score doesn't change unless
      // the user explicitly recomputes it.
      if (data?.computed) return false
      return 3000
    },
    staleTime: 5_000,
  })
}

/** Trigger a recompute of the virality score. */
export function useRecomputeViralityScore(projectId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ clipId, model }: { clipId: number; model?: string }) =>
      clipsApi.recomputeViralityScore(projectId, clipId, model),
    onSuccess: (_, { clipId }) => {
      // Invalidate so the polling hook picks up the new "not computed yet" state
      qc.invalidateQueries({ queryKey: ['virality-score', projectId, clipId] })
      qc.invalidateQueries({ queryKey: ['clips', projectId] })
      toast.success('Recalculando score de viralidad...')
    },
    onError: (e: Error) => toast.error(e.message),
  })
}

// ── B-roll suggestions (Phase 11) ──────────────────────────────────────

/** Fetch AI-suggested b-rolls for a clip. */
export function useBrollSuggestions(projectId: number, clipId: number | null) {
  return useQuery({
    queryKey: ['broll-suggestions', projectId, clipId],
    queryFn: () => clipsApi.getBrollSuggestions(projectId, clipId!),
    enabled: clipId != null,
    staleTime: 5 * 60_000,  // 5 min — keywords don't change often
  })
}

// ── Social publishing (Phase 12) ───────────────────────────────────────

import { socialApi } from '../services/api'

/** Connection status for all 3 platforms. */
export function useSocialStatus() {
  return useQuery({
    queryKey: ['social-status'],
    queryFn: () => socialApi.status(),
    staleTime: 30_000,
  })
}

/** Publish a vertical render to a social platform. */
export function usePublishToSocial() {
  return useMutation({
    mutationFn: ({
      platform, request,
    }: {
      platform: SocialPlatform
      request: SocialPublishRequest
    }) => socialApi.publish(platform, request),
  })
}

/** Disconnect a platform. */
export function useDisconnectSocial() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (platform: SocialPlatform) => socialApi.disconnect(platform),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['social-status'] }),
  })
}

/** List past publications for a project. */
export function useSocialPublications(projectId: number, platform?: SocialPlatform) {
  return useQuery({
    queryKey: ['social-publications', projectId, platform ?? 'all'],
    queryFn: () => socialApi.listPublications(projectId, platform),
    enabled: projectId > 0,
  })
}
