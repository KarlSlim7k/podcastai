import { useState } from 'react'
import { Mic, Play, Loader2, CheckCircle, AlertCircle, Clock, RotateCcw } from 'lucide-react'
import { useStartTranscription, useTranscriptionProgress, useResetTranscription } from '../../hooks/useProject'
import { Button } from '../ui/Button'
import { ProgressBar } from '../ui/ProgressBar'
import { Card, CardBody, CardHeader } from '../ui/Card'
import { cn, formatDuration } from '../../utils'
import type { Project, OllamaModel } from '../../types'

interface TranscriptionPanelProps {
  project: Project
  models?: OllamaModel[]
}

const WHISPER_MODELS = ['large-v3', 'large-v2', 'medium', 'small', 'base', 'tiny']
const LANGUAGES = [
  { value: '', label: 'Detección automática' },
  { value: 'es', label: 'Español' },
  { value: 'en', label: 'English' },
  { value: 'fr', label: 'Français' },
  { value: 'de', label: 'Deutsch' },
  { value: 'pt', label: 'Português' },
  { value: 'it', label: 'Italiano' },
  { value: 'ja', label: '日本語' },
  { value: 'zh', label: '中文' },
  { value: 'ko', label: '한국어' },
  { value: 'ru', label: 'Русский' },
  { value: 'ar', label: 'العربية' },
]

export function TranscriptionPanel({ project }: TranscriptionPanelProps) {
  const [model, setModel] = useState('large-v3')
  const [language, setLanguage] = useState('')
  const [beamSize, setBeamSize] = useState(5)

  const isTranscribing = project.status === 'transcribing'
  const hasTranscription = !!project.transcription?.text

  const startTranscription = useStartTranscription(project.id)
  const resetTranscription = useResetTranscription(project.id)
  const { data: progress } = useTranscriptionProgress(project.id, isTranscribing)

  const isStuck = isTranscribing && progress?.status === 'stale'

  const canTranscribe = !!project.audio_duration
  const audioReady = project.status === 'completed' || project.status === 'error' || hasTranscription

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Mic className="w-5 h-5 text-brand-400" />
            <h2 className="font-semibold text-white">Transcripción</h2>
          </div>
          {hasTranscription && (
            <div className="flex items-center gap-2 text-xs text-green-400">
              <CheckCircle className="w-3.5 h-3.5" />
              <span>{project.transcription!.word_count?.toLocaleString()} palabras</span>
              {project.transcription!.language_detected && (
                <span className="bg-slate-700 px-1.5 py-0.5 rounded uppercase text-slate-300">
                  {project.transcription!.language_detected}
                </span>
              )}
            </div>
          )}
        </div>
      </CardHeader>

      <CardBody className="space-y-5">
        {/* Config */}
        {!isTranscribing && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">Modelo Whisper</label>
              <select
                value={model}
                onChange={(e) => setModel(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-brand-500"
              >
                {WHISPER_MODELS.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">Idioma</label>
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-brand-500"
              >
                {LANGUAGES.map(l => <option key={l.value} value={l.value}>{l.label}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">
                Beam Size: <span className="text-white">{beamSize}</span>
              </label>
              <input
                type="range" min={1} max={10} value={beamSize}
                onChange={(e) => setBeamSize(Number(e.target.value))}
                className="w-full accent-brand-500"
              />
            </div>
          </div>
        )}

        {/* Audio info */}
        {project.audio_duration && (
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Clock className="w-4 h-4" />
            <span>Duración: <span className="text-white">{formatDuration(project.audio_duration)}</span></span>
          </div>
        )}

        {/* Progress */}
        {isTranscribing && progress && !isStuck && (
          <div className="space-y-3">
            <ProgressBar value={progress.progress} label={progress.current_step} color="brand" />
            <p className="text-xs text-slate-500 text-center animate-pulse">
              Procesando con GPU CUDA · {model}
            </p>
          </div>
        )}

        {/* Stuck state */}
        {isStuck && (
          <div className="space-y-3">
            <div className="flex items-start gap-2 text-amber-400 text-sm bg-amber-900/20 border border-amber-800/30 rounded-lg px-4 py-3">
              <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <span>{progress?.current_step ?? 'La transcripción podría estar atascada tras un reinicio del servidor.'}</span>
            </div>
            <Button
              onClick={() => resetTranscription.mutate()}
              loading={resetTranscription.isPending}
              variant="secondary"
            >
              <RotateCcw className="w-4 h-4" />
              Resetear estado
            </Button>
          </div>
        )}

        {/* Error */}
        {project.transcription?.status === 'error' && (
          <div className="flex items-start gap-2 text-red-400 text-sm bg-red-900/20 border border-red-800/30 rounded-lg px-4 py-3">
            <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <span>{project.transcription.error_message ?? 'Error desconocido'}</span>
          </div>
        )}

        {/* Action */}
        <div className="flex items-center gap-3">
          <Button
            onClick={() => startTranscription.mutate({ model, language: language || undefined, beam_size: beamSize })}
            disabled={!audioReady || isTranscribing}
            loading={startTranscription.isPending || isTranscribing}
          >
            <Play className="w-4 h-4" />
            {hasTranscription ? 'Re-transcribir' : 'Iniciar transcripción'}
          </Button>
          {!audioReady && (
            <p className="text-xs text-slate-500">
              Esperando a que el audio esté listo...
            </p>
          )}
        </div>

        {/* Speakers (only if diarization ran) */}
        {project.transcription && project.transcription.speaker_stats && project.transcription.speaker_stats.length > 0 && (
          <div className="bg-slate-800/30 rounded-lg p-3">
            <p className="text-xs font-medium text-slate-400 mb-2">Hablantes detectados</p>
            <div className="flex flex-wrap gap-2">
              {project.transcription.speaker_stats.map((sp) => {
                const colorIdx = parseInt(sp.speaker.replace(/\D/g, '') || '0', 10) % 6
                const colors = [
                  'bg-blue-500/20 text-blue-300 border-blue-500/30',
                  'bg-purple-500/20 text-purple-300 border-purple-500/30',
                  'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
                  'bg-amber-500/20 text-amber-300 border-amber-500/30',
                  'bg-rose-500/20 text-rose-300 border-rose-500/30',
                  'bg-cyan-500/20 text-cyan-300 border-cyan-500/30',
                ]
                const mins = (sp.total_time / 60).toFixed(1)
                return (
                  <div
                    key={sp.speaker}
                    className={`px-2.5 py-1 rounded-md text-xs font-medium border ${colors[colorIdx]}`}
                  >
                    {sp.speaker} · {mins} min · {sp.words} palabras
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Transcription preview */}
        {hasTranscription && (
          <div className="space-y-2">
            <p className="text-xs font-medium text-slate-400">Vista previa</p>
            <div className="bg-slate-900/60 rounded-xl p-4 max-h-48 overflow-y-auto text-sm text-slate-300 leading-relaxed">
              {project.transcription!.text!.slice(0, 600)}
              {project.transcription!.text!.length > 600 && (
                <span className="text-slate-500"> [...ver transcripción completa en la pestaña de búsqueda]</span>
              )}
            </div>
          </div>
        )}
      </CardBody>
    </Card>
  )
}
