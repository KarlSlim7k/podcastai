import { X, Keyboard } from 'lucide-react'
import { SHORTCUT_GROUPS } from '../../hooks/useEditorShortcuts'

export function ShortcutsModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[70] p-4" onClick={onClose}>
      <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 w-full max-w-lg shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-white flex items-center gap-2">
            <Keyboard className="w-5 h-5 text-brand-400" />Atajos de teclado
          </h3>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white focus-visible:ring-2 focus-visible:ring-brand-500">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-4">
          {SHORTCUT_GROUPS.map((group) => (
            <div key={group.title}>
              <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-2">{group.title}</h4>
              <div className="space-y-1.5">
                {group.items.map(([keys, desc]) => (
                  <div key={keys} className="flex items-center justify-between gap-3 text-sm">
                    <span className="text-slate-300">{desc}</span>
                    <kbd className="px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-[11px] font-mono text-slate-200 whitespace-nowrap">{keys}</kbd>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
