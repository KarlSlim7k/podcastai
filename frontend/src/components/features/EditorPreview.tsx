import { useEffect, useState } from 'react'
import { Loader2, Square, RefreshCw, Columns2, Volume2, VolumeX, Move, Grid3x3, Sparkles } from 'lucide-react'
import { Button } from '../ui/Button'
import { cn, formatDuration } from '../../utils'
import { VideoTransformOverlay } from './VideoTransformOverlay'
import { SafeAreaOverlay } from './SafeAreaOverlay'
import { LiveOverlay, type LiveOverlayProps } from './LiveOverlay'
import type { VerticalRender, VideoTransform } from '../../types'

const SPEEDS = [0.5, 1, 1.5, 2]
const PLAYBACK_PREFS_KEY = 'vertical-editor-playback-prefs'

interface PlaybackPrefs { volume: number; muted: boolean; speed: number }

function loadPlaybackPrefs(): PlaybackPrefs {
  try {
    const raw = localStorage.getItem(PLAYBACK_PREFS_KEY)
    if (raw) return { volume: 1, muted: false, speed: 1, ...JSON.parse(raw) }
  } catch { /* ignore */ }
  return { volume: 1, muted: false, speed: 1 }
}

interface EditorPreviewProps {
  previewMode: 'draft' | 'final'
  setPreviewMode: (m: 'draft' | 'final') => void
  compareMode: boolean
  toggleCompare: () => void
  draftUrl: string | null
  previewUrl: string | null
  draftPending: boolean
  draftError: string | null
  onRefresh: () => void
  previewRender: VerticalRender | null
  videoRef: React.RefObject<HTMLVideoElement>
  brollCount: number
  // Priority 1 — video transform
  transform: VideoTransform
  onTransformChange: (t: VideoTransform) => void
  onTransformCommit?: () => void
  transformMode: boolean
  // Live overlay (no-ffmpeg-roundtrip preview of subtitle/title/watermark edits)
  liveOverlay: Omit<LiveOverlayProps, 'videoRef'>
  /** True while overlay-only edits are pending a background draft re-sync. */
  overlaySyncing: boolean
}

/**
 * Centered, fixed-height preview workspace. The 9:16 video fills the available
 * height and is centered horizontally. Floating controls (mode, compare,
 * refresh, volume, speed, safe-area) live over the video. In transform mode a
 * bounding-box overlay lets the user move/scale/rotate the main video.
 */
