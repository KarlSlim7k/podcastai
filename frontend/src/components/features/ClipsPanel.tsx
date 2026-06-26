import { useState } from 'react'
import {
  Sparkles, Scissors, Download, Play, ChevronDown, ChevronUp, Loader2,
  Instagram, Music2, Youtube, Facebook, Twitter, Linkedin, RefreshCw, Trash2,
  CheckCircle2, AlertCircle, Hash, MessageSquare, Type, Wand2, Copy, Check,
  Smartphone, SlidersHorizontal, Layers, X,
} from 'lucide-react'
import {
  useClips, useDetectClips, useGenerateClipContent, useExtractClip, useDeleteClip,
  useTrimClip,
} from '../../hooks/useProject'
import { Card, CardBody, CardHeader } from '../ui/Card'
import { Button } from '../ui/Button'
import { ViralityBadge } from './ViralityBadge'
import { Timeline } from './Timeline'
import { cn, formatDuration, categoryLabel, categoryColor } from '../../utils'
import {
  CLIP_PLATFORM_LABELS, CLIP_PLATFORM_COLORS,
} from '../../types'
import type { Project, Clip, ClipPlatform, ClipGeneration, OllamaModel } from '../../types'
import { BatchVerticalRenderModal } from './BatchVerticalRenderModal'

interface ClipsPanelProps {
  project: Project
  models: OllamaModel[]
  onOpenVerticalEditor?: (clip: Clip) => void
}

const ALL_PLATFORMS: ClipPlatform[] = [
  'instagram_reels', 'tiktok', 'youtube_shorts', 'facebook_reels', 'twitter_video', 'linkedin_video',
]

const PLATFORM_ICONS: Record<ClipPlatform, any> = {
  instagram_reels: Instagram,
  tiktok: Music2,
  youtube_shorts: Youtube,
  facebook_reels: Facebook,
  twitter_video: Twitter,
  linkedin_video: Linkedin,
}

