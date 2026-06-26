import { useState } from 'react'
import { X, Layers, Loader2, Download, FolderOpen } from 'lucide-react'
import {
  useVerticalPresets, useBatchCreateVerticalRender, useProjectVerticalRenders,
} from '../../hooks/useProject'
import { verticalApi } from '../../services/api'
import { Button } from '../ui/Button'
import { cn } from '../../utils'
import type { Clip, VerticalPreset, VerticalRenderRequest, VerticalRenderStatus } from '../../types'

interface BatchVerticalRenderModalProps {
  projectId: number
  clips: Clip[]
  onClose: () => void
}

const DEFAULT_REQUEST: VerticalRenderRequest = {
  layout: 'split',
  bg_style: 'blur',
  bg_color: '#1a1a2e',
  bg_color2: '#16213e',
  sub_style: 'karaoke',
  sub_color: '#FFFFFF',
  sub_highlight: '#FFD700',
  sub_outline: '#000000',
  sub_size: 64,
  sub_position: 200,
  add_title: true,
  title_text: null, // null -> backend falls back to each clip's own title
  title_color: '#FFFFFF',
  title_size: 72,
  title_position: 'top',
  watermark_path: null,
  watermark_position: 'bottom_right',
  watermark_opacity: 0.8,
  broll_placements: [],
  video_transform: null,
}

function presetToRequest(p: VerticalPreset): VerticalRenderRequest {
  return {
    ...DEFAULT_REQUEST,
    layout: p.layout,
    bg_style: p.bg_style,
    bg_color: p.bg_color,
    bg_color2: p.bg_color2,
    sub_style: p.sub_style,
    sub_color: p.sub_color,
    sub_highlight: p.sub_highlight,
    sub_outline: p.sub_outline,
    sub_size: p.sub_size,
    sub_position: p.sub_position,
    add_title: !!p.add_title,
    title_text: null, // each clip keeps its own title even when a preset is applied
    title_color: p.title_color,
    title_size: p.title_size,
    title_position: p.title_position || 'top',
    watermark_path: p.watermark_path,
    watermark_position: p.watermark_position,
    watermark_opacity: p.watermark_opacity,
  }
}

const STATUS_BADGE: Record<VerticalRenderStatus, string> = {
  pending: 'bg-amber-900/80 text-amber-200',
  processing: 'bg-amber-900/80 text-amber-200',
  completed: 'bg-green-900/80 text-green-200',
  error: 'bg-red-900/80 text-red-200',
}

const STATUS_LABEL: Record<VerticalRenderStatus, string> = {
  pending: 'En cola',
  processing: 'Procesando',
  completed: 'Listo',
  error: 'Error',
}