export function EditorPreview({
  previewMode, setPreviewMode, compareMode, toggleCompare,
  draftUrl, previewUrl, draftPending, draftError, onRefresh,
  previewRender, videoRef, brollCount,
  transform, onTransformChange, onTransformCommit, transformMode,
  liveOverlay, overlaySyncing,
}: EditorPreviewProps) {
  const canCompare = !!draftUrl && !!previewUrl
  const [prefs, setPrefs] = useState<PlaybackPrefs>(loadPlaybackPrefs)
  const { volume, muted, speed } = prefs
  const [showSafeArea, setShowSafeArea] = useState(false)

  const setVolume = (v: number) => setPrefs((p) => ({ ...p, volume: v }))
  const setMuted = (m: boolean | ((prev: boolean) => boolean)) =>
    setPrefs((p) => ({ ...p, muted: typeof m === 'function' ? m(p.muted) : m }))
  const setSpeed = (s: number) => setPrefs((p) => ({ ...p, speed: s }))

  // Persist playback preferences across clip switches.
  useEffect(() => {
    try { localStorage.setItem(PLAYBACK_PREFS_KEY, JSON.stringify(prefs)) } catch { /* ignore */ }
  }, [prefs])

  // Keep the live <video> in sync with volume / speed (it remounts when the
  // src changes, so reapply whenever any of these — or the src — change).
  useEffect(() => {
    const v = videoRef.current
    if (!v) return
    v.volume = volume
    v.muted = muted
    v.playbackRate = speed
  }, [volume, muted, speed, draftUrl, previewUrl, previewMode, compareMode, videoRef])

  const showLiveOverlay = !compareMode && previewMode === 'draft'

  return (
    <div className="flex flex-col h-full min-h-0 p-4 gap-2">
      <div className="flex-1 min-h-0 flex items-center justify-center gap-3">
        {compareMode && draftUrl && previewUrl ? (
          <>
            <ComparePane label="Borrador · 480p" badgeClass="bg-amber-500/90 text-amber-950" src={draftUrl} videoRef={videoRef} />
            <ComparePane label="Final · 1080p" badgeClass="bg-emerald-500/90 text-emerald-950" src={previewUrl} />
          </>
        ) : (
          <div className="relative h-full aspect-[9/16] max-w-full bg-slate-950 rounded-xl overflow-hidden flex items-center justify-center">
            {/* thin progress bar while a draft is regenerating */}
            {draftPending && (
              <div className="absolute top-0 left-0 right-0 h-0.5 bg-brand-400/80 animate-pulse z-40" />
            )}

            {previewMode === 'final' ? (
              previewUrl ? (
                <video ref={videoRef} key={previewUrl} src={previewUrl} controls={!transformMode} autoPlay loop className="w-full h-full object-contain" />
              ) : (
                <Placeholder text={'Pulsa "Renderizar" para generar\nun render final en 1080p'} />
              )
            ) : draftPending && !draftUrl ? (
              <div className="flex flex-col items-center gap-3 text-slate-400 p-8 text-center">
                <Loader2 className="w-10 h-10 text-brand-400 animate-spin" />
                <p className="text-sm">Generando preview…<br /><span className="text-xs text-slate-500">480p · ~5-15s</span></p>
              </div>
            ) : draftError ? (
              <div className="flex flex-col items-center gap-3 text-rose-300 p-8 text-center">
                <Square className="w-10 h-10" />
                <p className="text-sm">Error en el preview:<br /><span className="text-xs">{draftError}</span></p>
                <Button variant="secondary" size="sm" onClick={onRefresh}>Reintentar</Button>
              </div>
            ) : draftUrl ? (
              <video ref={videoRef} key={draftUrl} src={draftUrl} controls={!transformMode} autoPlay loop className="w-full h-full object-contain" />
            ) : (
              <div className="flex flex-col items-center gap-3 text-slate-500 p-8 text-center">
                <Square className="w-16 h-16" />
                <p className="text-sm">Configura las opciones a la derecha<br />y genera un preview en vivo.</p>
                <Button variant="secondary" size="sm" onClick={onRefresh} loading={draftPending}>Generar preview</Button>
              </div>
            )}

            {showLiveOverlay && <LiveOverlay videoRef={videoRef} {...liveOverlay} />}
            {showSafeArea && <SafeAreaOverlay />}
            {transformMode && (draftUrl || previewUrl) && (
              <VideoTransformOverlay transform={transform} onChange={onTransformChange} onCommit={onTransformCommit} />
            )}

            {showLiveOverlay && overlaySyncing && (
              <div className="absolute top-2 left-1/2 -translate-x-1/2 z-40 flex items-center gap-1.5 bg-brand-600/90 text-white text-[10px] font-medium px-2 py-1 rounded-lg shadow-lg">
                <Sparkles className="w-3 h-3" />Vista en vivo · renderiza para fijar
              </div>
            )}

            {/* Floating mode toggle (top-left badge) */}
            <div className="absolute top-2 left-2 flex items-center gap-1 bg-slate-900/80 backdrop-blur rounded-lg p-0.5 border border-slate-700/50 shadow-lg z-40">
              <button onClick={() => setPreviewMode('draft')}
                className={cn('px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide rounded focus-visible:ring-2 focus-visible:ring-brand-500',
                  previewMode === 'draft' ? 'bg-amber-500/90 text-amber-950' : 'text-slate-400 hover:text-white')}>
                Borrador
              </button>
              <button onClick={() => setPreviewMode('final')} disabled={!previewRender}
                className={cn('px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide rounded focus-visible:ring-2 focus-visible:ring-brand-500',
                  previewMode === 'final' ? 'bg-emerald-500/90 text-emerald-950' : 'text-slate-400 hover:text-white',
                  !previewRender && 'opacity-40 cursor-not-allowed')}
                title={!previewRender ? 'Renderiza para generar el final' : undefined}>
                Final
              </button>
            </div>

            {transformMode && (
              <div className="absolute top-2 right-2 z-40 flex items-center gap-1 bg-brand-600/90 text-white text-[10px] font-bold uppercase tracking-wide px-2 py-1 rounded-lg shadow-lg">
                <Move className="w-3 h-3" />Transform
              </div>
            )}

            {/* Floating actions (bottom) */}
            <div className="absolute bottom-2 left-2 right-2 flex items-center justify-between gap-2 z-40">
              <div className="flex items-center gap-1.5 bg-slate-900/80 backdrop-blur rounded-lg px-2 py-1 border border-slate-700/50">
                <button onClick={() => setMuted((m) => !m)} className="text-slate-300 hover:text-white" title={muted ? 'Activar sonido' : 'Silenciar'}>
                  {muted || volume === 0 ? <VolumeX className="w-3.5 h-3.5" /> : <Volume2 className="w-3.5 h-3.5" />}
                </button>
                <input type="range" min={0} max={1} step={0.05} value={muted ? 0 : volume}
                  onChange={(e) => { setVolume(Number(e.target.value)); setMuted(false) }}
                  className="w-16 accent-brand-500" title="Volumen" />
                <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))}
                  className="bg-slate-800 border border-slate-700 rounded text-[10px] text-white px-1 py-0.5 focus:outline-none" title="Velocidad">
                  {SPEEDS.map((s) => <option key={s} value={s}>{s}x</option>)}
                </select>
              </div>
              <div className="flex items-center gap-1.5">
                <button onClick={() => setShowSafeArea((v) => !v)}
                  className={cn('p-2 rounded-lg border shadow-lg backdrop-blur transition-colors',
                    showSafeArea ? 'bg-cyan-600 border-cyan-500 text-white' : 'bg-slate-900/80 border-slate-700/50 text-slate-300 hover:text-white')}
                  title="Zona segura 9:16">
                  <Grid3x3 className="w-4 h-4" />
                </button>
                <button onClick={toggleCompare} disabled={!canCompare}
                  className={cn('p-2 rounded-lg border shadow-lg backdrop-blur transition-colors',
                    compareMode ? 'bg-brand-600 border-brand-500 text-white' : 'bg-slate-900/80 border-slate-700/50 text-slate-300 hover:text-white',
                    !canCompare && 'opacity-40 cursor-not-allowed')}
                  title={!canCompare ? 'Necesitas un borrador y un render final' : 'Comparar borrador vs final'}>
                  <Columns2 className="w-4 h-4" />
                </button>
                <button onClick={onRefresh}
                  className="p-2 rounded-lg bg-slate-900/80 border border-slate-700/50 text-slate-300 hover:text-white shadow-lg backdrop-blur"
                  title="Regenerar borrador">
                  <RefreshCw className={cn('w-4 h-4', draftPending && 'animate-spin')} />
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Status line */}
      <div className="h-4 flex items-center justify-center text-center">
        {compareMode ? (
          <p className="text-[10px] text-slate-500">Comparando borrador (480p) vs final (1080p)</p>
        ) : previewMode === 'draft' && draftUrl && !draftPending ? (
          <p className="text-[10px] text-slate-500 flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
            Preview en vivo · B-rolls y marca de agua NO incluidos
            {brollCount > 0 && <span className="text-amber-400">· {brollCount} b-roll(s) — renderiza para verlos</span>}
          </p>
        ) : previewMode === 'final' && previewRender ? (
          <div className="text-[10px] text-slate-500 flex items-center gap-2 flex-wrap justify-center">
            <span>Render #{previewRender.id}</span><span>·</span>
            <span>{formatDuration(previewRender.duration ?? 0)}</span><span>·</span>
            <span>{previewRender.width}x{previewRender.height}</span><span>·</span>
            <span>{((previewRender.file_size ?? 0) / 1024 / 1024).toFixed(1)} MB</span>
          </div>
        ) : null}
      </div>
    </div>
  )
}

function Placeholder({ text }: { text: string }) {
  return (
    <div className="flex flex-col items-center gap-3 text-slate-500 p-8 text-center">
      <Square className="w-16 h-16" />
      <p className="text-sm whitespace-pre-line">{text}</p>
    </div>
  )
}

function ComparePane({ label, badgeClass, src, videoRef }: {
  label: string; badgeClass: string; src: string; videoRef?: React.Ref<HTMLVideoElement>
}) {
  return (
    <div className="relative h-full aspect-[9/16] max-w-full bg-slate-950 rounded-xl overflow-hidden">
      <video ref={videoRef} key={src} src={src} controls loop className="w-full h-full object-contain" />
      <div className={cn('absolute top-2 left-2 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide shadow-lg', badgeClass)}>{label}</div>
    </div>
  )
}