export function ClipsPanel({ project, models, onOpenVerticalEditor }: ClipsPanelProps) {
  const [numClips, setNumClips] = useState(8)
  const [minDur, setMinDur] = useState(15)
  const [maxDur, setMaxDur] = useState(60)
  const [model, setModel] = useState(models[0]?.name ?? 'gemma4:latest')
  const [expandedClip, setExpandedClip] = useState<number | null>(null)
  const [selectedClipIds, setSelectedClipIds] = useState<Set<number>>(new Set())
  const [showBatchModal, setShowBatchModal] = useState(false)

  const hasTranscription = !!project.transcription?.text && !!project.transcription?.segments?.length

  const clipsQuery = useClips(project.id, hasTranscription)
  const detectClips = useDetectClips(project.id)
  const generate = useGenerateClipContent(project.id)
  const extract = useExtractClip(project.id)
  const deleteClip = useDeleteClip(project.id)

  const clips = clipsQuery.data ?? []

  const handleDetect = () => {
    detectClips.mutate({
      num_clips: numClips,
      min_duration: minDur,
      max_duration: maxDur,
      model,
    })
  }

  const toggleClipSelection = (clipId: number) => {
    const next = new Set(selectedClipIds)
    next.has(clipId) ? next.delete(clipId) : next.add(clipId)
    setSelectedClipIds(next)
  }

  const selectedClips = clips.filter((c) => selectedClipIds.has(c.id))

  return (
    <div className="space-y-4">
      {/* Detection panel */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-brand-400" />
            <h2 className="font-semibold text-white">Detector de clips virales</h2>
          </div>
        </CardHeader>
        <CardBody className="space-y-4">
          {!hasTranscription ? (
            <p className="text-sm text-slate-400">
              Transcribe el audio primero para detectar momentos virales.
            </p>
          ) : (
            <>
              <p className="text-sm text-slate-400">
                Analiza la transcripción con IA para encontrar los mejores momentos para Reels,
                TikTok y YouTube Shorts. Cada clip incluirá un título, descripción y score de viralidad.
              </p>

              <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1.5">Nº clips</label>
                  <input
                    type="number" min={1} max={20}
                    value={numClips}
                    onChange={(e) => setNumClips(Math.max(1, Math.min(20, Number(e.target.value) || 1)))}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-brand-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1.5">Duración mín. (s)</label>
                  <input
                    type="number" min={10} max={60}
                    value={minDur}
                    onChange={(e) => setMinDur(Math.max(10, Number(e.target.value) || 10))}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-brand-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1.5">Duración máx. (s)</label>
                  <input
                    type="number" min={20} max={120}
                    value={maxDur}
                    onChange={(e) => setMaxDur(Math.max(minDur + 5, Number(e.target.value) || 60))}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-brand-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-400 mb-1.5">Modelo</label>
                  <select
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-brand-500"
                  >
                    {(models.length > 0 ? models : [
                      { name: 'gemma4:latest' } as OllamaModel,
                      { name: 'qwen3:8b' } as OllamaModel,
                    ]).map((m) => (
                      <option key={m.name} value={m.name}>{m.name}</option>
                    ))}
                  </select>
                </div>
              </div>

              <Button
                onClick={handleDetect}
                loading={detectClips.isPending}
                className="w-full"
              >
                <Wand2 className="w-4 h-4" />
                {clips.length > 0 ? 'Detectar más clips' : 'Detectar clips'}
              </Button>

              {detectClips.isPending && (
                <p className="text-xs text-amber-400 text-center animate-pulse">
                  Analizando transcripción en chunks de 5 min · Esto puede tardar varios minutos
                </p>
              )}
            </>
          )}
        </CardBody>
      </Card>

      {/* Clips list */}
      {clipsQuery.isLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 text-brand-400 animate-spin" />
        </div>
      )}

      {clips.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-white">
              {clips.length} clip{clips.length !== 1 ? 's' : ''} detectado{clips.length !== 1 ? 's' : ''}
            </h3>
            <p className="text-xs text-slate-500">Ordenados por score de viralidad</p>
          </div>

          {selectedClipIds.size > 0 && (
            <div className="flex items-center justify-between gap-3 px-4 py-2.5 bg-pink-900/10 border border-pink-800/30 rounded-lg">
              <span className="text-sm text-pink-200">
                {selectedClipIds.size} clip{selectedClipIds.size !== 1 ? 's' : ''} seleccionado{selectedClipIds.size !== 1 ? 's' : ''}
              </span>
              <div className="flex items-center gap-2">
                <Button size="sm" onClick={() => setShowBatchModal(true)}>
                  <Layers className="w-3.5 h-3.5" />
                  Exportar en lote
                </Button>
                <button
                  onClick={() => setSelectedClipIds(new Set())}
                  className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-700/60 rounded-lg"
                  title="Cancelar selección"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}

          {clips.map((clip) => (
            <ClipCard
              key={clip.id}
              clip={clip}
              project={project}
              isExpanded={expandedClip === clip.id}
              onToggle={() => setExpandedClip(expandedClip === clip.id ? null : clip.id)}
              model={model}
              onGenerate={(platforms) => generate.mutate({ clipId: clip.id, platforms, model })}
              onExtract={(withVideo) => extract.mutate({ clipId: clip.id, withVideo })}
              onDelete={() => deleteClip.mutate(clip.id)}
              onOpenVerticalEditor={onOpenVerticalEditor ? () => onOpenVerticalEditor(clip) : undefined}
              isGenerating={generate.isPending}
              isExtracting={extract.isPending}
              isSelected={selectedClipIds.has(clip.id)}
              onToggleSelect={() => toggleClipSelection(clip.id)}
            />
          ))}
        </div>
      )}

      {showBatchModal && selectedClips.length > 0 && (
        <BatchVerticalRenderModal
          projectId={project.id}
          clips={selectedClips}
          onClose={() => { setShowBatchModal(false); setSelectedClipIds(new Set()) }}
        />
      )}

      {clips.length === 0 && hasTranscription && !clipsQuery.isLoading && (
        <Card>
          <CardBody className="py-12 text-center">
            <Sparkles className="w-12 h-12 text-slate-600 mx-auto mb-3" />
            <p className="text-slate-400">Aún no se han detectado clips virales</p>
            <p className="text-xs text-slate-500 mt-2">
              Pulsa el botón de arriba para analizar la transcripción
            </p>
          </CardBody>
        </Card>
      )}
    </div>
  )
}

interface ClipCardProps {
  clip: Clip
  project: Project
  isExpanded: boolean
  onToggle: () => void
  model: string
  onGenerate: (platforms: ClipPlatform[]) => void
  onExtract: (withVideo: boolean) => void
  onDelete: () => void
  isGenerating: boolean
  isExtracting: boolean
  onOpenVerticalEditor?: () => void
  isSelected: boolean
  onToggleSelect: () => void
}

