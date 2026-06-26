import { Cpu, Zap } from 'lucide-react'
import { useHardwareInfo } from '../../hooks/useProject'

/**
 * Small badge that shows what hardware/encoder the backend detected.
 * Useful for debugging performance issues and confirming the system is
 * using GPU acceleration on macOS / Windows.
 */
export function HardwareBadge() {
  const { data, isLoading, isError } = useHardwareInfo()
  if (isLoading) {
    return (
      <div className="flex items-center gap-1.5 text-xs text-slate-500">
        <Cpu className="w-3 h-3 animate-pulse" />
        Detectando hardware...
      </div>
    )
  }
  if (isError || !data) return null

  const isGpu = data.compute_backend !== 'cpu'
  const isMac = data.os === 'darwin'
  const backendLabel = isMac && data.is_apple_silicon
    ? 'Apple Silicon'
    : data.compute_backend.toUpperCase()
  const encoderLabel = data.ffmpeg_encoder === 'libx264'
    ? 'CPU'
    : data.ffmpeg_encoder.replace('h264_', '').toUpperCase()

  return (
    <div
      className="flex items-center gap-2 text-xs"
      title={data.summary}
    >
      <div className="flex items-center gap-1 px-2 py-0.5 rounded bg-slate-800 text-slate-300">
        <Cpu className="w-3 h-3" />
        {backendLabel}
      </div>
      {isGpu && (
        <div className="flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-900/40 text-emerald-300 border border-emerald-800/50">
          <Zap className="w-3 h-3" />
          {encoderLabel} GPU
        </div>
      )}
    </div>
  )
}
