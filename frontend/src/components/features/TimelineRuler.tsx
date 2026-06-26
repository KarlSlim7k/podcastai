import { useMemo } from 'react'

interface TimelineRulerProps {
  /** Total clip duration in seconds. */
  duration: number
  /** Pixels per second at the current zoom. */
  pps: number
  /** Ruler height in px. */
  height?: number
}

const NICE_STEPS = [0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600]
const MIN_LABEL_PX = 60

/** Time ruler with adaptive tick spacing — labels stay ~60px apart at any zoom. */
export function TimelineRuler({ duration, pps, height = 28 }: TimelineRulerProps) {
  const { major, minorPx } = useMemo(() => {
    const rawInterval = MIN_LABEL_PX / pps
    const step = NICE_STEPS.find((s) => s >= rawInterval) ?? NICE_STEPS[NICE_STEPS.length - 1]
    const ticks: number[] = []
    for (let t = 0; t <= duration + 1e-6; t += step) ticks.push(Math.round(t * 1000) / 1000)
    return { major: ticks, minorPx: (step / 5) * pps }
  }, [duration, pps])

  return (
    <div
      className="relative bg-slate-800 border-b border-slate-700/60 select-none"
      style={{ height, width: duration * pps }}
    >
      {major.map((t, i) => {
        const left = t * pps
        return (
          <div key={i} className="absolute top-0 bottom-0" style={{ left }}>
            {/* major tick */}
            <div className="absolute bottom-0 w-px h-2.5 bg-slate-500" />
            <span className="absolute top-1 left-1 text-[10px] font-mono text-slate-400 whitespace-nowrap">
              {formatTick(t)}
            </span>
            {/* 4 minor ticks between this major and the next */}
            {minorPx > 6 &&
              [1, 2, 3, 4].map((m) => (
                <div
                  key={m}
                  className="absolute bottom-0 w-px h-1.5 bg-slate-600/70"
                  style={{ left: m * minorPx }}
                />
              ))}
          </div>
        )
      })}
    </div>
  )
}

function formatTick(seconds: number): string {
  if (seconds < 60) {
    // Show one decimal only when we're zoomed into sub-second territory.
    return Number.isInteger(seconds) ? `${seconds}s` : `${seconds.toFixed(1)}s`
  }
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}
