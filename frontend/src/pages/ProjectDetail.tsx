import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Trash2, Mic2, Brain, MessageCircle, Download, Upload, Edit2, Check, X, Search, Sparkles, AlertTriangle } from 'lucide-react'
import { useProject, useDeleteProject, useSystemStatus } from '../hooks/useProject'
import { projectsApi, systemApi } from '../services/api'
import { Button } from '../components/ui/Button'
import { StatusBadge } from '../components/ui/Badge'
import { FileUpload } from '../components/features/FileUpload'
import { TranscriptionPanel } from '../components/features/TranscriptionPanel'
import { AnalysisPanel } from '../components/features/AnalysisPanel'
import { ChatPanel } from '../components/features/ChatPanel'
import { ExportPanel } from '../components/features/ExportPanel'
import { SearchPanel } from '../components/features/SearchPanel'
import { ClipsPanel } from '../components/features/ClipsPanel'
import { Modal } from '../components/ui/Modal'
import { formatDuration, formatDate, formatFileSize } from '../utils'
import { useQuery } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import type { Clip } from '../types'

type Tab = 'upload' | 'transcription' | 'search' | 'clips' | 'analysis' | 'chat' | 'export'

export function ProjectDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const projectId = Number(id)

  const [activeTab, setActiveTab] = useState<Tab>('upload')
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [editingName, setEditingName] = useState(false)
  const [nameInput, setNameInput] = useState('')

  // Open the vertical editor as a REAL separate browser window (popup). It's
  // the same SPA loaded at a dedicated route — a separate browser context
  // with its own React tree that talks to the same backend, so no
  // cross-window messaging is needed. The window name is keyed by clip id,
  // so re-clicking focuses the existing popup instead of opening a duplicate.
  const openVerticalEditor = (clip: Clip) => {
    const url = `/vertical-editor/${projectId}/${clip.id}`
    const win = window.open(url, `vertical-editor-${clip.id}`, 'popup=yes,width=1400,height=920')
    if (win) {
      win.focus()
    } else {
      // Popup blocked — fall back to a new tab so the user isn't stuck.
      window.open(url, '_blank')
    }
  }

  const { data: project, isLoading } = useProject(projectId)
  const { data: system } = useSystemStatus()
  const { data: models = [] } = useQuery({
    queryKey: ['ollama-models'],
    queryFn: () => systemApi.models(),
    staleTime: 60_000,
  })
  const deleteProject = useDeleteProject()

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  if (!project) return null

  const handleDelete = async () => {
    await deleteProject.mutateAsync(project.id)
    navigate('/projects')
  }

  const handleSaveName = async () => {
    if (!nameInput.trim()) return
    await projectsApi.update(project.id, { name: nameInput.trim() })
    toast.success('Nombre actualizado')
    setEditingName(false)
  }

  const tabs: { key: Tab; label: string; icon: React.ReactNode; disabled?: boolean }[] = [
    { key: 'upload', label: 'Archivo', icon: <Upload className="w-4 h-4" /> },
    { key: 'transcription', label: 'Transcripción', icon: <Mic2 className="w-4 h-4" />, disabled: !project.audio_duration },
    { key: 'search', label: 'Búsqueda', icon: <Search className="w-4 h-4" />, disabled: !project.transcription?.text },
    { key: 'clips', label: 'Reels/Shorts', icon: <Sparkles className="w-4 h-4" />, disabled: !project.transcription?.text || !project.transcription.segments?.length },
    { key: 'analysis', label: 'Análisis IA', icon: <Brain className="w-4 h-4" />, disabled: !project.transcription?.text },
    { key: 'chat', label: 'Chat', icon: <MessageCircle className="w-4 h-4" />, disabled: !project.transcription?.text },
    { key: 'export', label: 'Exportar', icon: <Download className="w-4 h-4" /> },
  ]

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-8 py-5 border-b border-slate-700/50 bg-slate-900/40">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-4">
            <button
              onClick={() => navigate('/projects')}
              className="mt-1 p-1.5 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>
            <div>
              {editingName ? (
                <div className="flex items-center gap-2">
                  <input
                    value={nameInput}
                    onChange={(e) => setNameInput(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') handleSaveName(); if (e.key === 'Escape') setEditingName(false) }}
                    autoFocus
                    className="bg-slate-800 border border-slate-600 rounded-lg px-3 py-1 text-lg font-bold text-white focus:outline-none focus:border-brand-500"
                  />
                  <button onClick={handleSaveName} className="p-1 text-green-400 hover:text-green-300"><Check className="w-4 h-4" /></button>
                  <button onClick={() => setEditingName(false)} className="p-1 text-slate-400 hover:text-white"><X className="w-4 h-4" /></button>
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <h1 className="text-xl font-bold text-white">{project.name}</h1>
                  <button onClick={() => { setNameInput(project.name); setEditingName(true) }}
                    className="p-1 text-slate-500 hover:text-slate-300 transition-colors">
                    <Edit2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              )}
              <div className="flex items-center gap-3 mt-2">
                <StatusBadge status={project.status} />
                {project.original_filename && (
                  <span className="text-xs text-slate-500">{project.original_filename}</span>
                )}
                {project.audio_duration && (
                  <span className="text-xs text-slate-400">{formatDuration(project.audio_duration)}</span>
                )}
                {project.original_file_size && (
                  <span className="text-xs text-slate-500">{formatFileSize(project.original_file_size)}</span>
                )}
                <span className="text-xs text-slate-500">{formatDate(project.created_at)}</span>
              </div>
            </div>
          </div>

          <button
            onClick={() => setShowDeleteModal(true)}
            className="p-2 rounded-lg hover:bg-red-900/20 text-slate-500 hover:text-red-400 transition-colors"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mt-5 -mb-5 pb-5 overflow-x-auto">
          {tabs.map(tab => (
            <button
              key={tab.key}
              onClick={() => !tab.disabled && setActiveTab(tab.key)}
              disabled={tab.disabled}
              className={`flex items-center gap-2 px-4 py-2 rounded-t-lg text-sm font-medium transition-all border-b-2 whitespace-nowrap
                ${activeTab === tab.key
                  ? 'text-brand-300 border-brand-500 bg-brand-900/20'
                  : tab.disabled
                    ? 'text-slate-600 border-transparent cursor-not-allowed'
                    : 'text-slate-400 border-transparent hover:text-slate-200 hover:bg-slate-800/40'
                }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-8">
        {activeTab === 'upload' && (
          <div className="max-w-2xl space-y-6">
            <FileUpload projectId={project.id} onSuccess={() => setActiveTab('transcription')} />
            {project.error_message && (
              <div className="bg-red-900/20 border border-red-800/30 rounded-xl p-4 text-sm text-red-400">
                {project.error_message}
              </div>
            )}
          </div>
        )}
        {activeTab === 'transcription' && (
          <div className="max-w-4xl space-y-4">
            {system?.whisper_available && !system.whisper_model_cached && !project.transcription && (
              <div className="bg-amber-900/20 border border-amber-700/40 rounded-xl p-4 flex items-start gap-3">
                <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-amber-300">
                    Primera transcripción: descarga automática del modelo
                  </p>
                  <p className="text-xs text-amber-400/80 mt-1">
                    Al iniciar la transcripción se descargará el modelo{' '}
                    <strong className="text-amber-300">{system.whisper_model_name || 'large-v3'}</strong>{' '}
                    (~3 GB). Puede tardar varios minutos dependiendo de tu conexión. Después quedará
                    guardado localmente y las siguientes transcripciones arrancarán de inmediato.
                  </p>
                </div>
              </div>
            )}
            <TranscriptionPanel project={project} />
          </div>
        )}
        {activeTab === 'search' && (
          <div className="max-w-4xl">
            <SearchPanel project={project} />
          </div>
        )}
        {activeTab === 'clips' && (
          <div className="max-w-4xl">
            <ClipsPanel
              project={project}
              models={models}
              onOpenVerticalEditor={openVerticalEditor}
            />
          </div>
        )}
        {activeTab === 'analysis' && (
          <div className="max-w-4xl">
            <AnalysisPanel project={project} models={models} />
          </div>
        )}
        {activeTab === 'chat' && (
          <div className="max-w-3xl">
            <ChatPanel project={project} models={models} />
          </div>
        )}
        {activeTab === 'export' && (
          <div className="max-w-2xl">
            <ExportPanel project={project} />
          </div>
        )}
      </div>

      {/* Delete Modal */}
      <Modal open={showDeleteModal} onClose={() => setShowDeleteModal(false)} title="Eliminar proyecto">
        <div className="space-y-4">
          <p className="text-slate-300">
            ¿Eliminar <span className="font-semibold text-white">"{project.name}"</span>?
            Esta acción no se puede deshacer.
          </p>
          <div className="flex gap-3 justify-end">
            <Button variant="secondary" onClick={() => setShowDeleteModal(false)}>Cancelar</Button>
            <Button variant="danger" onClick={handleDelete} loading={deleteProject.isPending}>
              <Trash2 className="w-4 h-4" />
              Eliminar
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}
