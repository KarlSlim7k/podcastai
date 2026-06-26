import { useState } from 'react'
import {
  Clapperboard, ImageIcon, FolderOpen, Save, Trash2,
  PanelLeftClose, PanelLeftOpen, Layers, Loader2,
} from 'lucide-react'
import { BrollPanel } from './BrollPanel'
import { RenderCard } from './VerticalEditorParts'
import { cn } from '../../utils'
import type { Clip, VerticalRender, VerticalPreset, BrollSuggestion } from '../../types'

type Section = 'renders' | 'broll' | 'presets'

export interface EditorLeftSidebarProps {
  collapsed: boolean
  onToggleCollapsed: () => void
  // Renders gallery
  projectId: number
  clip: Clip
  renders: VerticalRender[]
  previewRenderId: number | null
  onSelectRender: (r: VerticalRender) => void
  onDeleteRender: (id: number) => void
  // B-roll suggestions
  clipId: number
  onPickBroll: (s: BrollSuggestion) => void
  isBrollAdded: (s: BrollSuggestion) => boolean
  // Presets
  presets: VerticalPreset[]
  onApplyPreset: (p: VerticalPreset) => void
  onDeletePreset: (id: number) => void
  onSavePreset: () => void
  // Batch apply (Priority 6)
  otherClipsCount: number
  onApplyToAllClips: () => void
  applyingToAll: boolean
}

const RAIL: { id: Section; icon: React.ReactNode; label: string }[] = [
  { id: 'renders', icon: <Clapperboard className="w-5 h-5" />, label: 'Renders' },
  { id: 'broll', icon: <ImageIcon className="w-5 h-5" />, label: 'B-rolls' },
  { id: 'presets', icon: <FolderOpen className="w-5 h-5" />, label: 'Presets' },
]

/**
 * VS Code-style activity bar: a 48px icon rail that is always visible, plus an
 * expandable 260px content panel. Clicking an icon opens its section; clicking
 * the active icon (or the header toggle) collapses the panel.
 */
export function EditorLeftSidebar(props: EditorLeftSidebarProps) {
  const { collapsed, onToggleCollapsed } = props
  const [section, setSection] = useState<Section>('renders')

  const onRailClick = (id: Section) => {
    if (collapsed) { setSection(id); onToggleCollapsed() }
    else if (id === section) onToggleCollapsed()
    else setSection(id)
  }

  return (
    <div className="flex h-full min-h-0">
      {/* Icon rail */}
      <div className="w-12 flex-shrink-0 bg-slate-900 border-r border-slate-700/50 flex flex-col items-center gap-1 py-2">
        <button onClick={onToggleCollapsed}
          className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 mb-1"
          title={collapsed ? 'Expandir panel' : 'Colapsar panel'}>
          {collapsed ? <PanelLeftOpen className="w-5 h-5" /> : <PanelLeftClose className="w-5 h-5" />}
        </button>
        {RAIL.map((r) => (
          <button key={r.id} onClick={() => onRailClick(r.id)} title={r.label}
            className={cn('p-2 rounded-lg transition-colors',
              !collapsed && section === r.id ? 'bg-brand-600/30 text-brand-200' : 'text-slate-400 hover:text-white hover:bg-slate-800')}>
            {r.icon}
          </button>
        ))}
      </div>

      {/* Expandable content */}
      <div className={cn('bg-slate-900 border-r border-slate-700/50 overflow-hidden transition-all duration-300 ease-in-out',
        collapsed ? 'w-0' : 'w-[260px]')}>
        <div className="w-[260px] h-full overflow-y-auto p-3">
          {section === 'renders' && (
            <SectionShell title={`Renders (${props.renders.length})`}>
              {props.otherClipsCount > 0 && (
                <button onClick={props.onApplyToAllClips} disabled={props.applyingToAll}
                  className="w-full mb-3 flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs bg-brand-600/20 border border-brand-500/40 text-brand-200 hover:bg-brand-600/30 disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-brand-500">
                  {props.applyingToAll ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Layers className="w-3.5 h-3.5" />}
                  Aplicar ajustes a los {props.otherClipsCount} clips
                </button>
              )}
              {props.renders.length === 0 ? (
                <p className="text-xs text-slate-500 py-2">Aún no has renderizado este clip.</p>
              ) : (
                <div className="grid grid-cols-2 gap-2">
                  {props.renders.map((r) => (
                    <RenderCard key={r.id} render={r} projectId={props.projectId} clip={props.clip}
                      isActive={props.previewRenderId === r.id}
                      onSelect={() => props.onSelectRender(r)}
                      onDelete={() => props.onDeleteRender(r.id)} />
                  ))}
                </div>
              )}
            </SectionShell>
          )}

          {section === 'broll' && (
            <SectionShell title="B-rolls sugeridos (IA)">
              <BrollPanel projectId={props.projectId} clipId={props.clipId} onPick={props.onPickBroll} isAdded={props.isBrollAdded} />
            </SectionShell>
          )}

          {section === 'presets' && (
            <SectionShell title="Presets"
              action={
                <button onClick={props.onSavePreset} className="text-xs text-brand-400 hover:underline flex items-center gap-1">
                  <Save className="w-3.5 h-3.5" />Guardar
                </button>
              }>
              {props.presets.length === 0 ? (
                <p className="text-xs text-slate-500 py-2">No hay presets guardados.</p>
              ) : (
                <div className="space-y-1">
                  {props.presets.map((preset) => (
                    <div key={preset.id} className="flex items-center justify-between gap-2 px-2 py-1.5 rounded-lg bg-slate-800/40 border border-slate-700/40 hover:bg-slate-800/70">
                      <button onClick={() => props.onApplyPreset(preset)} className="flex-1 text-left text-sm text-white truncate">{preset.name}</button>
                      <button onClick={() => props.onDeletePreset(preset.id)} className="p-1 text-slate-500 hover:text-red-400 flex-shrink-0" title="Eliminar preset">
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </SectionShell>
          )}
        </div>
      </div>
    </div>
  )
}

function SectionShell({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-white">{title}</h3>
        {action}
      </div>
      {children}
    </div>
  )
}
