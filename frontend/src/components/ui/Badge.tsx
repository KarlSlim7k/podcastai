import { cn } from '../../utils'
import type { ProjectStatus } from '../../types'

interface BadgeProps {
  status: string
  className?: string
}

const statusStyles: Record<string, string> = {
  created: 'bg-slate-700/60 text-slate-300 border-slate-600/40',
  uploading: 'bg-blue-900/40 text-blue-300 border-blue-700/40',
  extracting_audio: 'bg-yellow-900/40 text-yellow-300 border-yellow-700/40',
  transcribing: 'bg-purple-900/40 text-purple-300 border-purple-700/40',
  analyzing: 'bg-indigo-900/40 text-indigo-300 border-indigo-700/40',
  completed: 'bg-green-900/40 text-green-300 border-green-700/40',
  error: 'bg-red-900/40 text-red-300 border-red-700/40',
  pending: 'bg-slate-700/60 text-slate-300 border-slate-600/40',
  processing: 'bg-blue-900/40 text-blue-300 border-blue-700/40',
}

const statusLabels: Record<string, string> = {
  created: 'Creado',
  uploading: 'Subiendo',
  extracting_audio: 'Extrayendo audio',
  transcribing: 'Transcribiendo',
  analyzing: 'Analizando',
  completed: 'Completado',
  error: 'Error',
  pending: 'Pendiente',
  processing: 'Procesando',
}

export function StatusBadge({ status, className }: BadgeProps) {
  return (
    <span className={cn(
      'inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border',
      statusStyles[status] ?? 'bg-slate-700 text-slate-300 border-slate-600',
      className
    )}>
      {['uploading', 'extracting_audio', 'transcribing', 'analyzing', 'processing'].includes(status) && (
        <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
      )}
      {statusLabels[status] ?? status}
    </span>
  )
}
