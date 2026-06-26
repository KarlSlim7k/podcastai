import { useState } from 'react'
import { Sparkles, Loader2, TrendingUp, RefreshCw, X } from 'lucide-react'
import { useClipViralityScore, useRecomputeViralityScore } from '../../hooks/useProject'
import { cn } from '../../utils'
import type { ViralityScore } from '../../types'

/**
 * Badge showing the AI-predicted virality score for a clip.
 *
 *  - Pending / not computed: dashed gray badge with a "compute" button
 *  - Computed: solid color badge (green >70, yellow 40-69, red <40)
 *    with the score + a popover showing the breakdown + reason
 */
export function ViralityBadge({
  projectId, clipId, score: initialScore, size = 'md',
}: {
  projectId: number
  clipId: number
  score: number | null
  size?: 'sm' | 'md'
}) {
  const [open, setOpen] = useState(false)
  const { data, isLoading } = useClipViralityScore(
    projectId, clipId, initialScore == null,
  )
  const recompute = useRecomputeViralityScore(projectId)

  // Prefer fresh data from the polling hook, fall back to the row's score
  const live: ViralityScore | undefined = data
  const score = live?.score ?? initialScore
  const computed = live?.computed ?? (initialScore != null)
  const isPending = !computed

  const colorClass = isPending
    ? 'border-dashed border-slate-600 text-slate-400 bg-slate-800/40'
    : (score ?? 0) >= 70
      ? 'bg-emerald-900/50 text-emerald-300 border-emerald-700/60'
      : (score ?? 0) >= 40
        ? 'bg-amber-900/40 text-amber-300 border-amber-700/60'
        : 'bg-rose-900/40 text-rose-300 border-rose-700/60'

  const px = size === 'sm' ? 'px-1.5 py-0.5 text-[10px]' : 'px-2 py-1 text-xs'

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (isPending) {
      recompute.mutate({ clipId })
    } else {
      setOpen(true)
    }
  }

  return (
    <>
      <button
        onClick={handleClick}
        className={cn(
          'inline-flex items-center gap-1 rounded-full border transition-colors',
          px,
          colorClass,
          'hover:opacity-80',
        )}
        title={isPending
          ? 'Click para calcular el score de viralidad'
          : `Score: ${score}/100 — click para ver detalles`}
      >
        {recompute.isPending ? (
          <Loader2 className={cn('animate-spin', size === 'sm' ? 'w-2.5 h-2.5' : 'w-3 h-3')} />
        ) : isPending ? (
          <Sparkles className={cn(size === 'sm' ? 'w-2.5 h-2.5' : 'w-3 h-3')} />
        ) : (
          <TrendingUp className={cn(size === 'sm' ? 'w-2.5 h-2.5' : 'w-3 h-3')} />
        )}
        <span className="font-mono font-semibold">
          {isPending ? '...' : score}
        </span>
      </button>

      {/* Detail popover */}
      {open && live && computed && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/60"
          onClick={() => setOpen(false)}
        >
          <div
            className="bg-slate-900 border border-slate-700 rounded-xl p-5 w-full max-w-md shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between mb-3">
              <div>
                <div className="flex items-center gap-2">
                  <TrendingUp className="w-5 h-5 text-emerald-400" />
                  <h3 className="text-lg font-semibold text-white">Score: {live.score}/100</h3>
                </div>
                {live.category && (
                  <p className="text-xs text-slate-400 mt-1 capitalize">
                    Categoría: {live.category}
                  </p>
                )}
              </div>
              <button
                onClick={() => setOpen(false)}
                className="p-1 rounded hover:bg-slate-800 text-slate-400"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Reason */}
            {live.reason && (
              <div className="bg-slate-800/60 rounded-lg p-3 mb-4 border border-slate-700/40">
                <p className="text-sm text-slate-200 italic">"{live.reason}"</p>
              </div>
            )}

            {/* Breakdown bars */}
            {live.breakdown && (
              <div className="space-y-2 mb-4">
                <BreakdownBar label="Hook" value={live.breakdown.hook} />
                <BreakdownBar label="Pacing" value={live.breakdown.pacing} />
                <BreakdownBar label="Emoción" value={live.breakdown.emotional_pull} />
                <BreakdownBar label="Shareability" value={live.breakdown.shareability} />
              </div>
            )}

            {/* Actions */}
            <div className="flex items-center gap-2 justify-end pt-3 border-t border-slate-700/40">
              <button
                onClick={() => { recompute.mutate({ clipId }); setOpen(false) }}
                disabled={recompute.isPending}
                className="flex items-center gap-1.5 text-xs text-slate-300 hover:text-white px-3 py-1.5 rounded-md hover:bg-slate-800 disabled:opacity-50"
              >
                {recompute.isPending
                  ? <Loader2 className="w-3 h-3 animate-spin" />
                  : <RefreshCw className="w-3 h-3" />}
                Recalcular
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}


function BreakdownBar({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-slate-400">{label}</span>
        <span className="text-xs font-mono text-white">{value}/5</span>
      </div>
      <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
        <div
          className={cn(
            'h-full transition-all',
            value >= 4 ? 'bg-emerald-500'
              : value >= 3 ? 'bg-amber-500'
              : 'bg-rose-500',
          )}
          style={{ width: `${(value / 5) * 100}%` }}
        />
      </div>
    </div>
  )
}
