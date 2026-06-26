import { NavLink, useNavigate } from 'react-router-dom'
import { Mic2, FolderOpen, Settings, Zap, PlusCircle, Activity } from 'lucide-react'
import { cn } from '../../utils'
import { useProjects, useCreateProject, useHardwareInfo } from '../../hooks/useProject'
import { StatusBadge } from '../ui/Badge'

export function Sidebar() {
  const navigate = useNavigate()
  const { data: projects } = useProjects()
  const createProject = useCreateProject()
  const { data: hw } = useHardwareInfo()

  const handleNewProject = async () => {
    const name = `Proyecto ${new Date().toLocaleDateString('es-ES')}`
    const project = await createProject.mutateAsync({ name })
    navigate(`/projects/${project.id}`)
  }

  return (
    <aside className="w-72 flex-shrink-0 bg-slate-900/95 border-r border-slate-700/50 flex flex-col h-full">
      {/* Logo */}
      <div className="px-6 py-5 border-b border-slate-700/50">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center shadow-lg">
            <Mic2 className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-sm font-bold text-white">PodcastAI</h1>
            <p className="text-xs text-slate-500">Transcripción Local</p>
          </div>
        </div>
      </div>

      {/* New Project Button */}
      <div className="px-4 py-3">
        <button
          onClick={handleNewProject}
          disabled={createProject.isPending}
          className="w-full flex items-center gap-2 px-4 py-2.5 rounded-lg bg-brand-600/20 hover:bg-brand-600/30 border border-brand-600/30 text-brand-300 hover:text-brand-200 text-sm font-medium transition-all"
        >
          <PlusCircle className="w-4 h-4" />
          Nuevo Proyecto
        </button>
      </div>

      {/* Nav Links */}
      <nav className="px-3 space-y-0.5">
        <SidebarLink to="/" icon={<Activity className="w-4 h-4" />} label="Dashboard" end />
        <SidebarLink to="/projects" icon={<FolderOpen className="w-4 h-4" />} label="Proyectos" end />
        <SidebarLink to="/system" icon={<Settings className="w-4 h-4" />} label="Sistema" end />
      </nav>

      {/* Recent Projects */}
      {projects && projects.length > 0 && (
        <div className="flex-1 overflow-y-auto px-3 py-3 mt-2">
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wider px-2 mb-2">
            Recientes
          </p>
          <div className="space-y-0.5">
            {projects.slice(0, 10).map((p) => (
              <NavLink
                key={p.id}
                to={`/projects/${p.id}`}
                className={({ isActive }) => cn(
                  'flex flex-col gap-1 px-3 py-2.5 rounded-lg text-sm transition-all',
                  isActive
                    ? 'bg-brand-600/20 text-white'
                    : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
                )}
              >
                <span className="font-medium truncate">{p.name}</span>
                <StatusBadge status={p.status} />
              </NavLink>
            ))}
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="px-6 py-4 border-t border-slate-700/50">
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <Zap className="w-3.5 h-3.5 text-brand-500" />
          <span>
            {hw
              ? hw.is_apple_silicon
                ? 'Apple Silicon · mlx-whisper · Ollama'
                : hw.has_cuda
                  ? 'CUDA · Faster-Whisper · Ollama'
                  : 'CPU · Faster-Whisper · Ollama'
              : 'Faster-Whisper · Ollama'}
          </span>
        </div>
      </div>
    </aside>
  )
}

function SidebarLink({ to, icon, label, end }: {
  to: string; icon: React.ReactNode; label: string; end?: boolean
}) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) => cn(
        'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all',
        isActive
          ? 'bg-brand-600/20 text-brand-300 border border-brand-600/20'
          : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
      )}
    >
      {icon}
      {label}
    </NavLink>
  )
}
