import {
  forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState,
} from 'react'
import {
  ZoomIn, ZoomOut, Maximize2, Magnet, Scissors, Film, ImageIcon,
  Captions, Heading1, Check, Clock, Crop,
  Copy, Trash2, Crosshair, RotateCcw, Move, Pencil,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { useTimelineDrag } from '../../hooks/useTimelineDrag'
import { useSyncPlayhead } from '../../hooks/useSyncPlayhead'
import { TimelineRuler } from './TimelineRuler'
import { TimelinePlayhead } from './TimelinePlayhead'
import { TimelineTrack } from './TimelineTrack'
import { TimelineBlock, type ResizeEdge } from './TimelineBlock'
import { TimelineInspector, type Selection } from './TimelineInspector'
import { BlockContextMenu, type MenuItem } from './BlockContextMenu'
import { MainVideoBar, TrimOverlay, mergeWords } from './TimeLineV2Parts'
import { Button } from '../ui/Button'
import { cn, formatDuration } from '../../utils'
import type {
  BrollPlacement, CaptionWord, TimelineTrackType, VerticalTitlePosition, VideoTransform,
} from '../../types'

// Stable palette so each speaker keeps the same badge color across the track.
const SPEAKER_COLORS = ['#22d3ee', '#a78bfa', '#f472b6', '#fbbf24', '#34d399']
const speakerColor = (s: string) => {
  let h = 0
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0
  return SPEAKER_COLORS[h % SPEAKER_COLORS.length]
}
// "SPEAKER_00" → "S1"; otherwise a short uppercase tag.
const speakerLabel = (s: string) => {
  const m = s.match(/(\d+)/)
  return m ? `S${Number(m[1]) + 1}` : s.slice(0, 3).toUpperCase()
}

// ── Tunables ────────────────────────────────────────────────────────────────
const BASE_PPS = 50          // pixels per second at 1x zoom
const MIN_ZOOM = 0.5
const MAX_ZOOM = 20
const LABEL_W = 120          // pinned label-column width
const RULER_H = 28
const TRACK_H = 56
const SNAP_PX = 8
const MIN_BROLL = 0.5        // seconds

export interface TimeLineV2Props {
  // Clip info (absolute seconds for clip bounds; everything else clip-relative)
  clipDuration: number
  clipStart: number
  clipEnd: number

  // Trim (absolute seconds, operates over a window around the clip)
  trimWindowStart: number
  trimWindowEnd: number
  pendingStart: number
  pendingEnd: number
  onTrimChange: (start: number, end: number) => void
  onApplyTrim?: () => void
  trimApplying?: boolean
  trimChanged?: boolean

  // B-rolls (clip-relative seconds)
  brollPlacements: BrollPlacement[]
  onBrollUpdate: (index: number, patch: Partial<BrollPlacement>) => void
  onBrollRemove: (index: number) => void
  onBrollSplit?: (index: number, at: number) => void
  onBrollDuplicate?: (index: number) => void
  /** Called when a split is attempted but the playhead isn't on a cuttable b-roll. */
  onSplitMiss?: () => void

  // Captions / title
  words?: CaptionWord[]
  onUpdateCaptionWord?: (index: number, patch: Partial<CaptionWord>) => void
  onDeleteCaptionWord?: (index: number) => void
  addTitle: boolean
  titleText: string | null
  setTitleText?: (v: string) => void
  titleColor?: string
  setTitleColor?: (v: string) => void
  titlePosition?: VerticalTitlePosition
  setTitlePosition?: (v: VerticalTitlePosition) => void

  // Click-to-edit signals — bubble up so the page can switch right-panel tabs
  onVideoTrackClick?: () => void
  onCaptionBlockClick?: () => void
  onTitleBlockClick?: () => void

  // Video transform (drives the video-block inspector popover)
  videoTransform?: VideoTransform
  setVideoTransform?: (t: VideoTransform) => void
  onResetTransform?: () => void

  // Speaker badges on caption blocks (omitted entirely when undiarized)
  speakerForClipTime?: (clipRelStart: number) => string | null

  // Playhead sync
  videoRef?: React.RefObject<HTMLVideoElement>
  onPlayheadChange?: (time: number) => void
  /** Bumped by the page when the video source changes, to reset the playhead to 0. */
  playheadResetSignal?: number

  disabled?: boolean
}

/** Imperative API so the page's keyboard shortcuts can drive the timeline. */
export interface TimeLineV2Handle {
  toggleTrim: () => void
  fit: () => void
  zoomIn: () => void
  zoomOut: () => void
  split: () => void
}

type DragCtx =
  | { kind: 'playhead' }
  | { kind: 'scrub'; startClientX: number; startScroll: number; moved: boolean }
  | { kind: 'broll-move'; index: number; startClientX: number; origStart: number; origEnd: number }
  | { kind: 'broll-resize'; index: number; edge: ResizeEdge; startClientX: number; origStart: number; origEnd: number }
  | { kind: 'trim'; edge: 'start' | 'end'; startClientX: number }

interface DragPreview { index: number; start: number; end: number }

interface CtxMenuBase { x: number; y: number; el: HTMLElement | null }
type CtxMenu =
  | (CtxMenuBase & { kind: 'broll'; index: number })
  | (CtxMenuBase & { kind: 'caption'; wordIndex: number })
  | (CtxMenuBase & { kind: 'title' })
  | (CtxMenuBase & { kind: 'video' })
// Plain Omit collapses a union to its common keys; distribute it so each
// member keeps its discriminant-specific fields (index / wordIndex).
type DistributiveOmit<T, K extends keyof T> = T extends unknown ? Omit<T, K> : never
type CtxMenuInit = DistributiveOmit<CtxMenu, 'x' | 'y' | 'el'>

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))
const round2 = (n: number) => Math.round(n * 100) / 100

