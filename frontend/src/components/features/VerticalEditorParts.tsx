import { Play, Download, Trash2, Loader2 } from 'lucide-react'
import { verticalApi } from '../../services/api'
import { PublishButtons } from './PublishButtons'
import { cn } from '../../utils'
import type { Clip, VerticalRender, VerticalStyleInfo, BrollPlacement } from '../../types'

/**
 * Presentational pieces shared by the vertical editor window. Kept separate
 * from the page so they can be reused without pulling in the whole editor.
 */

function round2(n: number) {
  return Math.round(n * 100) / 100
}

export function BrollPlacementRow({
  placement, maxDuration, onChange, onRemove,
}: {
  placement: BrollPlacement
  maxDuration: number
  onChange: (patch: Partial<BrollPlacement>) => void
  onRemove: () => void
}) {
  // Display the placement as "inicio + duración" instead of "inicio..fin" —
  // duración is more intuitive for image overlays.
  const duration = Math.max(0, placement.end - placement.start)
  const onDurationChange = (newDur: number) => {
    const clamped = Math.max(0.1, Math.min(newDur, maxDuration - placement.start))
    onChange({ end: round2(placement.start + clamped) })
  }
  const onStartChange = (newStart: number) => {
    const clamped = Math.max(0, Math.min(newStart, maxDuration - 0.1))
    onChange({ start: round2(clamped), end: round2(Math.max(clamped + 0.1, placement.end)) })
  }
  return (
    <div className="flex items-center gap-2 bg-slate-800/40 rounded-lg p-2 border border-slate-700/40">
      <img
        src={placement.url}
        alt=""
        className="w-10 h-16 object-cover rounded border border-slate-700 flex-shrink-0"
        onError={(e) => { (e.currentTarget as HTMLImageElement).style.opacity = '0.3' }}
      />
      <div className="flex-1 space-y-1.5">
        <div className="flex items-center gap-2 text-[11px] text-slate-400">
          <label className="w-14">Inicio</label>
          <input
            type="number" min={0} max={Math.max(0, maxDuration - 0.1)} step={0.1}
            value={placement.start.toFixed(1)}
            onChange={(e) => onStartChange(Number(e.target.value))}
            className="w-16 bg-slate-900 border border-slate-700 rounded px-1.5 py-0.5 text-white font-mono text-[11px]"
          />
          <span>s</span>
          <label className="w-14 ml-1">Duración</label>
          <input
            type="number" min={0.1} max={Math.max(0.1, maxDuration - placement.start)} step={0.1}
            value={duration.toFixed(1)}
            onChange={(e) => onDurationChange(Number(e.target.value))}
            className="w-16 bg-slate-900 border border-slate-700 rounded px-1.5 py-0.5 text-white font-mono text-[11px]"
          />
          <span>s</span>
        </div>
        <div className="flex items-center gap-2 text-[11px] text-slate-400">
          <label className="w-14">Opacidad</label>
          <input
            type="range" min={10} max={100} step={5}
            value={Math.round(placement.opacity * 100)}
            onChange={(e) => onChange({ opacity: Number(e.target.value) / 100 })}
            className="flex-1 accent-brand-500"
          />
          <span className="text-white w-8 text-right font-mono">{Math.round(placement.opacity * 100)}%</span>
        </div>
      </div>
      <button
        onClick={onRemove}
        className="p-1.5 text-slate-500 hover:text-red-400 self-start"
        title="Quitar b-roll"
      >
        <Trash2 className="w-3.5 h-3.5" />
      </button>
    </div>
  )
}

export function ColorRow({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex items-center gap-2">
      <label className="text-xs text-slate-400 w-20">{label}</label>
      <input type="color" value={value} onChange={(e) => onChange(e.target.value)} className="w-10 h-8 rounded border border-slate-700 cursor-pointer" />
      <input type="text" value={value} onChange={(e) => onChange(e.target.value)}
        className="flex-1 bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-white font-mono" />
    </div>
  )
}

export function SliderRow({
  label, min, max, step = 1, value, onChange, display, hint,
}: {
  label: string; min: number; max: number; step?: number; value: number
  onChange: (v: number) => void; display: string; hint?: string
}) {
  return (
    <div>
      <div className="flex items-center gap-2">
        <label className="text-xs text-slate-400 w-20">{label}</label>
        <input type="range" min={min} max={max} step={step} value={value}
          onChange={(e) => onChange(Number(e.target.value))} className="flex-1 accent-brand-500" />
        <span className="text-xs text-white w-12 text-right">{display}</span>
      </div>
      {hint && <p className="text-[10px] text-slate-500 mt-0.5 ml-[5.5rem]">{hint}</p>}
    </div>
  )
}

