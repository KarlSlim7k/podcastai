import { useCallback, useEffect, useRef, useState } from 'react'

interface UseResizablePanelOptions {
  /** Starting size in px. */
  initialSize: number
  /** Minimum size in px. */
  min: number
  /**
   * Maximum size in px, or a function returning it (re-evaluated on every
   * move + on window resize) so values like "50vh" track the viewport.
   */
  max: number | (() => number)
  /**
   * When true (default), dragging the handle *up* grows the panel — the right
   * behaviour for a panel pinned to the bottom of the screen (the timeline).
   */
  growUp?: boolean
}

interface ResizablePanel {
  size: number
  setSize: (n: number) => void
  dragging: boolean
  /** Spread onto the drag-handle element. */
  handleProps: { onPointerDown: (e: React.PointerEvent) => void }
}

const resolveMax = (max: number | (() => number)) => (typeof max === 'function' ? max() : max)
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))

/**
 * Pointer-driven resize for a single edge. Used for the divider between the
 * preview workspace and the bottom timeline. Listeners are attached on the
 * window for the duration of the gesture (so the drag keeps working if the
 * cursor leaves the thin handle) and torn down on pointer-up / unmount.
 */
export function useResizablePanel({
  initialSize, min, max, growUp = true,
}: UseResizablePanelOptions): ResizablePanel {
  const [size, setSizeRaw] = useState(() => clamp(initialSize, min, resolveMax(max)))
  const [dragging, setDragging] = useState(false)
  const cleanupRef = useRef<(() => void) | null>(null)

  const setSize = useCallback((n: number) => {
    setSizeRaw(clamp(n, min, resolveMax(max)))
  }, [min, max])

  // Re-clamp when the viewport shrinks (max may depend on innerHeight).
  useEffect(() => {
    const onResize = () => setSizeRaw((s) => clamp(s, min, resolveMax(max)))
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [min, max])

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    e.preventDefault()
    const startY = e.clientY
    const startSize = size
    setDragging(true)

    const move = (ev: PointerEvent) => {
      const delta = growUp ? startY - ev.clientY : ev.clientY - startY
      setSizeRaw(clamp(startSize + delta, min, resolveMax(max)))
    }
    const up = () => {
      setDragging(false)
      cleanupRef.current?.()
      cleanupRef.current = null
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
    window.addEventListener('pointercancel', up)
    cleanupRef.current = () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      window.removeEventListener('pointercancel', up)
    }
  }, [size, min, max, growUp])

  useEffect(() => () => { cleanupRef.current?.() }, [])

  return { size, setSize, dragging, handleProps: { onPointerDown } }
}
