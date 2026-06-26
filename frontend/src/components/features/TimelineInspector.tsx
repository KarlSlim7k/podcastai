import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Trash2, Copy, X, RotateCcw, Move, ChevronsLeftRight } from 'lucide-react'
import toast from 'react-hot-toast'
import { ColorRow } from './VerticalEditorParts'
import { cn } from '../../utils'
import type { BrollPlacement, CaptionWord, VideoTransform, VerticalTitlePosition } from '../../types'

export type Selection =
  | { kind: 'broll'; indices: Set<number> }
  | { kind: 'caption'; indices: Set<number> } // representative word indices (one per merged segment)
  | { kind: 'title' }
  | { kind: 'video' }

const TITLE_POSITIONS: [VerticalTitlePosition, string][] = [
  ['top', '↑ Arriba'], ['center', '● Centro'], ['bottom', '↓ Abajo'],
]

export interface TimelineInspectorProps {
  selection: Selection
  /** The selected block's DOM node — the popover anchors to it. */
  anchorEl: HTMLElement | null
  /** The scrollable timeline viewport, so the popover follows horizontal scroll. */
  scrollEl?: HTMLElement | null
  onClose: () => void
  // B-roll(s)
  brollPlacements: BrollPlacement[]
  onBrollUpdate: (index: number, patch: Partial<BrollPlacement>) => void
  onBrollRemove: (index: number) => void
  onBrollDuplicate?: (index: number) => void
  // Caption word(s)
  words: CaptionWord[]
  onUpdateCaptionWord?: (index: number, patch: Partial<CaptionWord>) => void
  onDeleteCaptionWord?: (index: number) => void
  // Title
  titleText: string
  setTitleText: (v: string) => void
  titleColor: string
  setTitleColor: (v: string) => void
  titlePosition: VerticalTitlePosition
  setTitlePosition: (v: VerticalTitlePosition) => void
  // Video transform
  videoTransform?: VideoTransform
  setVideoTransform?: (t: VideoTransform) => void
  onEditInVideoTab?: () => void
  onResetTransform?: () => void
}

/** Position the popover above the anchor (or below if there's no room), clamped to the viewport. */
function usePopoverPosition(anchorEl: HTMLElement | null, scrollEl: HTMLElement | null | undefined, selection: Selection) {
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null)

  useLayoutEffect(() => {
    const compute = () => {
      const a = anchorEl?.getBoundingClientRect()
      const el = ref.current
      if (!a || !el) return
      const M = 8
      const pw = el.offsetWidth
      const ph = el.offsetHeight
      let left = a.left + a.width / 2 - pw / 2
      left = Math.max(M, Math.min(left, window.innerWidth - pw - M))
      let top = a.top - ph - M               // prefer above
      if (top < M) top = a.bottom + M        // flip below
      top = Math.max(M, Math.min(top, window.innerHeight - ph - M))
      setPos({ left, top })
    }
    compute()
    window.addEventListener('resize', compute)
    window.addEventListener('scroll', compute, true)
    scrollEl?.addEventListener('scroll', compute, { passive: true })
    return () => {
      window.removeEventListener('resize', compute)
      window.removeEventListener('scroll', compute, true)
      scrollEl?.removeEventListener('scroll', compute)
    }
    // Re-measure when the selection (and therefore the body size) changes.
  }, [anchorEl, scrollEl, selection])

  return { ref, pos }
}

