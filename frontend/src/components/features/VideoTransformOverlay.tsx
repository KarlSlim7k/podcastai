import { useEffect, useRef, useState } from 'react'
import { RotateCw } from 'lucide-react'
import type { VideoTransform } from '../../types'

interface Props {
  transform: VideoTransform
  onChange: (t: VideoTransform) => void
  /** Called once when a drag gesture ends — a good undo/commit boundary. */
  onCommit?: () => void
}

type Mode =
  | { kind: 'move'; sx: number; sy: number; t: VideoTransform }
  | { kind: 'scale'; cx: number; cy: number; startDist: number; t: VideoTransform }
  | { kind: 'rotate'; cx: number; cy: number; startAngle: number; t: VideoTransform }

const SNAP_PX = 10
const FRAME_W = 1080
const FRAME_H = 1920
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))
const round = (n: number) => Math.round(n)

/**
 * CapCut-style bounding box over the preview for moving/scaling/rotating the
 * main video. Works in screen space and converts back to render-space px
 * (1080x1920, offset from frame centre) which is what the backend expects.
 */
export function VideoTransformOverlay({ transform, onChange, onCommit }: Props) {
  const rootRef = useRef<HTMLDivElement>(null)
  const modeRef = useRef<Mode | null>(null)
  const [snap, setSnap] = useState<{ x: boolean; y: boolean }>({ x: false, y: false })
  // Track the on-screen width so render-space px map correctly (and react to resize).
  const [boxW, setBoxW] = useState(0)
  useEffect(() => {
    const el = rootRef.current
    if (!el) return
    const ro = new ResizeObserver((entries) => setBoxW(entries[0].contentRect.width))
    ro.observe(el)
    setBoxW(el.getBoundingClientRect().width)
    return () => ro.disconnect()
  }, [])
  const screenPerRender = boxW ? boxW / FRAME_W : 1

  // Screen px per render px (the overlay covers the full 9:16 frame area).
  const pxScale = () => (rootRef.current ? rootRef.current.getBoundingClientRect().width / FRAME_W : 1)
  const center = () => {
    const r = rootRef.current!.getBoundingClientRect()
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 }
  }

  const begin = (mode: Mode) => (e: React.PointerEvent) => {
    e.preventDefault(); e.stopPropagation()
    modeRef.current = mode
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }

  const move = (e: PointerEvent) => {
    const m = modeRef.current
    if (!m) return
    if (m.kind === 'move') {
      const s = pxScale()
      let nx = m.t.x + (e.clientX - m.sx) / s
      let ny = m.t.y + (e.clientY - m.sy) / s
      const snapX = Math.abs(nx) < SNAP_PX / s
      const snapY = Math.abs(ny) < SNAP_PX / s
      if (snapX) nx = 0
      if (snapY) ny = 0
      setSnap({ x: snapX, y: snapY })
      onChange({ ...m.t, x: round(nx), y: round(ny) })
    } else if (m.kind === 'scale') {
      const dist = Math.hypot(e.clientX - m.cx, e.clientY - m.cy)
      const ratio = dist / Math.max(1, m.startDist)
      onChange({ ...m.t, scale: clamp(round(m.t.scale * ratio), 10, 400) })
    } else {
      const angle = Math.atan2(e.clientY - m.cy, e.clientX - m.cx)
      let deg = m.t.rotation + (angle - m.startAngle) * (180 / Math.PI)
      // snap to 0 / ±90 / 180
      for (const target of [-180, -90, 0, 90, 180]) {
        if (Math.abs(deg - target) < 5) deg = target
      }
      onChange({ ...m.t, rotation: clamp(round(deg), -180, 180) })
    }
  }

  const up = () => {
    modeRef.current = null
    setSnap({ x: false, y: false })
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', up)
    onCommit?.()
  }

  const onCornerDown = (e: React.PointerEvent) => {
    const c = center()
    begin({ kind: 'scale', cx: c.x, cy: c.y, startDist: Math.hypot(e.clientX - c.x, e.clientY - c.y), t: transform })(e)
  }
  const onRotateDown = (e: React.PointerEvent) => {
    const c = center()
    begin({ kind: 'rotate', cx: c.x, cy: c.y, startAngle: Math.atan2(e.clientY - c.y, e.clientX - c.x), t: transform })(e)
  }
  const onBodyDown = (e: React.PointerEvent) =>
    begin({ kind: 'move', sx: e.clientX, sy: e.clientY, t: transform })(e)

  const s = transform.scale / 100

  return (
    <div ref={rootRef} className="absolute inset-0 z-30">
      {/* snap guide lines */}
      {snap.x && <div className="absolute left-1/2 top-0 bottom-0 w-px bg-cyan-400 -translate-x-1/2 pointer-events-none" />}
      {snap.y && <div className="absolute top-1/2 left-0 right-0 h-px bg-cyan-400 -translate-y-1/2 pointer-events-none" />}

      {/* bounding box */}
      <div
        className="absolute touch-none"
        style={{
          left: '50%', top: '50%', width: '100%', height: '100%',
          transform: `translate(-50%, -50%) translate(${transform.x * screenPerRender}px, ${transform.y * screenPerRender}px) rotate(${transform.rotation}deg) scale(${s})`,
          transformOrigin: 'center',
        }}
      >
        <div onPointerDown={onBodyDown} className="absolute inset-0 cursor-move border-2 border-brand-400/90 bg-brand-400/5" />
        {/* corner scale handles */}
        {([['left-0 top-0', 'nwse-resize'], ['right-0 top-0', 'nesw-resize'], ['left-0 bottom-0', 'nesw-resize'], ['right-0 bottom-0', 'nwse-resize']] as const).map(([pos, cursor]) => (
          <div key={pos} onPointerDown={onCornerDown}
            className={`absolute ${pos} w-3 h-3 -m-1.5 bg-white border border-brand-500 rounded-sm touch-none`}
            style={{ cursor }} />
        ))}
        {/* rotation handle */}
        <div className="absolute left-1/2 -top-7 -translate-x-1/2 flex flex-col items-center">
          <div onPointerDown={onRotateDown}
            className="w-5 h-5 rounded-full bg-white border border-brand-500 flex items-center justify-center cursor-grab touch-none">
            <RotateCw className="w-3 h-3 text-brand-600" />
          </div>
          <div className="w-px h-2 bg-brand-400/90" />
        </div>
      </div>
    </div>
  )
}
