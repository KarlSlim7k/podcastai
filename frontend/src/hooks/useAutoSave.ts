import { useCallback, useEffect, useRef, useState } from 'react'

interface SavedDraft<T> {
  savedAt: number
  data: T
}

interface UseAutoSave<T> {
  /** A previous-session draft found in localStorage on mount, or null. */
  available: SavedDraft<T> | null
  /** Forget the offered draft without deleting the live autosave. */
  dismiss: () => void
  /** Delete the stored draft entirely. */
  clear: () => void
  /** Force an immediate write. */
  saveNow: () => void
  /** Timestamp (ms) of the last successful write this session, or null. */
  lastSavedAt: number | null
  /** True while a debounced write is pending (drives the "Guardando…" state). */
  saving: boolean
}

/**
 * Persists `value` to localStorage so a refresh doesn't lose work. It writes a
 * short debounce after every change (so the header indicator can show
 * "Guardando…" → "Guardado") and once more on `beforeunload`. On mount it reads
 * any existing draft and exposes it as `available` (independent of the live
 * autosave) so the caller can offer to restore it.
 */
export function useAutoSave<T>(
  key: string,
  value: T,
  { debounceMs = 1_000, enabled = true }: { debounceMs?: number; enabled?: boolean } = {},
): UseAutoSave<T> {
  const valueRef = useRef(value)
  valueRef.current = value

  const [available, setAvailable] = useState<SavedDraft<T> | null>(() => {
    try {
      const raw = localStorage.getItem(key)
      return raw ? (JSON.parse(raw) as SavedDraft<T>) : null
    } catch {
      return null
    }
  })

  const [lastSavedAt, setLastSavedAt] = useState<number | null>(null)
  const [saving, setSaving] = useState(false)

  const write = useCallback(() => {
    try {
      const at = Date.now()
      localStorage.setItem(key, JSON.stringify({ savedAt: at, data: valueRef.current }))
      setLastSavedAt(at)
    } catch {
      /* quota or serialization error — best-effort only */
    } finally {
      setSaving(false)
    }
  }, [key])

  // Debounced write on every value change. The first run (mount) is skipped so
  // simply opening the editor doesn't flash "Guardando…".
  const mountedRef = useRef(false)
  useEffect(() => {
    if (!enabled) return
    if (!mountedRef.current) { mountedRef.current = true; return }
    setSaving(true)
    const id = setTimeout(write, debounceMs)
    return () => clearTimeout(id)
  }, [value, write, debounceMs, enabled])

  // Flush the latest value if the tab is closing mid-debounce.
  useEffect(() => {
    if (!enabled) return
    const onUnload = () => write()
    window.addEventListener('beforeunload', onUnload)
    return () => window.removeEventListener('beforeunload', onUnload)
  }, [write, enabled])

  const dismiss = useCallback(() => setAvailable(null), [])
  const clear = useCallback(() => {
    try { localStorage.removeItem(key) } catch { /* ignore */ }
    setAvailable(null)
    setLastSavedAt(null)
    setSaving(false)
  }, [key])

  return { available, dismiss, clear, saveNow: write, lastSavedAt, saving }
}