/** CapCut-style multi-track timeline for the vertical editor. */
export const TimeLineV2 = forwardRef<TimeLineV2Handle, TimeLineV2Props>(function TimeLineV2({
  clipDuration, clipStart, clipEnd,
  trimWindowStart, trimWindowEnd, pendingStart, pendingEnd, onTrimChange,
  onApplyTrim, trimApplying, trimChanged,
  brollPlacements, onBrollUpdate, onBrollRemove, onBrollSplit, onBrollDuplicate, onSplitMiss,
  words, onUpdateCaptionWord, onDeleteCaptionWord,
  addTitle, titleText, setTitleText, titleColor, setTitleColor, titlePosition, setTitlePosition,
  onVideoTrackClick, onCaptionBlockClick, onTitleBlockClick,
  videoTransform, setVideoTransform, onResetTransform, speakerForClipTime,
  videoRef, onPlayheadChange, playheadResetSignal, disabled,
}: TimeLineV2Props, ref) {
  const viewportRef = useRef<HTMLDivElement>(null)
  const [zoom, setZoom] = useState(1)
  const [snap, setSnap] = useState(true)
  const [snapWhole, setSnapWhole] = useState(false)
  const [trimMode, setTrimMode] = useState(false)
  const [selection, setSelection] = useState<Selection | null>(null)
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null)
  const [contextMenu, setContextMenu] = useState<CtxMenu | null>(null)
  const [scrubCursor, setScrubCursor] = useState<number | null>(null)
  const [playhead, setPlayhead] = useState(0)
  const [dragPreview, setDragPreview] = useState<DragPreview | null>(null)
  const dragPreviewRef = useRef<DragPreview | null>(null)
  dragPreviewRef.current = dragPreview
  const [snapLine, setSnapLine] = useState<number | null>(null)
  const [collapsed, setCollapsed] = useState<Record<TimelineTrackType, boolean>>({
    video: false, broll: false, caption: false, title: false,
  })
  const [viewportW, setViewportW] = useState(0)

  const pps = BASE_PPS * zoom
  const contentWidth = Math.max(clipDuration * pps, 1)
  const winStart = trimWindowStart
  const winSpan = Math.max(0.001, trimWindowEnd - trimWindowStart)

  // Keep the broll selection valid as placements change.
  useEffect(() => {
    setSelection((prev) => {
      if (prev?.kind !== 'broll') return prev
      const next = new Set([...prev.indices].filter((i) => i < brollPlacements.length))
      return next.size ? { kind: 'broll', indices: next } : null
    })
  }, [brollPlacements.length])

  const selectBroll = useCallback((i: number, e: React.PointerEvent) => {
    setSelection((prev) => {
      if (e.shiftKey && prev?.kind === 'broll') {
        const next = new Set(prev.indices)
        if (next.has(i)) next.delete(i); else next.add(i)
        return next.size ? { kind: 'broll', indices: next } : null
      }
      return { kind: 'broll', indices: new Set([i]) }
    })
    setAnchorEl(e.currentTarget as HTMLElement)
  }, [])

  const selectCaption = useCallback((wordIndex: number, e: React.PointerEvent) => {
    setSelection((prev) => {
      if (e.shiftKey && prev?.kind === 'caption') {
        const next = new Set(prev.indices)
        if (next.has(wordIndex)) next.delete(wordIndex); else next.add(wordIndex)
        return next.size ? { kind: 'caption', indices: next } : null
      }
      return { kind: 'caption', indices: new Set([wordIndex]) }
    })
    setAnchorEl(e.currentTarget as HTMLElement)
  }, [])

  // Keep the caption selection valid as the word list changes.
  useEffect(() => {
    setSelection((prev) => {
      if (prev?.kind !== 'caption') return prev
      const n = words?.length ?? 0
      const next = new Set([...prev.indices].filter((i) => i < n))
      return next.size ? { kind: 'caption', indices: next } : null
    })
  }, [words?.length])

  // Snap the playhead back to 0 when the page swaps the video source.
  useEffect(() => { setPlayhead(0) }, [playheadResetSignal])

  // ── Playhead ↔ video sync ─────────────────────────────────────────────────
  const onPlayheadChangeRef = useRef(onPlayheadChange)
  onPlayheadChangeRef.current = onPlayheadChange
  const sync = useSyncPlayhead(videoRef, useCallback((t: number) => {
    setPlayhead(t)
    onPlayheadChangeRef.current?.(t)
  }, []))

  const setPlayheadAndSeek = useCallback((t: number) => {
    const c = clamp(t, 0, clipDuration)
    setPlayhead(c)
    sync.seek(c)
    onPlayheadChangeRef.current?.(c)
  }, [clipDuration, sync])

  // ── Coordinate helpers ──────────────────────────────────────────────────────
  const contentXAtClient = useCallback((clientX: number) => {
    const el = viewportRef.current
    if (!el) return 0
    const rect = el.getBoundingClientRect()
    return clientX - rect.left + el.scrollLeft - LABEL_W
  }, [])
  const timeAtClient = useCallback(
    (clientX: number) => clamp(contentXAtClient(clientX) / pps, 0, clipDuration),
    [contentXAtClient, pps, clipDuration],
  )
  const trimTimeAtClient = useCallback((clientX: number) => {
    const pct = clamp(contentXAtClient(clientX) / contentWidth, 0, 1)
    return winStart + pct * winSpan
  }, [contentXAtClient, contentWidth, winStart, winSpan])

  // ── Snapping ────────────────────────────────────────────────────────────────
  const snapTargets = useCallback((excludeIndex: number) => {
    const ts = [0, clipDuration, playhead]
    brollPlacements.forEach((b, i) => {
      if (i !== excludeIndex) { ts.push(b.start, b.end) }
    })
    return ts
  }, [clipDuration, playhead, brollPlacements])

  const applySnap = useCallback((t: number, excludeIndex: number): { t: number; line: number | null } => {
    // Snap-to-1s mode wins: hard-quantize edges to whole seconds.
    if (snapWhole) {
      const w = clamp(Math.round(t), 0, clipDuration)
      return { t: w, line: w }
    }
    if (!snap) return { t, line: null }
    const thr = SNAP_PX / pps
    let best: number | null = null
    let bestD = thr
    for (const tgt of snapTargets(excludeIndex)) {
      const d = Math.abs(t - tgt)
      if (d < bestD) { bestD = d; best = tgt }
    }
    return best != null ? { t: best, line: best } : { t, line: null }
  }, [snap, snapWhole, pps, clipDuration, snapTargets])

  // ── Drag handling ────────────────────────────────────────────────────────────
  const drag = useTimelineDrag<DragCtx>({
    onStart: (ctx, e) => {
      if (ctx.kind === 'playhead') setPlayheadAndSeek(timeAtClient(e.clientX))
    },
    onMove: (ctx, e) => {
      switch (ctx.kind) {
        case 'playhead': {
          const { t, line } = applySnap(timeAtClient(e.clientX), -1)
          setSnapLine(line)
          setPlayheadAndSeek(t)
          break
        }
        case 'scrub': {
          const dx = e.clientX - ctx.startClientX
          if (Math.abs(dx) > 4) ctx.moved = true
          if (ctx.moved) {
            const el = viewportRef.current
            if (el) el.scrollLeft = ctx.startScroll - dx
          }
          // A distinct cyan cursor shows where the pointer is while panning,
          // so it never reads as the (amber) playhead.
          setScrubCursor(timeAtClient(e.clientX))
          break
        }
        case 'broll-move': {
          const dt = (e.clientX - ctx.startClientX) / pps
          const dur = ctx.origEnd - ctx.origStart
          let ns = clamp(ctx.origStart + dt, 0, clipDuration - dur)
          const sStart = applySnap(ns, ctx.index)
          const sEnd = applySnap(ns + dur, ctx.index)
          if (sStart.line != null) { ns = sStart.t; setSnapLine(sStart.line) }
          else if (sEnd.line != null) { ns = sEnd.t - dur; setSnapLine(sEnd.line) }
          else setSnapLine(null)
          ns = clamp(ns, 0, clipDuration - dur)
          setDragPreview({ index: ctx.index, start: ns, end: ns + dur })
          break
        }
        case 'broll-resize': {
          const dt = (e.clientX - ctx.startClientX) / pps
          if (ctx.edge === 'start') {
            let ns = clamp(ctx.origStart + dt, 0, ctx.origEnd - MIN_BROLL)
            const s = applySnap(ns, ctx.index)
            if (s.line != null) { ns = clamp(s.t, 0, ctx.origEnd - MIN_BROLL); setSnapLine(s.line) }
            else setSnapLine(null)
            setDragPreview({ index: ctx.index, start: ns, end: ctx.origEnd })
          } else {
            let ne = clamp(ctx.origEnd + dt, ctx.origStart + MIN_BROLL, clipDuration)
            const s = applySnap(ne, ctx.index)
            if (s.line != null) { ne = clamp(s.t, ctx.origStart + MIN_BROLL, clipDuration); setSnapLine(s.line) }
            else setSnapLine(null)
            setDragPreview({ index: ctx.index, start: ctx.origStart, end: ne })
          }
          break
        }
        case 'trim': {
          const t = trimTimeAtClient(e.clientX)
          if (ctx.edge === 'start') {
            const ns = clamp(t, trimWindowStart, pendingEnd - 1)
            onTrimChange(round2(ns), pendingEnd)
          } else {
            const ne = clamp(t, pendingStart + 1, trimWindowEnd)
            onTrimChange(pendingStart, round2(ne))
          }
          break
        }
      }
    },
    onEnd: (ctx) => {
      if (ctx.kind === 'scrub' && !ctx.moved) {
        setPlayheadAndSeek(timeAtClient(ctx.startClientX))
      }
      if (ctx.kind === 'broll-move' || ctx.kind === 'broll-resize') {
        const p = dragPreviewRef.current
        if (p) {
          onBrollUpdate(p.index, { start: round2(p.start), end: round2(p.end) })
          if (ctx.kind === 'broll-move' && Math.abs(p.start - ctx.origStart) > 0.5) {
            toast(`B-roll movido a ${formatDuration(p.start)}`, { icon: '↔️' })
          }
        }
      }
      setDragPreview(null)
      setSnapLine(null)
      setScrubCursor(null)
    },
  })

  // ── Wheel zoom (Ctrl/⌘ + scroll), keeping the time under the cursor fixed ────
  useEffect(() => {
    const el = viewportRef.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey && !e.metaKey) return
      e.preventDefault()
      const rect = el.getBoundingClientRect()
      const localX = e.clientX - rect.left - LABEL_W
      const timeAtCursor = (localX + el.scrollLeft) / pps
      const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15
      const newZoom = clamp(zoom * factor, MIN_ZOOM, MAX_ZOOM)
      if (newZoom === zoom) return
      const newPps = BASE_PPS * newZoom
      setZoom(newZoom)
      requestAnimationFrame(() => {
        if (viewportRef.current) viewportRef.current.scrollLeft = timeAtCursor * newPps - localX
      })
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [zoom, pps])

  // ── Container resize → track width for "fit" ────────────────────────────────
  useEffect(() => {
    const el = viewportRef.current
    if (!el) return
    const ro = new ResizeObserver((entries) => setViewportW(entries[0].contentRect.width))
    ro.observe(el)
    setViewportW(el.clientWidth)
    return () => ro.disconnect()
  }, [])

  const zoomBy = (factor: number) => setZoom((z) => clamp(z * factor, MIN_ZOOM, MAX_ZOOM))
  const fitToScreen = () => {
    const avail = Math.max(50, viewportW - LABEL_W - 8)
    setZoom(clamp(avail / (clipDuration * BASE_PPS), MIN_ZOOM, MAX_ZOOM))
    if (viewportRef.current) viewportRef.current.scrollLeft = 0
  }

  // ── Split (Scissors) ────────────────────────────────────────────────────────
  // Cut the b-roll under the playhead into two pieces, refusing the cut if
  // either piece would fall under the minimum length.
  const doSplit = useCallback(() => {
    const t = playhead
    const idx = brollPlacements.findIndex(
      (b) => t > b.start + MIN_BROLL && t < b.end - MIN_BROLL,
    )
    if (idx < 0) { onSplitMiss?.(); return }
    onBrollSplit?.(idx, round2(t))
    setSelection(null)
  }, [playhead, brollPlacements, onBrollSplit, onSplitMiss])

  useImperativeHandle(ref, () => ({
    toggleTrim: () => setTrimMode((v) => !v),
    fit: fitToScreen,
    zoomIn: () => zoomBy(1.3),
    zoomOut: () => zoomBy(1 / 1.3),
    split: doSplit,
  }))

  // ── Delete / nudge the current selection via keyboard ───────────────────────
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (disabled) return // a full-screen modal (shortcuts/save preset) owns the keyboard while open
      if (!selection) return
      const tag = (e.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return

      if (e.key === 'Delete' || e.key === 'Backspace') {
        e.preventDefault()
        if (selection.kind === 'broll') {
          const count = selection.indices.size
          ;[...selection.indices].sort((a, b) => b - a).forEach(onBrollRemove) // highest-first keeps indices valid
          toast(count > 1 ? `${count} b-rolls eliminados` : 'B-roll eliminado', { icon: '🗑️' })
          setSelection(null)
        } else if (selection.kind === 'caption') {
          [...selection.indices].sort((a, b) => b - a).forEach((i) => onDeleteCaptionWord?.(i))
          setSelection(null)
        }
        return
      }
      // Nudge selected b-roll(s) by ±0.1s.
      if (selection.kind === 'broll' && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) {
        e.preventDefault()
        const delta = e.key === 'ArrowRight' ? 0.1 : -0.1
        selection.indices.forEach((i) => {
          const b = brollPlacements[i]
          if (!b) return
          const dur = b.end - b.start
          const ns = clamp(b.start + delta, 0, clipDuration - dur)
          onBrollUpdate(i, { start: round2(ns), end: round2(ns + dur) })
        })
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [selection, onBrollRemove, onDeleteCaptionWord, brollPlacements, clipDuration, onBrollUpdate, disabled])

  // ── Derived: caption segments (merge nearby words into phrases) ──────────────
  const captionSegments = useMemo(() => mergeWords(words ?? []), [words])
  const hasCaptions = captionSegments.length > 0

  // Background pointer-down → scrub/pan (shared by ruler + track backgrounds).
  const scrubDown = (e: React.PointerEvent) => {
    if (disabled) return
    const el = viewportRef.current
    drag.begin({ kind: 'scrub', startClientX: e.clientX, startScroll: el?.scrollLeft ?? 0, moved: false }, e)
  }

  // Effective placement for a b-roll (drag preview overrides committed state).
  const effective = (i: number, b: BrollPlacement) =>
    dragPreview && dragPreview.index === i ? { start: dragPreview.start, end: dragPreview.end } : b

  // Open the right-click menu for a block, capturing its DOM node so a menu
  // item like "Editar" can anchor the inspector popover to it.
  const openCtx = (e: React.MouseEvent, m: CtxMenuInit) => {
    e.preventDefault()
    e.stopPropagation()
    setContextMenu({ ...m, x: e.clientX, y: e.clientY, el: e.currentTarget as HTMLElement } as CtxMenu)
  }

  const ctxMenuItems = (m: CtxMenu): MenuItem[] => {
    switch (m.kind) {
      case 'broll': {
        const b = brollPlacements[m.index]
        return [
          { label: 'Duplicar', icon: <Copy className="w-3.5 h-3.5" />, onClick: () => onBrollDuplicate?.(m.index) },
          {
            label: 'Mover al cursor', icon: <Crosshair className="w-3.5 h-3.5" />,
            onClick: () => {
              if (!b) return
              const dur = b.end - b.start
              const ns = clamp(playhead, 0, clipDuration - dur)
              onBrollUpdate(m.index, { start: round2(ns), end: round2(ns + dur) })
            },
          },
          { label: 'Opacidad 50%', onClick: () => onBrollUpdate(m.index, { opacity: 0.5 }) },
          { label: 'Opacidad 100%', onClick: () => onBrollUpdate(m.index, { opacity: 1 }) },
          {
            label: 'Eliminar', icon: <Trash2 className="w-3.5 h-3.5" />, danger: true, separated: true,
            onClick: () => { onBrollRemove(m.index); toast('B-roll eliminado', { icon: '🗑️' }); setSelection(null) },
          },
        ]
      }
      case 'caption':
        return [
          {
            label: 'Editar', icon: <Pencil className="w-3.5 h-3.5" />,
            onClick: () => { setSelection({ kind: 'caption', indices: new Set([m.wordIndex]) }); setAnchorEl(m.el) },
          },
          {
            label: 'Eliminar', icon: <Trash2 className="w-3.5 h-3.5" />, danger: true, separated: true,
            onClick: () => { onDeleteCaptionWord?.(m.wordIndex); setSelection(null) },
          },
        ]
      case 'title':
        return [
          {
            label: 'Editar texto', icon: <Pencil className="w-3.5 h-3.5" />,
            onClick: () => { setSelection({ kind: 'title' }); setAnchorEl(m.el); onTitleBlockClick?.() },
          },
        ]
      case 'video':
        return [
          { label: 'Transformar', icon: <Move className="w-3.5 h-3.5" />, onClick: () => onVideoTrackClick?.() },
          { label: 'Reiniciar transform', icon: <RotateCcw className="w-3.5 h-3.5" />, separated: true, onClick: () => onResetTransform?.() },
        ]
    }
  }

  return (
    <div className="flex flex-col h-full min-h-0 bg-slate-900 border-t border-slate-700/50 text-slate-200">
      {/* ── Toolbar ── */}
      <div className="flex items-center gap-2 px-3 py-1.5 border-b border-slate-700/50 bg-slate-800/60">
        <span className="text-xs font-mono text-white tabular-nums w-28">
          {formatDuration(playhead)} / {formatDuration(clipDuration)}
        </span>
        <button
          onClick={doSplit}
          className="flex items-center gap-1 px-2 py-1 rounded text-xs border border-slate-700 text-slate-300 hover:text-white hover:border-rose-500/60 focus-visible:ring-2 focus-visible:ring-brand-500"
          title="Cortar B-roll en el cursor (S · Ctrl/⌘+K)"
        >
          <Scissors className="w-3.5 h-3.5" /> Cortar
        </button>
        <div className="w-px h-5 bg-slate-700" />
        <button
          onClick={() => setTrimMode((v) => !v)}
          className={cn('flex items-center gap-1 px-2 py-1 rounded text-xs border focus-visible:ring-2 focus-visible:ring-brand-500',
            trimMode ? 'bg-brand-600 border-brand-500 text-white' : 'border-slate-700 text-slate-400 hover:text-white')}
          title="Modo recorte (T)"
        >
          <Crop className="w-3.5 h-3.5" /> Recortar
        </button>
        {trimMode && trimChanged && onApplyTrim && (
          <Button size="sm" onClick={onApplyTrim} loading={trimApplying} disabled={trimApplying}>
            <Check className="w-3.5 h-3.5" /> Aplicar
          </Button>
        )}
        <button
          onClick={() => setSnap((v) => !v)}
          className={cn('flex items-center gap-1 px-2 py-1 rounded text-xs border focus-visible:ring-2 focus-visible:ring-brand-500',
            snap ? 'bg-cyan-600/80 border-cyan-500 text-white' : 'border-slate-700 text-slate-400 hover:text-white')}
          title="Imán / snapping"
        >
          <Magnet className="w-3.5 h-3.5" /> Snap
        </button>
        <button
          onClick={() => setSnapWhole((v) => !v)}
          className={cn('flex items-center gap-1 px-2 py-1 rounded text-xs border focus-visible:ring-2 focus-visible:ring-brand-500',
            snapWhole ? 'bg-cyan-600/80 border-cyan-500 text-white' : 'border-slate-700 text-slate-400 hover:text-white')}
          title="Ajustar a segundos enteros"
        >
          <Clock className="w-3.5 h-3.5" /> 1s
        </button>

        {selection?.kind === 'broll' && selection.indices.size > 1 && (
          <>
            <div className="w-px h-5 bg-slate-700" />
            <span className="px-2 py-1 rounded text-xs bg-cyan-600/30 border border-cyan-500/50 text-cyan-200">
              {selection.indices.size} seleccionados
            </span>
            <button
              onClick={() => setSelection(null)}
              className="px-2 py-1 rounded text-xs border border-slate-700 text-slate-400 hover:text-white focus-visible:ring-2 focus-visible:ring-brand-500"
            >
              Deseleccionar todo
            </button>
          </>
        )}

        <div className="flex-1" />

        <button onClick={() => zoomBy(1 / 1.3)} className="p-1 rounded text-slate-400 hover:text-white hover:bg-slate-700" title="Alejar">
          <ZoomOut className="w-4 h-4" />
        </button>
        <input
          type="range" min={MIN_ZOOM} max={MAX_ZOOM} step={0.1} value={zoom}
          onChange={(e) => setZoom(Number(e.target.value))}
          className="w-28 accent-brand-500" title={`Zoom ${zoom.toFixed(1)}x`}
        />
        <button onClick={() => zoomBy(1.3)} className="p-1 rounded text-slate-400 hover:text-white hover:bg-slate-700" title="Acercar">
          <ZoomIn className="w-4 h-4" />
        </button>
        <button onClick={fitToScreen} className="p-1 rounded text-slate-400 hover:text-white hover:bg-slate-700" title="Ajustar a la pantalla">
          <Maximize2 className="w-4 h-4" />
        </button>
      </div>

      {/* ── Inspector popover (floating, anchored to the selected block) ── */}
      {selection && anchorEl && (selection.kind !== 'title' || addTitle) && (
        <TimelineInspector
          selection={selection}
          anchorEl={anchorEl}
          scrollEl={viewportRef.current}
          onClose={() => { setSelection(null); setAnchorEl(null) }}
          brollPlacements={brollPlacements}
          onBrollUpdate={onBrollUpdate}
          onBrollRemove={(i) => { onBrollRemove(i); setSelection(null); setAnchorEl(null) }}
          onBrollDuplicate={onBrollDuplicate}
          words={words ?? []}
          onUpdateCaptionWord={onUpdateCaptionWord}
          onDeleteCaptionWord={(i) => { onDeleteCaptionWord?.(i); setSelection(null); setAnchorEl(null) }}
          titleText={titleText ?? ''}
          setTitleText={setTitleText ?? (() => {})}
          titleColor={titleColor ?? '#FFFFFF'}
          setTitleColor={setTitleColor ?? (() => {})}
          titlePosition={titlePosition ?? 'top'}
          setTitlePosition={setTitlePosition ?? (() => {})}
          videoTransform={videoTransform}
          setVideoTransform={setVideoTransform}
          onEditInVideoTab={onVideoTrackClick}
          onResetTransform={onResetTransform}
        />
      )}

      {/* ── Right-click context menu ── */}
      {contextMenu && (
        <BlockContextMenu
          x={contextMenu.x} y={contextMenu.y}
          items={ctxMenuItems(contextMenu)}
          onClose={() => setContextMenu(null)}
        />
      )}

      {/* ── Scrollable track area ── */}
      <div ref={viewportRef} className="relative flex-1 min-h-0 overflow-x-auto overflow-y-auto select-none">
        <div style={{ width: LABEL_W + contentWidth, position: 'relative' }}>
          {/* Ruler row */}
          <div className="flex sticky top-0 z-30">
            <div className="sticky left-0 z-40 flex-shrink-0 bg-slate-800 border-r border-b border-slate-700/60"
              style={{ width: LABEL_W, height: RULER_H }} />
            <div onPointerDown={scrubDown} className="cursor-text">
              <TimelineRuler duration={clipDuration} pps={pps} height={RULER_H} />
            </div>
          </div>

          {/* Track: Main video */}
          <TimelineTrack
            label="Video" icon={<Film className="w-3.5 h-3.5" />} labelWidth={LABEL_W}
            contentWidth={contentWidth} height={TRACK_H} collapsible
            collapsed={collapsed.video} onToggleCollapse={() => setCollapsed((c) => ({ ...c, video: !c.video }))}
            onContentPointerDown={trimMode ? undefined : scrubDown}
          >
            {trimMode ? (
              <TrimOverlay
                contentWidth={contentWidth} winStart={winStart} winSpan={winSpan}
                pendingStart={pendingStart} pendingEnd={pendingEnd}
                onHandleDown={(edge, e) => drag.begin({ kind: 'trim', edge, startClientX: e.clientX }, e)}
              />
            ) : (
              <MainVideoBar
                contentWidth={contentWidth} pps={pps} clipDuration={clipDuration}
                trimStart={pendingStart - clipStart} trimEnd={pendingEnd - clipStart}
                onActivate={(e) => { setSelection({ kind: 'video' }); setAnchorEl(e.currentTarget as HTMLElement) }}
                onContextMenu={(e) => openCtx(e, { kind: 'video' })}
              />
            )}
          </TimelineTrack>

          {/* Track: B-rolls */}
          <TimelineTrack
            label="B-rolls" icon={<ImageIcon className="w-3.5 h-3.5" />} labelWidth={LABEL_W}
            contentWidth={contentWidth} height={TRACK_H} zebra collapsible
            collapsed={collapsed.broll} onToggleCollapse={() => setCollapsed((c) => ({ ...c, broll: !c.broll }))}
            onContentPointerDown={scrubDown}
            placeholder={brollPlacements.length === 0 ? 'Añade B-rolls desde el panel de sugerencias →' : undefined}
          >
            {brollPlacements.map((b, i) => {
              const eff = effective(i, b)
              const isSelected = selection?.kind === 'broll' && selection.indices.has(i)
              return (
                <TimelineBlock
                  key={`${b.url}-${i}`}
                  left={eff.start * pps}
                  width={(eff.end - eff.start) * pps}
                  selected={isSelected}
                  multiSelected={isSelected && selection?.kind === 'broll' && selection.indices.size > 1}
                  dragging={dragPreview?.index === i}
                  thumbnailUrl={b.url}
                  opacity={b.opacity}
                  colorClass="bg-emerald-600/40 border-emerald-500"
                  draggable={!disabled} resizable={!disabled}
                  title={`B-roll ${eff.start.toFixed(1)}s–${eff.end.toFixed(1)}s`}
                  onSelect={(e) => selectBroll(i, e)}
                  onMoveDown={(e) => drag.begin(
                    { kind: 'broll-move', index: i, startClientX: e.clientX, origStart: b.start, origEnd: b.end }, e)}
                  onResizeDown={(edge, e) => drag.begin(
                    { kind: 'broll-resize', index: i, edge, startClientX: e.clientX, origStart: b.start, origEnd: b.end }, e)}
                  onContextMenu={(e) => openCtx(e, { kind: 'broll', index: i })}
                />
              )
            })}
          </TimelineTrack>

          {/* Track: Captions (hidden when there are none) */}
          {hasCaptions && (
            <TimelineTrack
              label="Subtítulos" icon={<Captions className="w-3.5 h-3.5" />} labelWidth={LABEL_W}
              contentWidth={contentWidth} height={36} collapsible
              collapsed={collapsed.caption} onToggleCollapse={() => setCollapsed((c) => ({ ...c, caption: !c.caption }))}
              onContentPointerDown={scrubDown}
            >
              {captionSegments.map((seg, i) => {
                const isSel = selection?.kind === 'caption' && selection.indices.has(seg.wordIndex)
                const speaker = speakerForClipTime?.(seg.start) ?? null
                return (
                  <div
                    key={i}
                    className={cn(
                      'absolute top-1 bottom-1 rounded border overflow-hidden cursor-pointer',
                      isSel ? 'bg-amber-500/50 border-amber-300 ring-2 ring-amber-400' : 'bg-amber-600/30 border-amber-500/50',
                    )}
                    style={{ left: seg.start * pps, width: Math.max(3, (seg.end - seg.start) * pps) }}
                    title={speaker ? `${speaker}: ${seg.text}` : seg.text}
                    onPointerDown={(e) => {
                      e.stopPropagation()
                      selectCaption(seg.wordIndex, e)
                      onCaptionBlockClick?.()
                    }}
                    onContextMenu={(e) => openCtx(e, { kind: 'caption', wordIndex: seg.wordIndex })}
                  >
                    {speaker && (
                      <span
                        className="absolute top-0 left-0 z-10 px-1 text-[8px] font-bold leading-tight rounded-br pointer-events-none"
                        style={{ background: speakerColor(speaker), color: '#0f172a' }}
                      >
                        {speakerLabel(speaker)}
                      </span>
                    )}
                    <span className={cn(
                      'block px-1 text-[9px] text-amber-100/90 truncate pointer-events-none leading-[26px]',
                      speaker && 'pl-6',
                    )}>
                      {seg.text}
                    </span>
                  </div>
                )
              })}
            </TimelineTrack>
          )}

          {/* Track: Title (only when enabled) */}
          {addTitle && (
            <TimelineTrack
              label="Título" icon={<Heading1 className="w-3.5 h-3.5" />} labelWidth={LABEL_W}
              contentWidth={contentWidth} height={36} zebra collapsible
              collapsed={collapsed.title} onToggleCollapse={() => setCollapsed((c) => ({ ...c, title: !c.title }))}
              onContentPointerDown={scrubDown}
            >
              <div
                className={cn(
                  'absolute top-1 bottom-1 rounded border overflow-hidden cursor-pointer',
                  selection?.kind === 'title' ? 'bg-violet-500/50 border-violet-300 ring-2 ring-violet-400' : 'bg-violet-600/30 border-violet-500/50',
                )}
                style={{ left: 0, width: Math.max(20, Math.min(3, clipDuration) * pps) }}
                title={titleText ?? 'Título'}
                onPointerDown={(e) => { e.stopPropagation(); setSelection({ kind: 'title' }); setAnchorEl(e.currentTarget as HTMLElement); onTitleBlockClick?.() }}
                onContextMenu={(e) => openCtx(e, { kind: 'title' })}
              >
                <span className="block px-1.5 text-[10px] text-violet-100/90 truncate pointer-events-none leading-[26px]">
                  {titleText || 'Título'}
                </span>
              </div>
            </TimelineTrack>
          )}

          {/* Scrub cursor — a cyan guide that tracks the pointer while panning */}
          {scrubCursor != null && (
            <div className="absolute top-0 bottom-0 w-px bg-cyan-300/60 z-30 pointer-events-none"
              style={{ left: LABEL_W + scrubCursor * pps }} />
          )}

          {/* Snap indicator */}
          {snapLine != null && (
            <div className="absolute top-0 bottom-0 w-px bg-cyan-400 z-30 pointer-events-none"
              style={{ left: LABEL_W + snapLine * pps, borderLeft: '1px dashed rgb(34 211 238)' }} />
          )}

          {/* Playhead (hidden in trim mode — the axis there is the trim window) */}
          {!trimMode && (
            <TimelinePlayhead
              time={playhead} pps={pps} contentLeft={LABEL_W} top={RULER_H}
              onHandleDown={(e) => drag.begin({ kind: 'playhead' }, e)}
            />
          )}
        </div>
      </div>
    </div>
  )
})