/** Selection-aware floating inspector popover anchored to the selected block. */
export function TimelineInspector(p: TimelineInspectorProps) {
  const { ref, pos } = usePopoverPosition(p.anchorEl, p.scrollEl, p.selection)

  // Read the latest anchor/onClose through refs so the once-bound listener
  // doesn't capture a stale anchor — otherwise clicking a *different* block
  // (which re-anchors the popover) would be treated as an outside click and
  // close it before the new selection sticks.
  const anchorRef = useRef(p.anchorEl)
  anchorRef.current = p.anchorEl
  const onCloseRef = useRef(p.onClose)
  onCloseRef.current = p.onClose

  // Close on Escape or a click outside the popover (and outside the anchor).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onCloseRef.current() }
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node
      if (ref.current?.contains(t)) return
      if (anchorRef.current?.contains(t)) return
      onCloseRef.current()
    }
    window.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onDown)
    return () => {
      window.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onDown)
    }
  }, [ref])

  const body = p.selection.kind === 'broll' ? <BrollBody {...p} indices={p.selection.indices} />
    : p.selection.kind === 'caption' ? <CaptionBody {...p} indices={p.selection.indices} />
    : p.selection.kind === 'video' ? <VideoBody {...p} />
    : <TitleBody {...p} />

  return (
    <div
      ref={ref}
      role="dialog"
      className="fixed z-50 max-w-[92vw] rounded-lg border border-brand-500/60 bg-slate-900/95 backdrop-blur-sm shadow-2xl"
      style={{
        left: pos?.left ?? -9999,
        top: pos?.top ?? -9999,
        visibility: pos ? 'visible' : 'hidden',
      }}
    >
      <button onClick={p.onClose} title="Cerrar inspector"
        className="absolute right-1 top-1 p-1 text-slate-500 hover:text-white z-10">
        <X className="w-3.5 h-3.5" />
      </button>
      {body}
    </div>
  )
}

function BrollBody({
  indices, brollPlacements, onBrollUpdate, onBrollRemove, onBrollDuplicate,
}: TimelineInspectorProps & { indices: Set<number> }) {
  const list = [...indices].sort((a, b) => a - b)
  const single = list.length === 1 ? brollPlacements[list[0]] : null
  const bulkOpacity = (v: number) => list.forEach((i) => onBrollUpdate(i, { opacity: v }))
  const bulkRemove = () => {
    const count = list.length
    ;[...list].sort((a, b) => b - a).forEach(onBrollRemove) // highest-first keeps indices valid
    toast(count > 1 ? `${count} b-rolls eliminados` : 'B-roll eliminado', { icon: '🗑️' })
  }

  if (single) {
    return (
      <div className="flex items-center gap-3 px-3 py-2.5 pr-8">
        <img src={single.url} alt="" className="w-8 h-12 object-cover rounded border border-slate-700 flex-shrink-0"
          onError={(e) => { (e.currentTarget as HTMLImageElement).style.opacity = '0.3' }} />
        <div className="flex flex-col gap-1.5">
          <span className="text-xs text-slate-400">
            B-roll · {single.start.toFixed(1)}s → {single.end.toFixed(1)}s ({(single.end - single.start).toFixed(1)}s)
          </span>
          <div className="flex items-center gap-2">
            <label className="text-[11px] text-slate-400">Opacidad</label>
            <input type="range" min={10} max={100} step={5} value={Math.round(single.opacity * 100)}
              onChange={(e) => bulkOpacity(Number(e.target.value) / 100)} className="w-28 accent-brand-500" />
            <span className="text-[11px] font-mono text-white w-9 text-right">{Math.round(single.opacity * 100)}%</span>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          {onBrollDuplicate && (
            <button onClick={() => onBrollDuplicate(list[0])}
              className="flex items-center gap-1 px-2 py-1 rounded text-xs text-slate-300 hover:bg-slate-700/50 border border-slate-700 focus-visible:ring-2 focus-visible:ring-brand-500">
              <Copy className="w-3.5 h-3.5" /> Duplicar
            </button>
          )}
          <button onClick={bulkRemove}
            className="flex items-center gap-1 px-2 py-1 rounded text-xs text-rose-300 hover:bg-rose-900/30 border border-rose-900/50 focus-visible:ring-2 focus-visible:ring-rose-500">
            <Trash2 className="w-3.5 h-3.5" /> Eliminar
          </button>
        </div>
      </div>
    )
  }

  const avgOpacity = list.reduce((s, i) => s + (brollPlacements[i]?.opacity ?? 1), 0) / Math.max(1, list.length)
  return (
    <div className="flex items-center gap-3 px-3 py-2.5 pr-8">
      <span className="text-xs text-cyan-300 font-medium">{list.length} B-rolls seleccionados</span>
      <div className="flex items-center gap-2">
        <label className="text-[11px] text-slate-400">Opacidad (todos)</label>
        <input type="range" min={10} max={100} step={5} value={Math.round(avgOpacity * 100)}
          onChange={(e) => bulkOpacity(Number(e.target.value) / 100)} className="w-28 accent-brand-500" />
      </div>
      <button onClick={bulkRemove}
        className="flex items-center gap-1 px-2 py-1 rounded text-xs text-rose-300 hover:bg-rose-900/30 border border-rose-900/50 focus-visible:ring-2 focus-visible:ring-rose-500">
        <Trash2 className="w-3.5 h-3.5" /> Eliminar todos
      </button>
    </div>
  )
}

