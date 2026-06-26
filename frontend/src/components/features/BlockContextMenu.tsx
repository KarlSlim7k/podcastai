import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'

export interface MenuItem {
  label: string
  icon?: ReactNode
  danger?: boolean
  /** Render a divider above this item. */
  separated?: boolean
  onClick: () => void
}

interface BlockContextMenuProps {
  /** Cursor position (viewport coords). */
  x: number
  y: number
  items: MenuItem[]
  onClose: () => void
}

/**
 * Floating right-click menu positioned at the cursor, flipping away from the
 * viewport edges. Closes on Escape, outside click, or item activation.
 */
export function BlockContextMenu({ x, y, items, onClose }: BlockContextMenuProps) {
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState({ left: x, top: y })

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const M = 6
    let left = x
    let top = y
    if (left + el.offsetWidth > window.innerWidth - M) left = Math.max(M, x - el.offsetWidth)
    if (top + el.offsetHeight > window.innerHeight - M) top = Math.max(M, y - el.offsetHeight)
    setPos({ left, top })
  }, [x, y])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    const onDown = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) onClose() }
    window.addEventListener('keydown', onKey)
    // capture so we beat any stopPropagation on the blocks below
    document.addEventListener('mousedown', onDown, true)
    return () => {
      window.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onDown, true)
    }
  }, [onClose])

  return (
    <div
      ref={ref}
      role="menu"
      className="fixed z-[70] min-w-[180px] py-1 rounded-lg border border-slate-700 bg-slate-800 shadow-2xl text-sm"
      style={{ left: pos.left, top: pos.top }}
      onContextMenu={(e) => e.preventDefault()}
    >
      {items.map((it, i) => (
        <div key={i}>
          {it.separated && <div className="my-1 h-px bg-slate-700" />}
          <button
            role="menuitem"
            onClick={() => { it.onClick(); onClose() }}
            className={
              'flex w-full items-center gap-2 px-3 py-1.5 text-left ' +
              (it.danger
                ? 'text-rose-300 hover:bg-rose-900/30'
                : 'text-slate-200 hover:bg-brand-600/30')
            }
          >
            {it.icon && <span className="w-3.5 h-3.5 flex items-center justify-center">{it.icon}</span>}
            {it.label}
          </button>
        </div>
      ))}
    </div>
  )
}
