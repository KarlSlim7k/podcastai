import { useState } from 'react'
import { Download, FileText, FileJson, File, Subtitles } from 'lucide-react'
import { useCreateExport } from '../../hooks/useProject'
import { Card, CardHeader, CardBody } from '../ui/Card'
import { Button } from '../ui/Button'
import { formatFileSize, formatRelativeDate } from '../../utils'
import { exportApi } from '../../services/api'
import type { Project, ExportFormat } from '../../types'

const EXPORT_FORMATS: { format: ExportFormat; label: string; icon: React.ReactNode; description: string }[] = [
  { format: 'txt', label: 'TXT', icon: <FileText className="w-5 h-5" />, description: 'Texto plano' },
  { format: 'markdown', label: 'Markdown', icon: <FileText className="w-5 h-5" />, description: 'Formato MD' },
  { format: 'docx', label: 'Word', icon: <File className="w-5 h-5" />, description: 'Microsoft Word' },
  { format: 'pdf', label: 'PDF', icon: <File className="w-5 h-5" />, description: 'Portable Document' },
  { format: 'json', label: 'JSON', icon: <FileJson className="w-5 h-5" />, description: 'Datos completos' },
  { format: 'srt', label: 'SRT', icon: <Subtitles className="w-5 h-5" />, description: 'Subtítulos SRT' },
  { format: 'vtt', label: 'VTT', icon: <Subtitles className="w-5 h-5" />, description: 'Subtítulos VTT' },
]

interface ExportPanelProps {
  project: Project
}

export function ExportPanel({ project }: ExportPanelProps) {
  const [generatingFormat, setGeneratingFormat] = useState<ExportFormat | null>(null)
  const createExport = useCreateExport(project.id)

  const handleExport = async (format: ExportFormat) => {
    setGeneratingFormat(format)
    try {
      const exp = await createExport.mutateAsync(format)
      const url = exportApi.downloadUrl(project.id, exp.id)
      const a = document.createElement('a')
      a.href = url
      a.download = `${project.name}_${format}`
      a.click()
    } finally {
      setGeneratingFormat(null)
    }
  }

  const hasTranscription = !!project.transcription?.text

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Download className="w-5 h-5 text-brand-400" />
          <h2 className="font-semibold text-white">Exportar</h2>
        </div>
      </CardHeader>
      <CardBody className="space-y-5">
        {/* Format grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {EXPORT_FORMATS.map(({ format, label, icon, description }) => {
            const isSubtitle = format === 'srt' || format === 'vtt'
            const disabled = !hasTranscription
            const isGenerating = generatingFormat === format

            return (
              <button
                key={format}
                onClick={() => handleExport(format)}
                disabled={disabled || !!generatingFormat}
                className="flex flex-col items-center gap-2 p-4 rounded-xl border border-slate-700/50 bg-slate-800/40 hover:bg-slate-700/40 hover:border-slate-600/60 transition-all disabled:opacity-40 disabled:cursor-not-allowed group"
              >
                <div className="text-slate-400 group-hover:text-brand-400 transition-colors">
                  {isGenerating ? (
                    <div className="w-5 h-5 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
                  ) : icon}
                </div>
                <div className="text-center">
                  <p className="text-sm font-medium text-white">{label}</p>
                  <p className="text-xs text-slate-500">{description}</p>
                </div>
              </button>
            )
          })}
        </div>

        {!hasTranscription && (
          <p className="text-sm text-slate-500 text-center">
            Necesitas una transcripción para exportar
          </p>
        )}

        {/* Export history */}
        {project.exports.length > 0 && (
          <div>
            <p className="text-xs font-medium text-slate-400 mb-3">Exportaciones anteriores</p>
            <div className="space-y-2">
              {project.exports.slice().reverse().map((exp) => (
                <div key={exp.id} className="flex items-center justify-between py-2 px-3 rounded-lg bg-slate-800/40 border border-slate-700/30">
                  <div className="flex items-center gap-3">
                    <span className="text-xs font-mono uppercase text-brand-400 bg-brand-900/30 px-2 py-0.5 rounded">
                      {exp.export_type}
                    </span>
                    <div>
                      <p className="text-xs text-slate-400">{formatRelativeDate(exp.created_at)}</p>
                      {exp.file_size && <p className="text-xs text-slate-600">{formatFileSize(exp.file_size)}</p>}
                    </div>
                  </div>
                  <a
                    href={exportApi.downloadUrl(project.id, exp.id)}
                    download
                    className="p-1.5 rounded-lg hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
                  >
                    <Download className="w-3.5 h-3.5" />
                  </a>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardBody>
    </Card>
  )
}