function CaptionBody({
  indices, words, onUpdateCaptionWord, onDeleteCaptionWord,
}: TimelineInspectorProps & { indices: Set<number> }) {
  const list = [...indices].sort((a, b) => a - b)
  const single = list.length === 1 ? list[0] : null

  // ── Single-word editor ──
  const word = single != null ? words[single] : undefined
  const [text, setText] = useState(word?.word ?? '')
  const [start, setStart] = useState(word?.start ?? 0)
  const [end, setEnd] = useState(word?.end ?? 0)
  useEffect(() => { setText(word?.word ?? ''); setStart(word?.start ?? 0); setEnd(word?.end ?? 0) }, [word])

  // Debounce text edits (500ms) so typing doesn't fire a mutation per keystroke.
  const textTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => () => { if (textTimer.current) clearTimeout(textTimer.current) }, [])
  const onTextChange = (v: string) => {
    setText(v)
    if (single == null) return
    if (textTimer.current) clearTimeout(textTimer.current)
    textTimer.current = setTimeout(() => onUpdateCaptionWord?.(single, { word: v }), 500)
  }
  const commitTimes = () => { if (single != null) onUpdateCaptionWord?.(single, { start, end }) }

  // ── Bulk editor ──
  const [bulkText, setBulkText] = useState('')
  const shiftAll = (deltaMs: number) => {
    const d = deltaMs / 1000
    list.forEach((i) => {
      const w = words[i]
      if (!w) return
      onUpdateCaptionWord?.(i, { start: Math.max(0, w.start + d), end: Math.max(0, w.end + d) })
    })
  }
  const replaceAll = () => {
    if (!bulkText.trim()) return
    list.forEach((i) => onUpdateCaptionWord?.(i, { word: bulkText }))
  }
  const deleteAll = () => [...list].sort((a, b) => b - a).forEach((i) => onDeleteCaptionWord?.(i))

  if (single != null && word) {
    return (
      <div className="flex items-center gap-2.5 px-3 py-2.5 pr-8">
        <span className="text-xs text-amber-300 font-medium flex-shrink-0">Subtítulo</span>
        <input value={text} onChange={(e) => onTextChange(e.target.value)} onBlur={() => single != null && onUpdateCaptionWord?.(single, { word: text })}
          className="w-32 bg-slate-950 border border-slate-700 rounded px-1.5 py-1 text-xs text-white focus:outline-none focus:border-brand-500" />
        <label className="text-[11px] text-slate-400">Inicio</label>
        <input type="number" step={0.05} value={start.toFixed(2)} onChange={(e) => setStart(Number(e.target.value))} onBlur={commitTimes}
          className="w-16 bg-slate-950 border border-slate-700 rounded px-1.5 py-1 text-xs text-white font-mono focus:outline-none focus:border-brand-500" />
        <label className="text-[11px] text-slate-400">Fin</label>
        <input type="number" step={0.05} value={end.toFixed(2)} onChange={(e) => setEnd(Number(e.target.value))} onBlur={commitTimes}
          className="w-16 bg-slate-950 border border-slate-700 rounded px-1.5 py-1 text-xs text-white font-mono focus:outline-none focus:border-brand-500" />
        <button onClick={() => onDeleteCaptionWord?.(single)}
          className="flex items-center gap-1 px-2 py-1 rounded text-xs text-rose-300 hover:bg-rose-900/30 border border-rose-900/50 focus-visible:ring-2 focus-visible:ring-rose-500">
          <Trash2 className="w-3.5 h-3.5" /> Eliminar
        </button>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2 px-3 py-2.5 pr-8">
      <span className="text-xs text-cyan-300 font-medium">{list.length} palabras seleccionadas</span>
      <div className="flex items-center gap-2 flex-wrap">
        <button onClick={() => shiftAll(-100)}
          className="px-2 py-1 rounded text-xs text-slate-300 hover:bg-slate-700/50 border border-slate-700 font-mono">−100ms</button>
        <button onClick={() => shiftAll(100)}
          className="px-2 py-1 rounded text-xs text-slate-300 hover:bg-slate-700/50 border border-slate-700 font-mono">+100ms</button>
        <input value={bulkText} onChange={(e) => setBulkText(e.target.value)} placeholder="Reemplazar texto…"
          className="w-36 bg-slate-950 border border-slate-700 rounded px-1.5 py-1 text-xs text-white focus:outline-none focus:border-brand-500" />
        <button onClick={replaceAll} disabled={!bulkText.trim()}
          className="px-2 py-1 rounded text-xs text-slate-300 hover:bg-slate-700/50 border border-slate-700 disabled:opacity-40">Aplicar</button>
        <button onClick={deleteAll}
          className="flex items-center gap-1 px-2 py-1 rounded text-xs text-rose-300 hover:bg-rose-900/30 border border-rose-900/50">
          <Trash2 className="w-3.5 h-3.5" /> Eliminar
        </button>
      </div>
    </div>
  )
}

