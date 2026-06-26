import { useEffect, useState } from 'react'
import { Check, Loader2 } from 'lucide-react'

function ago(ms: number): string {
  const s = Math.floor((Date.now() - ms) / 1000)
  if (s < 5) return 'justo ahora'
  if (s < 60) return `hace ${s}s`
  const m = Math.floor(s / 60)
  if (m < 60) return `hace ${m} min`
  const h = Math.floor(m / 60)
  return `hace ${h} h`
}

/**
 * Header autosave status: idle (nothing yet) · "Guardando…" while a write is
 * pending · "Guardado hace Xs" once persisted. Re-renders on a slow interval so
 * the relative time stays fresh without a per-second tick.
 */
export function SaveIndicator({ lastSavedAt, saving }: { lastSavedAt: number | null; saving: boolean }) {
  const [, force] = useState(0)
  useEffect(() => {
    if (saving || lastSavedAt == null) return
    const id = setInterval(() => force((n) => n + 1), 10_000)
    return () => clearInterval(id)
  }, [saving, lastSavedAt])

  if (saving) {
    return (
      <span className="flex items-center gap-1 text-xs text-slate-400" aria-live="polite">
        <Loader2 className="w-3 h-3 animate-spin" /> Guardando…
      </span>
    )
  }
  if (lastSavedAt != null) {
    return (
      <span
        className="flex items-center gap-1 text-xs text-slate-500"
        title={new Date(lastSavedAt).toLocaleString('es-ES')}
        aria-live="polite"
      >
        <Check className="w-3 h-3 text-emerald-400" /> Guardado {ago(lastSavedAt)}
      </span>
    )
  }
  return null
}