function ClipCard({
  clip, project, isExpanded, onToggle, model, onGenerate, onExtract, onDelete,
  isGenerating, isExtracting, onOpenVerticalEditor, isSelected, onToggleSelect,
}: ClipCardProps) {
  const [selectedPlatforms, setSelectedPlatforms] = useState<Set<ClipPlatform>>(new Set(['instagram_reels', 'tiktok', 'youtube_shorts']))
  const [copiedField, setCopiedField] = useState<string | null>(null)
  const [showTrim, setShowTrim] = useState(false)
  const [pendingStart, setPendingStart] = useState(clip.start)
  const [pendingEnd, setPendingEnd] = useState(clip.end)
  const [trimWindow, setTrimWindow] = useState({ start: 0, end: clip.end + 30 })
  const trimClip = useTrimClip(clip.project_id)

  const openTrim = () => {
    setPendingStart(clip.start)
    setPendingEnd(clip.end)
    const audioDuration = project.audio_duration ?? clip.end + 30
    setTrimWindow({
      start: Math.max(0, clip.start - 30),
      end: Math.min(audioDuration, clip.end + 30),
    })
    setShowTrim(true)
  }
  const trimChanged = Math.abs(pendingStart - clip.start) > 0.01 || Math.abs(pendingEnd - clip.end) > 0.01

  const togglePlatform = (p: ClipPlatform) => {
    const next = new Set(selectedPlatforms)
    next.has(p) ? next.delete(p) : next.add(p)
    setSelectedPlatforms(next)
  }

  const hasMedia = !!clip.audio_clip_path
  const hasAllPlatforms = ALL_PLATFORMS.every(p => clip.platforms.some(g => g.platform === p))

  return (
    <Card>
      {/* Header — always visible */}
      <div className="px-6 py-4 flex items-start gap-4">
        {/* Batch-export selection (only for clips with extracted media) */}
        {hasMedia && (
          <button
            onClick={(e) => { e.stopPropagation(); onToggleSelect() }}
            className={cn(
              'flex-shrink-0 mt-1 w-5 h-5 rounded-md border-2 flex items-center justify-center transition-colors',
              isSelected ? 'bg-pink-600 border-pink-600' : 'border-slate-600 hover:border-slate-400',
            )}
            title="Seleccionar para exportar en lote"
          >
            {isSelected && <Check className="w-3.5 h-3.5 text-white" />}
          </button>
        )}

        {/* Time range */}
        <div className="flex-shrink-0 w-28">
          <div className="bg-brand-600/20 border border-brand-500/30 rounded-md px-2 py-1.5 text-center">
            <div className="text-[10px] uppercase tracking-wide text-brand-300/80">Tiempo</div>
            <div className="text-xs font-mono text-brand-200 font-semibold">
              {formatDuration(clip.start)}
            </div>
            <div className="text-[10px] text-slate-500">→ {formatDuration(clip.end)}</div>
          </div>
          <div className="text-[10px] text-center text-slate-500 mt-1">
            {clip.duration.toFixed(0)}s
          </div>
        </div>

        {/* Content */}
        <div
          onClick={onToggle}
          className="flex-1 min-w-0 text-left cursor-pointer"
        >
          <div className="flex items-start gap-2">
            <h4 className="font-semibold text-white text-base flex-1">{clip.title}</h4>
            <ViralityBadge
              projectId={clip.project_id}
              clipId={clip.id}
              score={clip.virality_score}
              size="sm"
            />
          </div>
          {clip.description && (
            <p className="text-sm text-slate-400 mt-1 line-clamp-2">{clip.description}</p>
          )}
          <div className="flex items-center gap-2 mt-2">
            {clip.category && (
              <span className={cn('text-[10px] px-2 py-0.5 rounded border font-medium uppercase tracking-wide', categoryColor(clip.category))}>
                {categoryLabel(clip.category)}
              </span>
            )}
            {clip.platforms.length > 0 && (
              <span className="text-[10px] text-slate-500 flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3 text-green-400" />
                {clip.platforms.length}/{ALL_PLATFORMS.length} plataformas
              </span>
            )}
            {hasMedia && (
              <span className="text-[10px] text-slate-500 flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3 text-green-400" />
                {clip.video_clip_path ? 'Video' : 'Audio'} extraído
              </span>
            )}
          </div>
        </div>

        {/* Expand chevron */}
        <button onClick={onToggle} className="flex-shrink-0 pt-1 text-slate-400 hover:text-white">
          {isExpanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
        </button>
      </div>

      {/* Expanded content */}
      {isExpanded && (
        <div className="border-t border-slate-700/50">
          {/* Transcript excerpt */}
          {clip.transcript_excerpt && (
            <div className="px-6 py-4 bg-slate-900/40">
              <p className="text-xs text-slate-400 mb-2">Transcripción en este rango:</p>
              <p className="text-sm text-slate-200 leading-relaxed italic">
                "{clip.transcript_excerpt}"
              </p>
            </div>
          )}

          {/* Trim / timeline */}
          <div className="px-6 py-4 bg-slate-900/20 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <SlidersHorizontal className="w-4 h-4 text-brand-400" />
                <p className="text-sm font-medium text-white">Recortar clip</p>
              </div>
              <button
                onClick={() => (showTrim ? setShowTrim(false) : openTrim())}
                className="text-xs text-brand-400 hover:underline"
              >
                {showTrim ? 'Ocultar' : 'Ajustar límites'}
              </button>
            </div>
            {showTrim && (
              <>
                <Timeline
                  windowStart={trimWindow.start}
                  windowEnd={trimWindow.end}
                  start={pendingStart}
                  end={pendingEnd}
                  onChange={(s, e) => { setPendingStart(s); setPendingEnd(e) }}
                  disabled={trimClip.isPending}
                />
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    onClick={() => trimClip.mutate(
                      { clipId: clip.id, start: pendingStart, end: pendingEnd },
                      { onSuccess: () => setShowTrim(false) },
                    )}
                    loading={trimClip.isPending}
                    disabled={!trimChanged || trimClip.isPending}
                  >
                    <SlidersHorizontal className="w-3.5 h-3.5" />
                    Aplicar recorte
                  </Button>
                  <Button variant="secondary" size="sm" onClick={() => setShowTrim(false)} disabled={trimClip.isPending}>
                    Cancelar
                  </Button>
                </div>
                <p className="text-[10px] text-slate-500">
                  Arrastra los extremos para ajustar el inicio/fin. Al aplicar se vuelve a extraer el audio/video del clip.
                </p>
              </>
            )}
          </div>

          {/* Platform generation */}
          <div className="px-6 py-4 border-t border-slate-700/50 space-y-3">
            <div className="flex items-center gap-2">
              <Wand2 className="w-4 h-4 text-brand-400" />
              <p className="text-sm font-medium text-white">Generar contenido por plataforma</p>
            </div>
            <div className="flex flex-wrap gap-2">
              {ALL_PLATFORMS.map((p) => {
                const Icon = PLATFORM_ICONS[p]
                const isSelected = selectedPlatforms.has(p)
                return (
                  <button
                    key={p}
                    onClick={() => togglePlatform(p)}
                    className={cn(
                      'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-all',
                      isSelected
                        ? 'bg-brand-600/20 text-brand-200 border-brand-500/40'
                        : 'bg-slate-800/60 text-slate-400 border-slate-700/40 hover:text-slate-200'
                    )}
                  >
                    <Icon className="w-3.5 h-3.5" />
                    {CLIP_PLATFORM_LABELS[p]}
                  </button>
                )
              })}
            </div>
            <Button
              size="sm"
              onClick={() => onGenerate(Array.from(selectedPlatforms))}
              loading={isGenerating}
              disabled={selectedPlatforms.size === 0}
            >
              <Wand2 className="w-3.5 h-3.5" />
              Generar para {selectedPlatforms.size} plataforma{selectedPlatforms.size !== 1 ? 's' : ''}
            </Button>

            {/* Existing platform generations */}
            {clip.platforms.length > 0 && (
              <div className="mt-4 space-y-3">
                {clip.platforms.map((gen) => (
                  <PlatformCard
                    key={gen.id}
                    gen={gen}
                    projectId={clip.project_id}
                    clipId={clip.id}
                    onCopied={(field) => {
                      setCopiedField(field)
                      setTimeout(() => setCopiedField(null), 2000)
                    }}
                    copiedField={copiedField}
                  />
                ))}
                {!hasAllPlatforms && (
                  <p className="text-xs text-slate-500 text-center pt-2">
                    Selecciona más plataformas arriba para completar el paquete
                  </p>
                )}
              </div>
            )}
          </div>

          {/* Vertical editor (9:16 Reels/Shorts) */}
          {onOpenVerticalEditor && hasMedia && (
            <div className="px-6 py-4 border-t border-slate-700/50 bg-gradient-to-r from-pink-900/10 to-purple-900/10 space-y-2">
              <div className="flex items-center gap-2">
                <Smartphone className="w-4 h-4 text-pink-400" />
                <p className="text-sm font-medium text-white">Reels / Shorts verticales</p>
              </div>
              <Button
                size="sm"
                onClick={() => onOpenVerticalEditor?.()}
                className="w-full bg-gradient-to-r from-pink-600 to-purple-600 hover:from-pink-700 hover:to-purple-700"
              >
                <Smartphone className="w-3.5 h-3.5" />
                Abrir editor vertical (9:16)
              </Button>
              <p className="text-[10px] text-slate-500 text-center">
                Convierte este clip a formato vertical con subtítulos y fondo
              </p>
            </div>
          )}

          {/* Media extraction */}
          <div className="px-6 py-4 border-t border-slate-700/50 bg-slate-900/20 space-y-3">
            <div className="flex items-center gap-2">
              <Scissors className="w-4 h-4 text-brand-400" />
              <p className="text-sm font-medium text-white">Extraer fragmento de audio/video</p>
            </div>
            {hasMedia ? (
              <div className="flex flex-wrap gap-2">
                {clip.audio_clip_path && (
                  <a
                    href={`/api/v1/projects/${clip.project_id}/clips/${clip.id}/download/audio`}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 rounded-lg text-xs font-medium text-slate-200 border border-slate-700 transition-colors"
                    download
                  >
                    <Download className="w-3.5 h-3.5" />
                    Audio (.mp3)
                  </a>
                )}
                {clip.video_clip_path && (
                  <a
                    href={`/api/v1/projects/${clip.project_id}/clips/${clip.id}/download/video`}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 rounded-lg text-xs font-medium text-slate-200 border border-slate-700 transition-colors"
                    download
                  >
                    <Download className="w-3.5 h-3.5" />
                    Video (.mp4)
                  </a>
                )}
                <button
                  onClick={() => onExtract(false)}
                  disabled={isExtracting}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 disabled:opacity-50 rounded-lg text-xs font-medium text-slate-400 border border-slate-700 transition-colors"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  Re-extraer
                </button>
              </div>
            ) : (
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="secondary" onClick={() => onExtract(false)} loading={isExtracting}>
                  <Scissors className="w-3.5 h-3.5" />
                  Solo audio
                </Button>
                <Button size="sm" onClick={() => onExtract(true)} loading={isExtracting}>
                  <Scissors className="w-3.5 h-3.5" />
                  Audio + Video
                </Button>
              </div>
            )}
            {isExtracting && (
              <p className="text-xs text-amber-400 animate-pulse">
                Extrayendo con ffmpeg (puede tardar 30-60 segundos)...
              </p>
            )}
          </div>

          {/* Delete */}
          <div className="px-6 py-3 border-t border-slate-700/50 flex justify-end">
            <button
              onClick={onDelete}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-500 hover:text-red-400 transition-colors"
            >
              <Trash2 className="w-3.5 h-3.5" />
              Eliminar clip
            </button>
          </div>
        </div>
      )}
    </Card>
  )
}

function PlatformCard({
  gen, projectId, clipId, onCopied, copiedField,
}: {
  gen: ClipGeneration
  projectId: number
  clipId: number
  onCopied: (field: string) => void
  copiedField: string | null
}) {
  const Icon = PLATFORM_ICONS[gen.platform]
  const gradient = CLIP_PLATFORM_COLORS[gen.platform]
  const copy = (text: string, field: string) => {
    navigator.clipboard.writeText(text)
    onCopied(field)
  }

  if (gen.error_message) {
    return (
      <div className="bg-red-900/10 border border-red-800/30 rounded-lg p-3">
        <div className="flex items-center gap-2 text-red-400 text-xs">
          <AlertCircle className="w-3.5 h-3.5" />
          <span className="font-medium">{CLIP_PLATFORM_LABELS[gen.platform]}: {gen.error_message}</span>
        </div>
      </div>
    )
  }

  const fullPost = [
    gen.hook && `🎯 ${gen.hook}`,
    '',
    gen.caption,
    '',
    gen.hashtags && gen.hashtags.length > 0 ? gen.hashtags.join(' ') : '',
    gen.cta ? `\n${gen.cta}` : '',
  ].filter(Boolean).join('\n')

  return (
    <div className={cn('rounded-lg border border-slate-700/50 overflow-hidden')}>
      {/* Platform header */}
      <div className={cn('px-4 py-2.5 flex items-center gap-2 bg-gradient-to-r', gradient)}>
        <Icon className="w-4 h-4 text-white" />
        <span className="text-white font-semibold text-sm">{CLIP_PLATFORM_LABELS[gen.platform]}</span>
        {gen.processing_time != null && (
          <span className="text-white/70 text-xs ml-auto">{gen.processing_time.toFixed(1)}s</span>
        )}
      </div>

      <div className="p-4 space-y-3 bg-slate-900/40">
        {/* Hook */}
        {gen.hook && (
          <Field
            icon={<MessageSquare className="w-3.5 h-3.5" />}
            label="Hook"
            value={gen.hook}
            onCopy={() => copy(gen.hook, `hook-${gen.id}`)}
            copied={copiedField === `hook-${gen.id}`}
          />
        )}

        {/* Caption */}
        {gen.caption && (
          <Field
            icon={<Type className="w-3.5 h-3.5" />}
            label="Caption"
            value={gen.caption}
            onCopy={() => copy(gen.caption, `caption-${gen.id}`)}
            copied={copiedField === `caption-${gen.id}`}
            multiline
          />
        )}

        {/* Hashtags */}
        {gen.hashtags && gen.hashtags.length > 0 && (
          <Field
            icon={<Hash className="w-3.5 h-3.5" />}
            label="Hashtags"
            value={gen.hashtags.join(' ')}
            onCopy={() => copy(gen.hashtags!.join(' '), `tags-${gen.id}`)}
            copied={copiedField === `tags-${gen.id}`}
          />
        )}

        {/* CTA & On-screen text */}
        {(gen.cta || gen.on_screen_text) && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {gen.cta && (
              <div className="bg-slate-800/40 rounded-md p-2">
                <p className="text-[10px] uppercase tracking-wide text-slate-500 mb-1">CTA</p>
                <p className="text-xs text-slate-200">{gen.cta}</p>
              </div>
            )}
            {gen.on_screen_text && (
              <div className="bg-slate-800/40 rounded-md p-2">
                <p className="text-[10px] uppercase tracking-wide text-slate-500 mb-1">Texto en pantalla</p>
                <p className="text-xs text-slate-200 font-semibold">{gen.on_screen_text}</p>
              </div>
            )}
          </div>
        )}

        {/* Copy full post */}
        <button
          onClick={() => copy(fullPost, `full-${gen.id}`)}
          className="w-full flex items-center justify-center gap-1.5 px-3 py-2 bg-slate-800/60 hover:bg-slate-700 rounded-lg text-xs font-medium text-slate-300 border border-slate-700/40 transition-colors"
        >
          {copiedField === `full-${gen.id}` ? <Check className="w-3.5 h-3.5 text-green-400" /> : <Copy className="w-3.5 h-3.5" />}
          {copiedField === `full-${gen.id}` ? '¡Copiado!' : 'Copiar post completo'}
        </button>
      </div>
    </div>
  )
}

function Field({
  icon, label, value, onCopy, copied, multiline = false,
}: {
  icon: React.ReactNode
  label: string
  value: string
  onCopy: () => void
  copied: boolean
  multiline?: boolean
}) {
  return (
    <div className="group relative">
      <div className="flex items-center gap-1.5 mb-1">
        <span className="text-slate-500">{icon}</span>
        <p className="text-[10px] uppercase tracking-wide text-slate-500 font-medium">{label}</p>
      </div>
      <p className={cn(
        'text-sm text-slate-200 pr-8',
        multiline ? 'whitespace-pre-wrap' : ''
      )}>
        {value}
      </p>
      <button
        onClick={onCopy}
        className="absolute top-0 right-0 p-1.5 rounded-md opacity-0 group-hover:opacity-100 hover:bg-slate-700/60 text-slate-400 hover:text-white transition-all"
      >
        {copied ? <Check className="w-3.5 h-3.5 text-green-400" /> : <Copy className="w-3.5 h-3.5" />}
      </button>
    </div>
  )
}