function TitleBody({
  titleText, setTitleText, titleColor, setTitleColor, titlePosition, setTitlePosition,
}: TimelineInspectorProps) {
  return (
    <div className="flex items-center gap-3 px-3 py-2.5 pr-8">
      <span className="text-xs text-violet-300 font-medium flex-shrink-0">Título</span>
      <input value={titleText} onChange={(e) => setTitleText(e.target.value)} placeholder="Título del clip"
        className="w-44 bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs text-white focus:outline-none focus:border-brand-500" />
      <div className="w-40"><ColorRow label="Color" value={titleColor} onChange={setTitleColor} /></div>
      <div className="flex items-center gap-1">
        {TITLE_POSITIONS.map(([val, label]) => (
          <button key={val} onClick={() => setTitlePosition(val)}
            className={cn('px-2 py-1 text-[11px] rounded border transition-colors',
              titlePosition === val ? 'bg-brand-500 border-brand-500 text-white' : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-white')}>
            {label}
          </button>
        ))}
      </div>
    </div>
  )
}

function VideoBody({ videoTransform, setVideoTransform, onEditInVideoTab, onResetTransform }: TimelineInspectorProps) {
  const t = videoTransform
  if (!t || !setVideoTransform) {
    return (
      <div className="flex items-center gap-3 px-3 py-2.5 pr-8">
        <span className="text-xs text-brand-300 font-medium">Video</span>
        <button onClick={onEditInVideoTab}
          className="flex items-center gap-1 px-2 py-1 rounded text-xs text-slate-300 hover:bg-slate-700/50 border border-slate-700">
          <Move className="w-3.5 h-3.5" /> Editar en pestaña Video
        </button>
      </div>
    )
  }
  return (
    <div className="flex items-center gap-3 px-3 py-2.5 pr-8">
      <span className="text-xs text-brand-300 font-medium flex-shrink-0">Video</span>
      <div className="flex items-center gap-1.5">
        <label className="text-[11px] text-slate-400">Escala</label>
        <input type="range" min={50} max={200} step={1} value={t.scale}
          onChange={(e) => setVideoTransform({ ...t, scale: Number(e.target.value) })} className="w-24 accent-brand-500" />
        <span className="text-[11px] font-mono text-white w-9 text-right">{t.scale}%</span>
      </div>
      <div className="flex items-center gap-1.5">
        <label className="text-[11px] text-slate-400">Rotar</label>
        <input type="range" min={-180} max={180} step={1} value={t.rotation}
          onChange={(e) => setVideoTransform({ ...t, rotation: Number(e.target.value) })} className="w-24 accent-brand-500" />
        <span className="text-[11px] font-mono text-white w-9 text-right">{t.rotation}°</span>
      </div>
      <button onClick={onEditInVideoTab}
        className="flex items-center gap-1 px-2 py-1 rounded text-xs text-slate-300 hover:bg-slate-700/50 border border-slate-700" title="Mover/escalar en el lienzo">
        <ChevronsLeftRight className="w-3.5 h-3.5" /> Más
      </button>
      <button onClick={onResetTransform}
        className="flex items-center gap-1 px-2 py-1 rounded text-xs text-slate-300 hover:bg-slate-700/50 border border-slate-700">
        <RotateCcw className="w-3.5 h-3.5" /> Reiniciar
      </button>
    </div>
  )
}
