import { useNavigate } from 'react-router-dom'
import { PlusCircle, FolderOpen, Mic2, Brain, Cpu, Wifi, WifiOff } from 'lucide-react'
import { useProjects, useCreateProject, useSystemStatus } from '../hooks/useProject'
import { Button } from '../components/ui/Button'
import { Card, CardBody } from '../components/ui/Card'
import { HardwareBadge } from '../components/features/HardwareBadge'
import { StatusBadge } from '../components/ui/Badge'
import { formatDuration, formatRelativeDate } from '../utils'

export function Dashboard() {
  const navigate = useNavigate()
  const { data: projects = [] } = useProjects()
  const { data: system } = useSystemStatus()
  const createProject = useCreateProject()

  const handleNew = async () => {
    const project = await createProject.mutateAsync({ name: `Proyecto ${new Date().toLocaleDateString('es-ES')}` })
    navigate(`/projects/${project.id}`)
  }

  const stats = {
    total: projects.length,
    completed: projects.filter(p => p.status === 'completed').length,
    transcribing: projects.filter(p => p.status === 'transcribing').length,
    errors: projects.filter(p => p.status === 'error').length,
  }

  return (
    <div className="p-8 space-y-8 max-w-7xl">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">Dashboard</h1>
          <p className="text-slate-400 mt-1">Plataforma de transcripción y análisis con IA local</p>
        </div>
        <div className="flex items-center gap-3">
          <HardwareBadge />
          <Button onClick={handleNew} loading={createProject.isPending} size="lg">
            <PlusCircle className="w-5 h-5" />
            Nuevo Proyecto
          </Button>
        </div>
      </div>

      {/* System Status */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatusCard
          label="GPU CUDA"
          value={system?.cuda_available ? 'Activa' : 'No disponible'}
          icon={<Cpu className="w-5 h-5" />}
          active={system?.cuda_available}
          detail={system?.vram_total_gb ? `${system.vram_free_gb?.toFixed(1)} / ${system.vram_total_gb?.toFixed(1)} GB libre` : undefined}
        />
        <StatusCard
          label="Whisper"
          value={system?.whisper_available ? 'Disponible' : 'No instalado'}
          icon={<Mic2 className="w-5 h-5" />}
          active={system?.whisper_available}
        />
        <StatusCard
          label="Ollama"
          value={system?.ollama_available ? 'Conectado' : 'Desconectado'}
          icon={system?.ollama_available ? <Wifi className="w-5 h-5" /> : <WifiOff className="w-5 h-5" />}
          active={system?.ollama_available}
          detail={system?.ollama_available ? `${system.ollama_models.length} modelos` : undefined}
        />
        <StatusCard
          label="Proyectos"
          value={stats.total.toString()}
          icon={<FolderOpen className="w-5 h-5" />}
          active={true}
          detail={`${stats.completed} completados`}
        />
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Total', value: stats.total, color: 'text-white' },
          { label: 'Completados', value: stats.completed, color: 'text-green-400' },
          { label: 'En proceso', value: stats.transcribing, color: 'text-blue-400' },
          { label: 'Con errores', value: stats.errors, color: 'text-red-400' },
        ].map(({ label, value, color }) => (
          <Card key={label}>
            <CardBody className="text-center py-6">
              <p className={`text-3xl font-bold ${color}`}>{value}</p>
              <p className="text-sm text-slate-400 mt-1">{label}</p>
            </CardBody>
          </Card>
        ))}
      </div>

      {/* Recent Projects */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white">Proyectos recientes</h2>
          <button onClick={() => navigate('/projects')} className="text-sm text-brand-400 hover:text-brand-300">
            Ver todos →
          </button>
        </div>

        {projects.length === 0 ? (
          <Card>
            <CardBody className="py-16 text-center">
              <Mic2 className="w-16 h-16 text-slate-700 mx-auto mb-4" />
              <h3 className="text-lg font-medium text-slate-300 mb-2">Sin proyectos todavía</h3>
              <p className="text-slate-500 text-sm mb-6">
                Crea tu primer proyecto para transcribir y analizar contenido multimedia
              </p>
              <Button onClick={handleNew} loading={createProject.isPending}>
                <PlusCircle className="w-4 h-4" />
                Crear primer proyecto
              </Button>
            </CardBody>
          </Card>
        ) : (
          <div className="grid gap-3">
            {projects.slice(0, 5).map((project) => (
              <Card
                key={project.id}
                className="cursor-pointer hover:border-slate-600/70 transition-all"
                onClick={() => navigate(`/projects/${project.id}`)}
              >
                <CardBody className="flex items-center gap-4 py-4">
                  <div className="w-10 h-10 rounded-xl bg-brand-900/30 border border-brand-800/30 flex items-center justify-center flex-shrink-0">
                    <Mic2 className="w-5 h-5 text-brand-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-white truncate">{project.name}</p>
                    <div className="flex items-center gap-3 mt-1">
                      {project.original_filename && (
                        <span className="text-xs text-slate-500 truncate">{project.original_filename}</span>
                      )}
                      {project.audio_duration && (
                        <span className="text-xs text-slate-500">{formatDuration(project.audio_duration)}</span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-3 flex-shrink-0">
                    <StatusBadge status={project.status} />
                    <span className="text-xs text-slate-500">{formatRelativeDate(project.updated_at)}</span>
                  </div>
                </CardBody>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function StatusCard({ label, value, icon, active, detail }: {
  label: string; value: string; icon: React.ReactNode; active?: boolean; detail?: string
}) {
  return (
    <Card className={active ? 'border-green-800/30' : ''}>
      <CardBody className="flex items-center gap-3 py-4">
        <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${active ? 'bg-green-900/30 text-green-400' : 'bg-slate-700/60 text-slate-500'}`}>
          {icon}
        </div>
        <div>
          <p className="text-xs text-slate-400">{label}</p>
          <p className={`text-sm font-semibold ${active ? 'text-white' : 'text-slate-500'}`}>{value}</p>
          {detail && <p className="text-xs text-slate-500">{detail}</p>}
        </div>
      </CardBody>
    </Card>
  )
}
