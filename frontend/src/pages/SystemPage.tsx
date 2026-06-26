import { useQuery } from '@tanstack/react-query'
import { Cpu, Mic2, Brain, Server, CheckCircle, XCircle, RefreshCw, AlertTriangle, Zap } from 'lucide-react'
import { systemApi } from '../services/api'
import { useHardwareInfo } from '../hooks/useProject'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { Button } from '../components/ui/Button'

const WHISPER_MODEL_SIZES: Record<string, string> = {
  'large-v3': '~3.1 GB',
  'large-v2': '~3.1 GB',
  'large': '~3.1 GB',
  'medium': '~1.5 GB',
  'small': '~500 MB',
  'base': '~150 MB',
  'tiny': '~80 MB',
}

export function SystemPage() {
  const { data: status, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['system-status'],
    queryFn: () => systemApi.status(),
    staleTime: 10_000,
  })

  const { data: models = [] } = useQuery({
    queryKey: ['ollama-models'],
    queryFn: () => systemApi.models(),
    staleTime: 30_000,
  })

  const { data: hw } = useHardwareInfo()

  return (
    <div className="p-8 space-y-6 max-w-5xl">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Estado del Sistema</h1>
        <Button variant="secondary" onClick={() => refetch()} loading={isFetching} size="sm">
          <RefreshCw className="w-4 h-4" />
          Actualizar
        </Button>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16">
          <div className="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : (
        <div className="grid gap-6 md:grid-cols-2">

          {/* GPU / Cómputo */}
          <Card glow={status?.cuda_available || hw?.has_metal}>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Cpu className="w-5 h-5 text-brand-400" />
                <h2 className="font-semibold text-white">GPU / Cómputo</h2>
              </div>
            </CardHeader>
            <CardBody className="space-y-3">
              {hw ? (
                <>
                  <InfoRow
                    label="Backend"
                    value={
                      hw.is_apple_silicon ? 'Apple Silicon (Metal)' :
                      hw.has_cuda ? 'NVIDIA CUDA' : 'CPU'
                    }
                  />
                  <InfoRow label="Compute" value={hw.compute_backend.toUpperCase()} />
                </>
              ) : (
                <StatusRow label="CUDA disponible" value={status?.cuda_available} />
              )}
              {status?.cuda_available && (
                <>
                  <InfoRow
                    label="VRAM Total"
                    value={status.vram_total_gb ? `${status.vram_total_gb.toFixed(1)} GB` : '--'}
                  />
                  <InfoRow
                    label="VRAM Libre"
                    value={status.vram_free_gb ? `${status.vram_free_gb.toFixed(1)} GB` : '--'}
                  />
                  {status.vram_total_gb && status.vram_free_gb && (
                    <div>
                      <div className="flex justify-between text-xs text-slate-400 mb-1">
                        <span>Uso VRAM</span>
                        <span>
                          {((status.vram_total_gb - status.vram_free_gb) / status.vram_total_gb * 100).toFixed(0)}%
                        </span>
                      </div>
                      <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-gradient-to-r from-brand-500 to-brand-600 rounded-full"
                          style={{
                            width: `${((status.vram_total_gb - status.vram_free_gb) / status.vram_total_gb * 100)}%`
                          }}
                        />
                      </div>
                    </div>
                  )}
                </>
              )}
              {hw?.has_metal && !status?.cuda_available && (
                <div className="flex items-center gap-1.5 text-green-400 text-sm">
                  <CheckCircle className="w-4 h-4" />
                  <span>Metal activo (Neural Engine disponible)</span>
                </div>
              )}
              {!status?.cuda_available && !hw?.has_metal && (
                <div className="bg-slate-800/60 rounded-lg p-3">
                  <p className="text-xs text-slate-400">
                    Sin GPU detectada. La transcripción usará CPU, que es más lenta.
                    Considera usar un modelo Whisper más ligero (<code className="text-brand-400">small</code> o <code className="text-brand-400">medium</code>).
                  </p>
                </div>
              )}
            </CardBody>
          </Card>

          {/* Whisper */}
          <Card glow={status?.whisper_available}>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Mic2 className="w-5 h-5 text-brand-400" />
                <h2 className="font-semibold text-white">Whisper</h2>
              </div>
            </CardHeader>
            <CardBody className="space-y-3">
              <StatusRow label="Instalado" value={status?.whisper_available} />
              {hw && (
                <>
                  <InfoRow
                    label="Backend"
                    value={
                      hw.whisper_backend === 'mlx_whisper'
                        ? 'mlx-whisper (Apple Silicon)'
                        : 'faster-whisper'
                    }
                  />
                  <InfoRow label="Device" value={hw.compute_backend.toUpperCase()} />
                </>
              )}
              {status?.whisper_available && (
                <>
                  <InfoRow label="Modelo configurado" value={status.whisper_model_name || 'large-v3'} />
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-slate-400">Modelo en caché</span>
                    {status.whisper_model_cached ? (
                      <div className="flex items-center gap-1.5 text-green-400 text-sm">
                        <CheckCircle className="w-4 h-4" />
                        <span>Listo</span>
                      </div>
                    ) : (
                      <div className="flex items-center gap-1.5 text-amber-400 text-sm">
                        <AlertTriangle className="w-4 h-4" />
                        <span>Pendiente de descarga</span>
                      </div>
                    )}
                  </div>
                  {!status.whisper_model_cached && (
                    <div className="bg-amber-900/20 border border-amber-800/30 rounded-lg p-3">
                      <p className="text-xs text-amber-300">
                        La primera transcripción descargará el modelo{' '}
                        <strong>{status.whisper_model_name || 'large-v3'}</strong>{' '}
                        ({WHISPER_MODEL_SIZES[status.whisper_model_name] ?? '~3 GB'}).
                        Puede tardar varios minutos según tu conexión. Las siguientes
                        transcripciones arrancan de inmediato.
                      </p>
                    </div>
                  )}
                </>
              )}
            </CardBody>
          </Card>

          {/* Ollama */}
          <Card glow={status?.ollama_available}>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Brain className="w-5 h-5 text-brand-400" />
                <h2 className="font-semibold text-white">Ollama</h2>
              </div>
            </CardHeader>
            <CardBody className="space-y-3">
              <StatusRow label="Conectado" value={status?.ollama_available} />
              <InfoRow label="Endpoint" value="http://localhost:11434" />
              <InfoRow
                label="Modelos instalados"
                value={status?.ollama_models.length.toString() ?? '0'}
              />
              {models.length > 0 && (
                <div>
                  <p className="text-xs text-slate-400 mb-2">Modelos disponibles:</p>
                  <div className="space-y-1.5">
                    {models.map(m => (
                      <div
                        key={m.name}
                        className="flex items-center justify-between bg-slate-800/60 rounded-lg px-3 py-2"
                      >
                        <span className="text-sm text-white font-mono">{m.name}</span>
                        {m.size && (
                          <span className="text-xs text-slate-500">
                            {(m.size / 1024 / 1024 / 1024).toFixed(1)} GB
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {!status?.ollama_available && (
                <div className="bg-yellow-900/20 border border-yellow-800/30 rounded-lg p-3">
                  <p className="text-xs text-yellow-400">
                    Ollama no está disponible. Inicia el servicio con:{' '}
                    <span className="font-mono">ollama serve</span>
                  </p>
                </div>
              )}
              {status?.ollama_available && models.length === 0 && (
                <div className="bg-yellow-900/20 border border-yellow-800/30 rounded-lg p-3">
                  <p className="text-xs text-yellow-400">
                    Ollama conectado pero sin modelos. Descarga uno con:{' '}
                    <span className="font-mono">ollama pull qwen3:8b</span>
                  </p>
                </div>
              )}
            </CardBody>
          </Card>

          {/* Hardware detectado */}
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Server className="w-5 h-5 text-brand-400" />
                <h2 className="font-semibold text-white">Hardware detectado</h2>
              </div>
            </CardHeader>
            <CardBody className="space-y-3">
              <StatusRow label="Backend API" value={true} />
              {hw ? (
                <>
                  <InfoRow
                    label="Sistema operativo"
                    value={
                      hw.os === 'darwin'
                        ? (hw.is_apple_silicon ? 'macOS (Apple Silicon)' : 'macOS (Intel)')
                        : hw.os === 'windows' ? 'Windows' : 'Linux'
                    }
                  />
                  <InfoRow
                    label="Aceleración video"
                    value={
                      hw.has_ffmpeg_nvenc ? 'NVENC (NVIDIA)' :
                      hw.has_ffmpeg_videotoolbox ? 'VideoToolbox (Apple)' :
                      hw.has_ffmpeg_qsv ? 'Quick Sync (Intel)' :
                      'libx264 (CPU)'
                    }
                  />
                  <InfoRow label="Encoder ffmpeg" value={hw.ffmpeg_encoder} />
                </>
              ) : (
                <InfoRow label="Base de datos" value="SQLite (local)" />
              )}
              <InfoRow label="API" value="/api/v1" />
              <InfoRow label="Docs" value="/api/docs" link="/api/docs" />
              {status?.llamacpp_available && (
                <>
                  <div className="pt-1 border-t border-slate-700/50">
                    <p className="text-xs text-slate-500 mb-2">LlamaCpp (fallback)</p>
                    <InfoRow label="Modelos GGUF" value={status.llamacpp_models.length.toString()} />
                    {status.llamacpp_models.map(m => (
                      <p key={m} className="text-xs text-slate-400 font-mono pl-2">{m}</p>
                    ))}
                  </div>
                </>
              )}
            </CardBody>
          </Card>

        </div>
      )}
    </div>
  )
}

function StatusRow({ label, value }: { label: string; value?: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-sm text-slate-400">{label}</span>
      {value ? (
        <div className="flex items-center gap-1.5 text-green-400 text-sm">
          <CheckCircle className="w-4 h-4" />
          <span>Sí</span>
        </div>
      ) : (
        <div className="flex items-center gap-1.5 text-red-400 text-sm">
          <XCircle className="w-4 h-4" />
          <span>No</span>
        </div>
      )}
    </div>
  )
}

function InfoRow({ label, value, link }: { label: string; value: string; link?: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-sm text-slate-400">{label}</span>
      {link ? (
        <a
          href={link}
          target="_blank"
          rel="noreferrer"
          className="text-sm text-brand-400 hover:text-brand-300 font-mono"
        >
          {value}
        </a>
      ) : (
        <span className="text-sm text-white font-mono">{value}</span>
      )}
    </div>
  )
}
