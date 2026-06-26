import { useEffect, useState } from 'react'
import { Save, RotateCcw, Loader2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { useClipCaptions, useSaveClipCaptions, useResetClipCaptions } from '../../hooks/useProject'
import { Button } from '../ui/Button'
import { Timeline } from './Timeline'
import { cn } from '../../utils'
import type { CaptionWord } from '../../types'

interface CaptionEditorProps {
  projectId: number
  clipId: number
  clipDuration: number
  /** Called after a successful save/reset, so the caller can clear a stale preview. */
  onChanged?: () => void
}

/** Per-word caption editor: edit text inline, retime the selected word on a mini timeline. */
export function CaptionEditor({ projectId, clipId, clipDuration, onChanged }: CaptionEditorProps) {
  const captionsQuery = useClipCaptions(projectId, clipId)
  const saveCaptions = useSaveClipCaptions(projectId)
  const resetCaptions = useResetClipCaptions(projectId)

  const [words, setWords] = useState<CaptionWord[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [dirty, setDirty] = useState(false)
  const [shiftMs, setShiftMs] = useState(0)

  // Seed local state from the fetched (auto or custom) words, but don't
  // clobber in-progress edits if the query refetches in the background.
  useEffect(() => {
    if (captionsQuery.data && !dirty) {
      setWords(captionsQuery.data.words)
    }
  }, [captionsQuery.data, dirty])

  const updateWordText = (i: number, word: string) => {
    setWords((prev) => prev.map((w, idx) => (idx === i ? { ...w, word } : w)))
    setDirty(true)
  }

  const updateWordTiming = (i: number, start: number, end: number) => {
    setWords((prev) => prev.map((w, idx) => (idx === i ? { ...w, start, end } : w)))
    setDirty(true)
  }

  // Bulk-shift every word by `shiftMs` milliseconds (negative = earlier).
  const shiftAll = () => {
    const d = shiftMs / 1000
    if (!d) return
    setWords((prev) => prev.map((w) => ({
      ...w,
      start: Math.max(0, w.start + d),
      end: Math.max(0.01, w.end + d),
    })))
    setDirty(true)
  }

  // Split any multi-token word into separate words, dividing its duration evenly.
  const autoSplit = () => {
    setWords((prev) => {
      const out: CaptionWord[] = []
      for (const w of prev) {
        const parts = w.word.trim().split(/\s+/).filter(Boolean)
        if (parts.length <= 1) { out.push(w); continue }
        const dur = (w.end - w.start) / parts.length
        parts.forEach((p, i) => out.push({ word: p, start: w.start + i * dur, end: w.start + (i + 1) * dur }))
      }
      return out
    })
    setSelected(null)
    setDirty(true)
  }
  const hasMultiToken = words.some((w) => w.word.trim().split(/\s+/).length > 1)

  const handleSave = () => {
    saveCaptions.mutate({ clipId, words }, {
      onSuccess: () => {
        setDirty(false)
        onChanged?.()
        toast.success('Subtítulos guardados · renderiza para ver los cambios')
      },
    })
  }

  const handleReset = () => {
    resetCaptions.mutate(clipId, {
      onSuccess: () => { setDirty(false); setSelected(null); onChanged?.() },
    })
  }

  if (captionsQuery.isLoading) {
    return (
      <div className="flex items-center gap-2 text-xs text-slate-400 py-2">
        <Loader2 className="w-3.5 h-3.5 animate-spin" />
        Cargando subtítulos...
      </div>
    )
  }

  if (words.length === 0) {
    return <p className="text-xs text-slate-500 py-2">No hay palabras con timing en este rango.</p>
  }

  const selectedWord = selected != null ? words[selected] : null
  const wordWindow = selectedWord
    ? {
        start: Math.max(0, selectedWord.start - 1.5),
        end: Math.min(clipDuration, selectedWord.end + 1.5),
      }
    : null

  return (
    <div className="space-y-3">
      {/* Bulk tools */}
      <div className="flex flex-wrap items-center gap-2 bg-slate-800/40 rounded-lg p-2 border border-slate-700/40">
        <span className="text-[11px] text-slate-400">Desplazar todo</span>
        <input type="number" step={50} value={shiftMs}
          onChange={(e) => setShiftMs(Number(e.target.value) || 0)}
          className="w-20 bg-slate-900 border border-slate-700 rounded px-1.5 py-0.5 text-white font-mono text-[11px]" />
        <span className="text-[11px] text-slate-500">ms</span>
        <Button size="sm" variant="secondary" onClick={shiftAll} disabled={!shiftMs}>Aplicar</Button>
        <div className="flex-1" />
        <Button size="sm" variant="secondary" onClick={autoSplit} disabled={!hasMultiToken}
          title="Dividir palabras que contienen espacios en palabras individuales">
          Auto-dividir
        </Button>
      </div>

      <div className="flex flex-wrap gap-1">
        {words.map((w, i) => (
          <input
            key={i}
            value={w.word}
            onChange={(e) => updateWordText(i, e.target.value)}
            onFocus={() => setSelected(i)}
            style={{ width: `${Math.max(2, w.word.length) + 1.5}ch` }}
            className={cn(
              'px-1.5 py-1 rounded text-xs font-mono bg-slate-800 border text-white text-center',
              'focus:outline-none focus:border-brand-500',
              selected === i ? 'border-brand-500 ring-1 ring-brand-500/40' : 'border-slate-700/50',
            )}
          />
        ))}
      </div>

      {selectedWord && wordWindow && (
        <div className="bg-slate-800/40 rounded-lg p-2 border border-slate-700/40 space-y-1">
          <p className="text-[10px] text-slate-400">Retimar "{selectedWord.word}"</p>
          <Timeline
            windowStart={wordWindow.start}
            windowEnd={wordWindow.end}
            start={selectedWord.start}
            end={selectedWord.end}
            onChange={(s, e) => updateWordTiming(selected!, s, e)}
            minDuration={0.05}
            maxDuration={Math.max(0.1, wordWindow.end - wordWindow.start)}
          />
        </div>
      )}

      <div className="flex items-center gap-2">
        <Button size="sm" onClick={handleSave} loading={saveCaptions.isPending} disabled={!dirty}>
          <Save className="w-3.5 h-3.5" />
          Guardar subtítulos
        </Button>
        {captionsQuery.data?.is_custom && (
          <Button variant="secondary" size="sm" onClick={handleReset} loading={resetCaptions.isPending}>
            <RotateCcw className="w-3.5 h-3.5" />
            Restaurar automático
          </Button>
        )}
      </div>
      <p className="text-[10px] text-slate-500">
        Click en una palabra para editar el texto o arrastrar su tiempo. Los cambios se ven al renderizar.
      </p>
    </div>
  )
}
