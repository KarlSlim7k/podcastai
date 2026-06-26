import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Low-level pointer-drag primitive for the timeline. It is intentionally
 * generic: callers pass an arbitrary "context" object at pointer-down time
 * (which block, the original placement, the start clientX, …) and the hook
 * threads that same context through every move/end callback.
 *
 * Why a context object instead of closures? During a drag we add the
 * move/up listeners on `window` once and keep them for the whole gesture.
 * Keeping the per-gesture data in a ref (not in the listener closure) means
 * we never tear down/recreate listeners mid-drag, and the callbacks always
 * see fresh values.
 *
 * Uses pointer events (not mouse events) for touch/pen support.
 */
export interface TimelineDragCallbacks<Ctx> {
  onStart?: (ctx: Ctx, e: PointerEvent) => void
  onMove: (ctx: Ctx, e: PointerEvent) => void
  onEnd?: (ctx: Ctx, e: PointerEvent) => void
}

export interface TimelineDragController<Ctx> {
  /** Call from an element's onPointerDown to begin a drag with the given context. */
  begin: (ctx: Ctx, e: React.PointerEvent) => void
  /** True while a gesture is in progress. */
  dragging: boolean
}

export function useTimelineDrag<Ctx>(
  callbacks: TimelineDragCallbacks<Ctx>,
): TimelineDragController<Ctx> {
  const [dragging, setDragging] = useState(false)

  // Keep callbacks + active context in refs so the window listeners added in
  // `begin` always see the latest values without being recreated.
  const cbRef = useRef(callbacks)
  cbRef.current = callbacks
  const ctxRef = useRef<Ctx | null>(null)
  const cleanupRef = useRef<(() => void) | null>(null)

  const begin = useCallback((ctx: Ctx, e: React.PointerEvent) => {
    e.preventDefault()
    e.stopPropagation()
    ctxRef.current = ctx
    setDragging(true)
    cbRef.current.onStart?.(ctx, e.nativeEvent)

    const move = (ev: PointerEvent) => {
      if (ctxRef.current === null) return
      cbRef.current.onMove(ctxRef.current, ev)
    }
    const up = (ev: PointerEvent) => {
      if (ctxRef.current !== null) {
        cbRef.current.onEnd?.(ctxRef.current, ev)
      }
      ctxRef.current = null
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
  }, [])

  // Safety net: drop any dangling listeners if the component unmounts mid-drag.
  useEffect(() => () => { cleanupRef.current?.() }, [])

  return { begin, dragging }
}
