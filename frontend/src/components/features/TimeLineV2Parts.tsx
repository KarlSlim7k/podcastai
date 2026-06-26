import type React from 'react'
import { formatDuration } from '../../utils'
import type { CaptionWord } from '../../types'

/**
 * Presentational/pure pieces split out of TimeLineV2.tsx to keep that file
 * focused on drag/selection orchestration.
 */

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))

export function MainVideoBar({
  contentWidth, pps, clipDuration, trimStart, trimEnd, onActivate, onContextMenu,
}: {
  contentWidth: number; pps: number; clipDuration: number; trimStart: number; trimEnd: number
  onActivate?: (e: React.PointerEvent) => void
  onContextMenu?: (e: React.MouseEvent) => void
}) {
  const ts = clamp(trimStart, 0, clipDuration)
  const te = clamp(trimEnd, 0, clipDuration)
  return (
    <div
      className="absolute top-1 bottom-1 left-0 rounded-md bg-brand-600/20 border border-brand-500/60 overflow-hidden cursor-pointer"
      style={{ width: contentWidth }}
      onPointerDown={(e) => onActivate?.(e)}
      onContextMenu={onContextMenu}
    >
      {/* trimmed (kept) region */}
      <div className="absolute top-0 bottom-0 bg-brand-600/40"
        style={{ left: ts * pps, width: Math.max(0, (te - ts) * pps) }} />
      <span className="absolute left-2 top-1 text-[10px] text-brand-100/80 pointer-events-none">Clip</span>
    </div>
  )
}

export function TrimOverlay({
  contentWidth, winStart, winSpan, pendingStart, pendingEnd, onHandleDown,
}: {
  contentWidth: number; winStart: number; winSpan: number
  pendingStart: number; pendingEnd: number
  onHandleDown: (edge: 'start' | 'end', e: React.PointerEvent) => void
}) {
  const pct = (t: number) => clamp((t - winStart) / winSpan, 0, 1) * contentWidth
  const left = pct(pendingStart)
  const right = pct(pendingEnd)
  return (
    <div className="absolute top-1 bottom-1 left-0 bg-slate-800/60 rounded-md border border-slate-700/50"
      style={{ width: contentWidth }}>
      <div className="absolute top-0 bottom-0 bg-brand-600/40 border-y-2 border-brand-500"
        style={{ left, width: Math.max(0, right - left) }} />
      <div onPointerDown={(e) => onHandleDown('start', e)}
        className="absolute top-0 bottom-0 w-3 -ml-1.5 rounded bg-brand-400 border border-brand-200 cursor-ew-resize touch-none z-10"
        style={{ left }} title={`Inicio: ${formatDuration(pendingStart)}`} />
      <div onPointerDown={(e) => onHandleDown('end', e)}
        className="absolute top-0 bottom-0 w-3 -ml-1.5 rounded bg-brand-400 border border-brand-200 cursor-ew-resize touch-none z-10"
        style={{ left: right }} title={`Fin: ${formatDuration(pendingEnd)}`} />
    </div>
  )
}

export interface MergedSeg { start: number; end: number; text: string; wordIndex: number }

/** Merge nearby words into readable phrases for the captions track. */
export function mergeWords(words: CaptionWord[]): MergedSeg[] {
  if (words.length === 0) return []
  const out: MergedSeg[] = []
  let cur: MergedSeg = { start: words[0].start, end: words[0].end, text: words[0].word, wordIndex: 0 }
  for (let i = 1; i < words.length; i++) {
    const w = words[i]
    if (w.start - cur.end < 0.4 && w.end - cur.start < 6) {
      cur.end = w.end
      cur.text += ' ' + w.word
    } else {
      out.push(cur)
      cur = { start: w.start, end: w.end, text: w.word, wordIndex: i }
    }
  }
  out.push(cur)
  return out
}
