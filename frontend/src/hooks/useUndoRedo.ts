import { useCallback, useEffect, useRef, useState } from 'react'

interface UseUndoRedoOptions {
  capacity?: number
  /** Collapse a burst of rapid changes (e.g. a slider drag) into one entry. */
  debounceMs?: number
  enabled?: boolean
}

interface UndoRedo {
  undo: () => void
  redo: () => void
  canUndo: boolean
  canRedo: boolean
  /** Drop all history (e.g. after loading a preset or restoring a draft). */
  reset: () => void
}

/**
 * Snapshot-based undo/redo over an externally-owned state value.
 *
 * The caller passes the current `present` (a memoised snapshot of all tracked
 * fields) and an `apply` callback that writes a snapshot back into the
 * individual state setters. Changes are recorded debounced so a continuous
 * slider/drag becomes a single history entry, not hundreds.
 */
export function useUndoRedo<T>(
  present: T,
  apply: (snapshot: T) => void,
  { capacity = 50, debounceMs = 400, enabled = true }: UseUndoRedoOptions = {},
): UndoRedo {
  const past = useRef<T[]>([])
  const future = useRef<T[]>([])
  const presentRef = useRef(present)
  const skipRef = useRef(false)        // set while applying undo/redo
  const applyRef = useRef(apply)
  applyRef.current = apply
  const [, bump] = useState(0)
  const rerender = () => bump((n) => n + 1)

  useEffect(() => {
    if (!enabled) return
    if (skipRef.current) { skipRef.current = false; presentRef.current = present; return }
    const timer = setTimeout(() => {
      past.current.push(presentRef.current)
      if (past.current.length > capacity) past.current.shift()
      future.current = []
      presentRef.current = present
      rerender()
    }, debounceMs)
    return () => clearTimeout(timer)
  }, [present, capacity, debounceMs, enabled])

  const undo = useCallback(() => {
    if (!past.current.length) return
    const prev = past.current.pop()!
    future.current.push(presentRef.current)
    skipRef.current = true
    presentRef.current = prev
    applyRef.current(prev)
    rerender()
  }, [])

  const redo = useCallback(() => {
    if (!future.current.length) return
    const next = future.current.pop()!
    past.current.push(presentRef.current)
    skipRef.current = true
    presentRef.current = next
    applyRef.current(next)
    rerender()
  }, [])

  const reset = useCallback(() => {
    past.current = []
    future.current = []
    presentRef.current = present
    rerender()
  }, [present])

  return { undo, redo, canUndo: past.current.length > 0, canRedo: future.current.length > 0, reset }
}