export function BatchVerticalRenderModal({ projectId, clips, onClose }: BatchVerticalRenderModalProps) {
  const [presetId, setPresetId] = useState<number | 'default'>('default')
  const [queuedRenderIds, setQueuedRenderIds] = useState<number[] | null>(null)
  const [skippedClips, setSkippedClips] = useState<{ clip_id: number; detail: string }[]>([])

  const presetsQuery = useVerticalPresets()
  const batchRender = useBatchCreateVerticalRender(projectId)
  const projectRendersQuery = useProjectVerticalRenders(projectId, !!queuedRenderIds)

  const clipTitleById = new Map(clips.map((c) => [c.id, c.title]))

  const handleSubmit = () => {
    const preset = presetId !== 'default' ? presetsQuery.data?.find((p) => p.id === presetId) : undefined
    const request = preset ? presetToRequest(preset) : DEFAULT_REQUEST
    batchRender.mutate(
      { clipIds: clips.map((c) => c.id), request },
      {
        onSuccess: (data) => {
          setQueuedRenderIds(data.render_ids)
          setSkippedClips(data.errors)
        },
      },
    )
  }

  const queuedRenders = queuedRenderIds
    ? (projectRendersQuery.data ?? []).filter((r) => queuedRenderIds.includes(r.id))
    : []
  const allDone = queuedRenderIds != null && queuedRenders.length === queuedRenderIds.length
    && queuedRenders.every((r) => r.status === 'completed' || r.status === 'error')

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4 overflow-y-auto">
      <div className="bg-slate-900 rounded-2xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 bg-slate-900 border-b border-slate-700/50 px-6 py-4 flex items-center justify-between z-10">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-pink-500 to-purple-600 flex items-center justify-center">
              <Layers className="w-5 h-5 text-white" />
            </div>
            <div>
              <h2 className="font-semibold text-white text-lg">Exportar en lote</h2>
              <p className="text-xs text-slate-400">{clips.length} clip{clips.length !== 1 ? 's' : ''} seleccionado{clips.length !== 1 ? 's' : ''}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-5">
          {!queuedRenderIds ? (
            <>
              {/* Clip list */}
              <div className="space-y-1.5 max-h-40 overflow-y-auto">
                {clips.map((c) => (
                  <div key={c.id} className="text-sm text-slate-300 px-3 py-1.5 bg-slate-800/50 rounded-lg truncate">
                    {c.title}
                  </div>
                ))}
              </div>

              {/* Preset picker */}
              <div>
                <label className="flex items-center gap-1.5 text-xs font-medium text-slate-400 mb-1.5">
                  <FolderOpen className="w-3.5 h-3.5" />
                  Estilo a aplicar a todos
                </label>
                <select
                  value={presetId}
                  onChange={(e) => setPresetId(e.target.value === 'default' ? 'default' : Number(e.target.value))}
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-brand-500"
                >
                  <option value="default">Predeterminado (split / blur / karaoke)</option>
                  {(presetsQuery.data ?? []).map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
                <p className="text-[10px] text-slate-500 mt-1.5">
                  Cada clip conserva su propio título; el resto del estilo (layout, fondo, subtítulos, watermark) se aplica igual a todos.
                </p>
              </div>

              <Button onClick={handleSubmit} loading={batchRender.isPending} className="w-full">
                <Layers className="w-4 h-4" />
                Renderizar {clips.length} clip{clips.length !== 1 ? 's' : ''}
              </Button>
            </>
          ) : (
            <>
              {/* Queue */}
              {skippedClips.length > 0 && (
                <div className="bg-red-900/10 border border-red-800/30 rounded-lg p-3 space-y-1">
                  <p className="text-xs font-medium text-red-400">{skippedClips.length} clip(s) no se pudieron encolar:</p>
                  {skippedClips.map((s) => (
                    <p key={s.clip_id} className="text-xs text-red-300/80 truncate">
                      {clipTitleById.get(s.clip_id) ?? `Clip ${s.clip_id}`}: {s.detail}
                    </p>
                  ))}
                </div>
              )}

              <div className="space-y-2">
                {queuedRenders.map((r) => (
                  <div key={r.id} className="flex items-center gap-3 px-3 py-2 bg-slate-800/50 rounded-lg">
                    {(r.status === 'pending' || r.status === 'processing') && (
                      <Loader2 className="w-4 h-4 text-amber-400 animate-spin flex-shrink-0" />
                    )}
                    <span className="flex-1 text-sm text-slate-200 truncate">
                      {clipTitleById.get(r.clip_id) ?? `Clip ${r.clip_id}`}
                    </span>
                    <span className={cn('text-[10px] px-1.5 py-0.5 rounded flex-shrink-0', STATUS_BADGE[r.status])}>
                      {STATUS_LABEL[r.status]}
                    </span>
                    {r.status === 'completed' && (
                      <a
                        href={verticalApi.downloadUrl(projectId, r.id)}
                        download
                        className="p-1.5 hover:bg-slate-700 rounded text-slate-300 hover:text-white flex-shrink-0"
                        title="Descargar"
                      >
                        <Download className="w-3.5 h-3.5" />
                      </a>
                    )}
                  </div>
                ))}
                {queuedRenders.length === 0 && (
                  <p className="text-sm text-slate-500 text-center py-4">Iniciando renders…</p>
                )}
              </div>

              {allDone && (
                <p className="text-xs text-green-400 text-center">
                  Lote completado. Puedes cerrar esta ventana y descargar los clips desde aquí o desde el editor de cada clip.
                </p>
              )}

              <Button variant="secondary" onClick={onClose} className="w-full">
                {allDone ? 'Cerrar' : 'Cerrar y seguir en segundo plano'}
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
