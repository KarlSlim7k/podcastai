import { cn } from '../../utils'

export type ResizeEdge = 'start' | 'end'

interface TimelineBlockProps {
  /** Left offset and width in px (already converted from time by the parent). */
  left: number
  width: number
  selected?: boolean
  /** True when this block is part of a multi-selection (distinct ring color). */
  multiSelected?: boolean
  /** Render at half opacity while the block is being dragged. */
  dragging?: boolean
  label?: string
  /** Background thumbnail (b-roll image). Falls back to a flat color. */
  thumbnailUrl?: string
  /** 0..1 — when provided, shows a small opacity badge. */
  opacity?: number
  /** Tailwind classes for the flat background + border (fallback / overlay tint). */
  colorClass?: string
  resizable?: boolean
  draggable?: boolean
  title?: string
  onSelect?: (e: React.PointerEvent) => void
  onMoveDown?: (e: React.PointerEvent) => void
  onResizeDown?: (edge: ResizeEdge, e: React.PointerEvent) => void
  onContextMenu?: (e: React.MouseEvent) => void
}

const MIN_VISUAL_PX = 20

/** A single positioned block on a track — optionally draggable and resizable. */
export function TimelineBlock({
  left, width, selected, multiSelected, dragging, label, thumbnailUrl, opacity,
  colorClass = 'bg-slate-600/40 border-slate-500', resizable, draggable, title,
  onSelect, onMoveDown, onResizeDown, onContextMenu,
}: TimelineBlockProps) {
  const w = Math.max(MIN_VISUAL_PX, width)
  return (
    <div
      className={cn(
        'group absolute top-1 bottom-1 rounded-md border overflow-hidden select-none',
        colorClass,
        draggable ? 'cursor-grab active:cursor-grabbing touch-none' : 'cursor-pointer',
        selected && (multiSelected ? 'ring-2 ring-cyan-400 z-20' : 'ring-2 ring-brand-400 z-20'),
        dragging && 'opacity-50',
      )}
      style={{ left, width: w }}
      title={title}
      onPointerDown={(e) => {
        onSelect?.(e)
        if (draggable) onMoveDown?.(e)
      }}
      onContextMenu={onContextMenu}
    >
      {thumbnailUrl && (
        <div
          className="absolute inset-0 bg-cover bg-center opacity-80"
          style={{ backgroundImage: `url(${thumbnailUrl})` }}
        />
      )}
      {/* dark scrim so the label stays readable over a thumbnail */}
      {thumbnailUrl && <div className="absolute inset-0 bg-black/20" />}

      {label && w > 34 && (
        <span className="relative z-10 block px-1.5 py-0.5 text-[10px] font-medium text-white/90 truncate pointer-events-none">
          {label}
        </span>
      )}

      {opacity != null && w > 44 && (
        <span className="absolute bottom-0.5 right-1 z-10 text-[9px] font-mono text-white/80 bg-black/40 rounded px-1 pointer-events-none">
          {Math.round(opacity * 100)}%
        </span>
      )}

      {resizable && (
        <>
          <div
            onPointerDown={(e) => { e.stopPropagation(); onResizeDown?.('start', e) }}
            className="absolute left-0 top-0 bottom-0 w-2 cursor-ew-resize bg-white/0 hover:bg-white/30 z-10 touch-none"
          />
          <div
            onPointerDown={(e) => { e.stopPropagation(); onResizeDown?.('end', e) }}
            className="absolute right-0 top-0 bottom-0 w-2 cursor-ew-resize bg-white/0 hover:bg-white/30 z-10 touch-none"
          />
        </>
      )}
    </div>
  )
}
