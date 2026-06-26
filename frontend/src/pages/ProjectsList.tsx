import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { PlusCircle, Search, Mic2, Trash2 } from 'lucide-react'
import { useProjects, useCreateProject, useDeleteProject } from '../hooks/useProject'
import { Button } from '../components/ui/Button'
import { Card, CardBody } from '../components/ui/Card'
import { StatusBadge } from '../components/ui/Badge'
import { Modal } from '../components/ui/Modal'
import { formatDuration, formatRelativeDate, formatFileSize } from '../utils'

export function ProjectsList() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<number | null>(null)

  const { data: projects = [], isLoading } = useProjects()
  const createProject = useCreateProject()
  const deleteProject = useDeleteProject()

  const filtered = projects.filter(p =>
    p.name.toLowerCase().includes(search.toLowerCase()) ||
    p.original_filename?.toLowerCase().includes(search.toLowerCase())
  )

  const handleNew = async () => {
    const project = await createProject.mutateAsync({ name: `Proyecto ${new Date().toLocaleDateString('es-ES')}` })
    navigate(`/projects/${project.id}`)
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    await deleteProject.mutateAsync(deleteTarget)
    setDeleteTarget(null)
  }

  return (
    <div className="p-8 space-y-6 max-w-7xl">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Proyectos</h1>
        <Button onClick={handleNew} loading={createProject.isPending}>
          <PlusCircle className="w-4 h-4" />
          Nuevo Proyecto
        </Button>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
        <input
          type="text"
          placeholder="Buscar proyectos..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full bg-slate-800 border border-slate-700 rounded-xl pl-10 pr-4 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-brand-500"
        />
      </div>

      {/* List */}
      {isLoading ? (
        <div className="flex justify-center py-16">
          <div className="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : filtered.length === 0 ? (
        <Card>
          <CardBody className="py-16 text-center">
            <Mic2 className="w-16 h-16 text-slate-700 mx-auto mb-4" />
            <p className="text-slate-400 mb-6">
              {search ? 'No hay proyectos que coincidan con la búsqueda' : 'Sin proyectos todavía'}
            </p>
            {!search && (
              <Button onClick={handleNew}>
                <PlusCircle className="w-4 h-4" />
                Crear primer proyecto
              </Button>
            )}
          </CardBody>
        </Card>
      ) : (
        <div className="grid gap-3">
          {filtered.map((project) => (
            <Card
              key={project.id}
              className="cursor-pointer hover:border-slate-600/70 group transition-all"
              onClick={() => navigate(`/projects/${project.id}`)}
            >
              <CardBody className="flex items-center gap-4 py-4">
                <div className="w-11 h-11 rounded-xl bg-brand-900/30 border border-brand-800/30 flex items-center justify-center flex-shrink-0">
                  <Mic2 className="w-5 h-5 text-brand-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-white truncate group-hover:text-brand-300 transition-colors">
                    {project.name}
                  </p>
                  <div className="flex items-center gap-3 mt-1 flex-wrap">
                    {project.original_filename && (
                      <span className="text-xs text-slate-500 truncate max-w-xs">{project.original_filename}</span>
                    )}
                    {project.audio_duration && (
                      <span className="text-xs text-slate-500">{formatDuration(project.audio_duration)}</span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-3 flex-shrink-0">
                  <StatusBadge status={project.status} />
                  <span className="text-xs text-slate-500 hidden sm:block">
                    {formatRelativeDate(project.updated_at)}
                  </span>
                  <button
                    onClick={(e) => { e.stopPropagation(); setDeleteTarget(project.id) }}
                    className="p-1.5 rounded-lg opacity-0 group-hover:opacity-100 hover:bg-red-900/20 text-slate-500 hover:text-red-400 transition-all"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </CardBody>
            </Card>
          ))}
        </div>
      )}

      {/* Delete modal */}
      <Modal open={!!deleteTarget} onClose={() => setDeleteTarget(null)} title="Eliminar proyecto">
        <div className="space-y-4">
          <p className="text-slate-300">¿Estás seguro de que deseas eliminar este proyecto? Esta acción no se puede deshacer.</p>
          <div className="flex gap-3 justify-end">
            <Button variant="secondary" onClick={() => setDeleteTarget(null)}>Cancelar</Button>
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
