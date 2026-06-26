import type { ReactNode } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { cn } from '../../utils'

interface TimelineTrackProps {
  label: string
  icon?: ReactNode
  /** Width of the pinned label column (px). */
  labelWidth: number
  /** Width of the scrolling content area (px) = duration * pps. */
  contentWidth: number
  /** Row height in px. */
  height: number
  /** Zebra striping driven by the row index. */
  zebra?: boolean
  collapsible?: boolean
  collapsed?: boolean
  onToggleCollapse?: () => void
  /** Shown centered in the content area when there are no blocks. */
  placeholder?: string
  /** Pointer-down on the empty track background (used for pan / seek). */
  onContentPointerDown?: (e: React.PointerEvent) => void
  /** Positioned <TimelineBlock> children. */
  children?: ReactNode
}

/**
 * One timeline row: a left label cell pinned with `position: sticky` so it
 * stays visible while the content area scrolls horizontally, plus the
 * positioned-block content area.
 */
export function TimelineTrack({
  label, icon, labelWidth, contentWidth, height, zebra, collapsible,
  collapsed, onToggleCollapse, placeholder, onContentPointerDown, children,
}: TimelineTrackProps) {
  const rowH = collapsed ? 22 : height
  return (
    <div className="flex" style={{ height: rowH }}>
      {/* Pinned label cell */}
      <div
        className={cn(
          'sticky left-0 z-40 flex items-center gap-1.5 px-2 border-r border-b border-slate-700/50 flex-shrink-0',
          zebra ? 'bg-slate-950' : 'bg-slate-900',
        )}
        style={{ width: labelWidth }}
      >
        {collapsible && (
          <button
            onClick={onToggleCollapse}
            className="text-slate-500 hover:text-slate-200 flex-shrink-0"
            title={collapsed ? 'Expandir pista' : 'Colapsar pista'}
          >
            {collapsed ? <ChevronRight className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>
        )}
        {icon && <span className="text-slate-400 flex-shrink-0">{icon}</span>}
        <span className="text-xs text-slate-400 truncate">{label}</span>
      </div>

      {/* Content area */}
      <div
        className={cn('relative border-b border-slate-700/50', zebra ? 'bg-slate-950' : 'bg-slate-900')}
        style={{ width: contentWidth }}
        onPointerDown={onContentPointerDown}
      >
        {!collapsed && children}
        {!collapsed && placeholder && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <span className="text-[11px] text-slate-600 italic">{placeholder}</span>
          </div>
        )}
      </div>
    </div>
  )
}