export function StylePicker({
  options, value, onChange,
}: {
  options: VerticalStyleInfo[]
  value: string
  onChange: (v: string) => void
}) {
  return (
    <div className="grid grid-cols-2 gap-1.5">
      {options.map((opt) => {
        const isActive = opt.id === value
        return (
          <button
            key={opt.id}
            onClick={() => onChange(opt.id)}
            title={opt.description}
            className={cn(
              'text-left px-3 py-2 rounded-lg text-xs font-medium border transition-all',
              isActive
                ? 'bg-brand-600/30 text-brand-200 border-brand-500/50'
                : 'bg-slate-800/40 text-slate-400 border-slate-700/40 hover:text-slate-200 hover:bg-slate-800/60'
            )}
          >
            <div className="flex items-center gap-1.5">
              {opt.preview_color && (
                <span
                  className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                  style={{ backgroundColor: opt.preview_color }}
                />
              )}
              <span className="truncate">{opt.label}</span>
            </div>
          </button>
        )
      })}
    </div>
  )
}

export function RenderCard({
  render, projectId, clip, isActive, onSelect, onDelete,
}: {
  render: VerticalRender
  projectId: number
  clip: Clip
  isActive: boolean
  onSelect: () => void
  onDelete: () => void
}) {
  const isProcessing = render.status === 'pending' || render.status === 'processing'
  const isError = render.status === 'error'
  const isDone = render.status === 'completed'

  return (
    <div className={cn(
      'rounded-lg border overflow-hidden transition-all',
      isActive ? 'border-brand-500 ring-2 ring-brand-500/30' : 'border-slate-700/50',
    )}>
      {/* Thumbnail / status */}
      <button
        onClick={isDone ? onSelect : undefined}
        disabled={!isDone}
        className="w-full aspect-[9/16] bg-slate-950 flex items-center justify-center relative"
      >
        {isDone ? (
          <Play className="w-6 h-6 text-white opacity-70" />
        ) : isProcessing ? (
          <Loader2 className="w-6 h-6 text-amber-400 animate-spin" />
        ) : (
          <span className="text-xs text-red-400 text-center px-2">Error</span>
        )}
        <span className={cn(
          'absolute top-1 right-1 text-[10px] px-1.5 py-0.5 rounded',
          isProcessing ? 'bg-amber-900/80 text-amber-200' :
          isError ? 'bg-red-900/80 text-red-200' :
          'bg-green-900/80 text-green-200'
        )}>
          {render.status}
        </span>
      </button>

      {/* Info */}
      <div className="p-2 space-y-1">
        <p className="text-[10px] text-slate-400 truncate">
          {render.layout}/{render.bg_style}/{render.sub_style}
        </p>
        {isDone && render.file_size && (
          <p className="text-[10px] text-slate-500">
            {((render.file_size) / 1024 / 1024).toFixed(1)} MB · {render.duration?.toFixed(0)}s
          </p>
        )}
        {isError && render.error_message && (
          <p className="text-[10px] text-red-400 truncate" title={render.error_message}>
            {render.error_message}
          </p>
        )}

        {/* Actions */}
        {isDone && (
          <PublishButtons
            projectId={projectId}
            verticalRenderId={render.id}
            title={clip.title}
            description={(clip.description || clip.title) + " #Shorts"}
            hashtags={[]}
          />
        )}
        <div className="flex items-center gap-1 pt-1">
          {isDone && (
            <a
              href={verticalApi.downloadUrl(projectId, render.id)}
              download
              className="flex-1 flex items-center justify-center gap-1 px-2 py-1 bg-slate-800 hover:bg-slate-700 rounded text-[10px] text-slate-200 transition-colors"
            >
              <Download className="w-3 h-3" />
              Bajar
            </a>
          )}
          <button
            onClick={onDelete}
            disabled={isProcessing}
            className="p-1 hover:bg-red-900/20 rounded text-slate-500 hover:text-red-400 transition-colors disabled:opacity-30"
            title="Eliminar"
          >
            <Trash2 className="w-3 h-3" />
          </button>
        </div>
      </div>
    </div>
  )
}
