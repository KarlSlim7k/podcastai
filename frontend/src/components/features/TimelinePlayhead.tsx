interface TimelinePlayheadProps {
  /** Current time in seconds (clip-relative). */
  time: number
  /** Pixels per second at the current zoom. */
  pps: number
  /** Left offset of the content area (label-column width). */
  contentLeft: number
  /** Top offset so the line starts below the ruler. */
  top: number
  /** Pointer-down on the triangle handle — begins a playhead drag. */
  onHandleDown: (e: React.PointerEvent) => void
}

// CapCut-style amber playhead. Bigger handle + glow so it reads as the
// "where am I" marker, visually distinct from the cyan scrub cursor.
const AMBER = 'rgb(251 191 36)' // amber-400
const GLOW = '0 0 6px rgba(251, 191, 36, 0.6)'

/** Amber vertical playhead with a draggable triangle handle at the top. */
export function TimelinePlayhead({ time, pps, contentLeft, top, onHandleDown }: TimelinePlayheadProps) {
  const left = contentLeft + time * pps
  return (
    <div className="absolute bottom-0 z-30 pointer-events-none" style={{ left, top: 0 }}>
      {/* A wide "head" bar in the ruler makes the playhead easy to spot and grab. */}
      <div
        onPointerDown={onHandleDown}
        className="absolute -translate-x-1/2 rounded-sm cursor-ew-resize pointer-events-auto touch-none"
        style={{
          top: Math.max(0, top - 12),
          width: 20,
          height: 8,
          background: AMBER,
          boxShadow: GLOW,
        }}
        title="Arrastra para mover el cursor"
      />
      {/* Triangle handle — sits in the ruler, the larger interactive target */}
      <div
        onPointerDown={onHandleDown}
        className="absolute -translate-x-1/2 w-0 h-0 cursor-ew-resize pointer-events-auto touch-none"
        style={{
          top: Math.max(0, top - 4),
          borderLeft: '10px solid transparent',
          borderRight: '10px solid transparent',
          borderTop: `12px solid ${AMBER}`,
          filter: 'drop-shadow(0 0 4px rgba(251, 191, 36, 0.6))',
        }}
        title="Arrastra para mover el cursor"
      />
      {/* The line itself */}
      <div
        className="absolute bottom-0 -translate-x-1/2 w-0.5"
        style={{ top, background: AMBER, boxShadow: GLOW }}
      />
    </div>
  )
}
