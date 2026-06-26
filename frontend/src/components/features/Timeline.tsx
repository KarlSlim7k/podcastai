import { useEffect, useRef, useState } from 'react'
import { formatDuration } from '../../utils'
import { cn } from '../../utils'

type DragHandle = 'start' | 'end' | null

interface TimelineProps {
  /** Visible window, absolute seconds (left/right edges of the track). */
  windowStart: number
  windowEnd: number
  /** Current selection, absolute seconds. */
  start: number
  end: number
  onChange: (start: number, end: number) => void
  disabled?: boolean
  minDuration?: number
  maxDuration?: number
}

/** Dual-handle range scrubber for trimming a clip's [start, end]. */
export function Timeline({
  windowStart, windowEnd, start, end, onChange,
  disabled = false, minDuration = 3, maxDuration = 180,
}: TimelineProps) {
  const trackRef = useRef<HTMLDivElement>(null)
  const [dragging, setDragging] = useState<DragHandle>(null)

  // Refs so the pointermove listener always sees the latest values without
  // having to tear down/recreate the listener on every drag-driven re-render.
  const liveRef = useRef({ start, end })
  liveRef.current = { start, end }
  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange

  const windowSpan = Math.max(0.001, windowEnd - windowStart)
  const pctOf = (t: number) => Math.min(100, Math.max(0, ((t - windowStart) / windowSpan) * 100))

  useEffect(() => {
    if (!dragging) return
    const track = trackRef.current
    if (!track) return

    const move = (e: PointerEvent) => {
      const rect = track.getBoundingClientRect()
      const pct = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width))
      const t = windowStart + pct * windowSpan
      const { start: s, end: en } = liveRef.current
      if (dragging === 'start') {
        const newStart = Math.max(windowStart, Math.min(t, en - minDuration))
        onChangeRef.current(round2(newStart), en)
      } else {
        const newEndRaw = Math.max(t, s + minDuration)
        const newEnd = Math.min(windowEnd, newEndRaw, s + maxDuration)
        onChangeRef.current(s, round2(newEnd))
      }
    }
    const up = () => setDragging(null)
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
    return () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
    }
  }, [dragging, windowStart, windowEnd, windowSpan, minDuration, maxDuration])

  const startPct = pctOf(start)
  const endPct = pctOf(end)

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-[10px] text-slate-500 font-mono">
        <span>{formatDuration(windowStart)}</span>
        <span className="text-slate-300">
          {formatDuration(start)} → {formatDuration(end)} · {(end - start).toFixed(1)}s
        </span>
        <span>{formatDuration(windowEnd)}</span>
      </div>
      <div
        ref={trackRef}
        className="relative h-8 bg-slate-800 rounded-lg border border-slate-700/50 select-none touch-none"
      >
        {/* Selected range */}
        <div
          className="absolute top-0 bottom-0 bg-brand-600/40 border-y-2 border-brand-500"
          style={{ left: `${startPct}%`, width: `${Math.max(0, endPct - startPct)}%` }}
        />
        {/* Start handle */}
        <div
          onPointerDown={(e) => { if (!disabled) { e.preventDefault(); setDragging('start') } }}
          className={cn(
            'absolute top-0 bottom-0 w-3 -ml-1.5 rounded bg-brand-400 border border-brand-200 cursor-ew-resize touch-none',
            disabled && 'opacity-50 cursor-not-allowed',
          )}
          style={{ left: `${startPct}%` }}
          title={`Inicio: ${formatDuration(start)}`}
        />
        {/* End handle */}
        <div
          onPointerDown={(e) => { if (!disabled) { e.preventDefault(); setDragging('end') } }}
          className={cn(
            'absolute top-0 bottom-0 w-3 -ml-1.5 rounded bg-brand-400 border border-brand-200 cursor-ew-resize touch-none',
            disabled && 'opacity-50 cursor-not-allowed',
          )}
          style={{ left: `${endPct}%` }}
          title={`Fin: ${formatDuration(end)}`}
        />
      </div>
    </div>
  )
}

function round2(n: number) {
  return Math.round(n * 100) / 100
}
