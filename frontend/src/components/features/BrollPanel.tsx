import { useState } from 'react'
import { Image as ImageIcon, Loader2, RefreshCw, ImagePlus, Check, Sparkles } from 'lucide-react'
import { useBrollSuggestions } from '../../hooks/useProject'
import { cn } from '../../utils'
import type { BrollSuggestion } from '../../types'

/**
 * B-roll suggestions panel for the vertical editor.
 *
 * Phase 11: fetch AI-suggested stock images via Ollama + Pexels (or mock).
 * Phase 14: clicking a thumbnail now *adds* the suggestion to the parent
 * editor's B-roll placements list (instead of just toggling a local
 * 'picked' flag). The parent owns the placement state so the placements
 * get sent in the VerticalRenderRequest.
 */
export function BrollPanel({
  projectId, clipId,
  onPick,
  isAdded,
}: {
  projectId: number
  clipId: number
  /** Called when the user clicks a suggestion to add it as a placement. */
  onPick: (suggestion: BrollSuggestion) => void
  /** Returns true if the suggestion is already in the placements list
   *  (used to disable the toggle / show "added" state). */
  isAdded: (suggestion: BrollSuggestion) => boolean
}) {
  const { data, isLoading, isError, refetch, isFetching } = useBrollSuggestions(projectId, clipId)

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 p-3 bg-slate-800/40 rounded-lg border border-slate-700/50">
        <Loader2 className="w-4 h-4 text-brand-400 animate-spin" />
        <span className="text-xs text-slate-400">
          Analizando transcripción con IA y buscando b-rolls...
        </span>
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div className="flex items-center gap-2 p-3 bg-rose-900/20 rounded-lg border border-rose-700/40">
        <span className="text-xs text-rose-300">Error al cargar b-rolls</span>
        <button
          onClick={() => refetch()}
          className="ml-auto text-xs text-brand-400 hover:underline"
        >
          Reintentar
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {/* Header: keywords + source + refresh */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1">
          <div className="flex items-center gap-1.5 mb-1">
            <Sparkles className="w-3 h-3 text-brand-400" />
            <p className="text-xs font-medium text-slate-300">
              Sugerencias de IA
              {data.source === 'mock' && (
                <span className="ml-1.5 text-[10px] text-amber-400 font-normal">
                  (mock — agrega PEXELS_API_KEY al .env para fotos reales)
                </span>
              )}
            </p>
          </div>
          <div className="flex flex-wrap gap-1">
            {data.keywords.slice(0, 4).map((kw: string) => (
              <span
                key={kw}
                className="text-[10px] bg-slate-800 text-slate-300 px-1.5 py-0.5 rounded border border-slate-700/50"
              >
                {kw}
              </span>
            ))}
          </div>
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-white disabled:opacity-50"
          title="Regenerar sugerencias"
        >
          <RefreshCw className={cn('w-3.5 h-3.5', isFetching && 'animate-spin')} />
        </button>
      </div>

      {/* Grid of b-roll thumbnails */}
      {data.suggestions.length === 0 ? (
        <p className="text-xs text-slate-500 text-center py-4">
          No se encontraron sugerencias para este clip.
        </p>
      ) : (
        <div className="grid grid-cols-3 gap-1.5">
          {data.suggestions.map((b: BrollSuggestion) => (
            <BrollCard
              key={b.id}
              broll={b}
              added={isAdded(b)}
              onPick={() => onPick(b)}
            />
          ))}
        </div>
      )}

      <p className="text-[10px] text-slate-500">
        Click en una imagen para añadirla al video. Luego ajusta su inicio, duración y opacidad abajo.
      </p>
    </div>
  )
}

function BrollCard({
  broll, added, onPick,
}: {
  broll: BrollSuggestion
  added: boolean
  onPick: () => void
}) {
  const [loaded, setLoaded] = useState(false)
  const [errored, setErrored] = useState(false)

  return (
    <button
      onClick={onPick}
      className={cn(
        'relative aspect-[9/16] rounded-md overflow-hidden border-2 transition-all',
        added
          ? 'border-emerald-500 ring-2 ring-emerald-500/30'
          : 'border-slate-700/50 hover:border-slate-500',
      )}
      title={`${broll.keyword} — ${broll.photographer}`}
    >
      {!loaded && !errored && (
        <div className="absolute inset-0 bg-slate-800 flex items-center justify-center">
          <Loader2 className="w-3 h-3 text-slate-500 animate-spin" />
        </div>
      )}
      {errored ? (
        <div className="absolute inset-0 bg-slate-800 flex flex-col items-center justify-center text-slate-500 p-1">
          <ImagePlus className="w-3 h-3 mb-0.5" />
          <span className="text-[8px]">no img</span>
        </div>
      ) : (
        <img
          src={broll.thumb_url}
          alt={broll.keyword}
          loading="lazy"
          onLoad={() => setLoaded(true)}
          onError={() => setErrored(true)}
          className={cn(
            'w-full h-full object-cover transition-opacity',
            loaded ? 'opacity-100' : 'opacity-0',
          )}
        />
      )}
      {added && (
        <div className="absolute top-1 right-1 w-4 h-4 rounded-full bg-emerald-500 flex items-center justify-center">
          <Check className="w-2.5 h-2.5 text-white" />
        </div>
      )}
      <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent p-1">
        <p className="text-[8px] text-white truncate">{broll.keyword}</p>
      </div>
    </button>
  )
}
