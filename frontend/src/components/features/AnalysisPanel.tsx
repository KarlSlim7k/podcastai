import { useState } from 'react'
import { Brain, Play, ChevronDown, ChevronUp, Copy, Check, Loader2, RefreshCw } from 'lucide-react'
import { useStartAnalysis, useRunSingleAnalysis } from '../../hooks/useProject'
import { Button } from '../ui/Button'
import { Card, CardBody, CardHeader } from '../ui/Card'
import { cn, analysisTypeLabel } from '../../utils'
import type { Project, AnalysisType, OllamaModel } from '../../types'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const ALL_TYPES: AnalysisType[] = [
  'executive_summary', 'main_topics', 'key_ideas', 'action_items', 'important_questions',
  'chapters', 'timeline', 'learning_points',
  'facebook_post', 'twitter_post', 'linkedin_post', 'blog_article', 'youtube_description',
  'suggested_titles', 'suggested_tags', 'faq', 'conclusions',
  'viral_moments', 'best_quotes', 'seo_timestamps',
]

const TYPE_GROUPS: Record<string, AnalysisType[]> = {
  'Resumen y Análisis': ['executive_summary', 'main_topics', 'key_ideas', 'action_items', 'important_questions', 'chapters', 'timeline', 'learning_points', 'conclusions', 'faq'],
  'Contenido Social': ['facebook_post', 'twitter_post', 'linkedin_post', 'viral_moments', 'best_quotes'],
  'Contenido Largo': ['blog_article', 'youtube_description', 'seo_timestamps'],
  'SEO y Metadatos': ['suggested_titles', 'suggested_tags'],
}

interface AnalysisPanelProps {
  project: Project
  models: OllamaModel[]
}

export function AnalysisPanel({ project, models }: AnalysisPanelProps) {
  const [selectedTypes, setSelectedTypes] = useState<Set<AnalysisType>>(new Set(['executive_summary', 'main_topics', 'key_ideas']))
  const [selectedModel, setSelectedModel] = useState(models[0]?.name ?? 'qwen3:14b')
  const [expandedTypes, setExpandedTypes] = useState<Set<string>>(new Set())
  const [copiedId, setCopiedId] = useState<number | null>(null)

  const startAnalysis = useStartAnalysis(project.id)
  const runSingle = useRunSingleAnalysis(project.id)

  const analysisMap = new Map(project.analyses.map(a => [a.analysis_type, a]))
  const hasTranscription = !!project.transcription?.text

  const toggleType = (type: AnalysisType) => {
    const next = new Set(selectedTypes)
    next.has(type) ? next.delete(type) : next.add(type)
    setSelectedTypes(next)
  }

  const toggleExpand = (type: string) => {
    const next = new Set(expandedTypes)
    next.has(type) ? next.delete(type) : next.add(type)
    setExpandedTypes(next)
  }

  const copyToClipboard = async (text: string, id: number) => {
    await navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const selectAll = () => setSelectedTypes(new Set(ALL_TYPES))
  const selectNone = () => setSelectedTypes(new Set())

  if (!hasTranscription) {
    return (
      <Card>
        <CardBody className="py-12 text-center">
          <Brain className="w-12 h-12 text-slate-600 mx-auto mb-3" />
          <p className="text-slate-400">Transcribe el audio primero para habilitar el análisis IA</p>
        </CardBody>
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      {/* Controls */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Brain className="w-5 h-5 text-brand-400" />
            <h2 className="font-semibold text-white">Análisis con IA</h2>
          </div>
        </CardHeader>
        <CardBody className="space-y-4">
          {/* Model selector */}
          <div className="flex items-center gap-3">
            <label className="text-xs font-medium text-slate-400 whitespace-nowrap">Modelo:</label>
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="flex-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-brand-500"
            >
              {models.length > 0 ? models.map(m => (
                <option key={m.name} value={m.name}>{m.name}</option>
              )) : (
                <>
                  <option value="qwen3:14b">qwen3:14b</option>
                  <option value="qwen3:8b">qwen3:8b</option>
                  <option value="gemma3">gemma3</option>
                </>
              )}
            </select>
          </div>

          {/* Type selection */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-400">Tipos de análisis ({selectedTypes.size} seleccionados)</span>
              <div className="flex gap-2">
                <button onClick={selectAll} className="text-xs text-brand-400 hover:text-brand-300">Todos</button>
                <span className="text-slate-600">·</span>
                <button onClick={selectNone} className="text-xs text-slate-400 hover:text-slate-300">Ninguno</button>
              </div>
            </div>

            {Object.entries(TYPE_GROUPS).map(([group, types]) => (
              <div key={group}>
                <p className="text-xs text-slate-500 mb-2">{group}</p>
                <div className="flex flex-wrap gap-2">
                  {types.map(type => {
                    const analysis = analysisMap.get(type)
                    const isDone = !!analysis?.content
                    return (
                      <button
                        key={type}
                        onClick={() => toggleType(type as AnalysisType)}
                        className={cn(
                          'px-3 py-1.5 rounded-lg text-xs font-medium border transition-all',
                          selectedTypes.has(type as AnalysisType)
                            ? 'bg-brand-600/20 border-brand-500/40 text-brand-300'
                            : 'bg-slate-800/60 border-slate-700/40 text-slate-400 hover:text-slate-300',
                          isDone && !selectedTypes.has(type as AnalysisType) && 'border-green-800/40'
                        )}
                      >
                        {isDone && <span className="mr-1 text-green-500">✓</span>}
                        {analysisTypeLabel(type)}
                      </button>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>

          <Button
            onClick={() => startAnalysis.mutate({ types: Array.from(selectedTypes), model: selectedModel })}
            disabled={selectedTypes.size === 0 || startAnalysis.isPending}
            loading={startAnalysis.isPending}
            className="w-full"
          >
            <Play className="w-4 h-4" />
            Generar {selectedTypes.size} análisis
          </Button>
        </CardBody>
      </Card>

      {/* Results */}
      {project.analyses.length > 0 && (
        <div className="space-y-3">
          {project.analyses.map((analysis) => (
            <Card key={analysis.id}>
              <button
                className="w-full px-6 py-4 flex items-center justify-between hover:bg-slate-700/20 transition-colors rounded-xl"
                onClick={() => toggleExpand(analysis.analysis_type)}
              >
                <div className="flex items-center gap-3">
                  <span className="font-medium text-white text-sm">
                    {analysisTypeLabel(analysis.analysis_type)}
                  </span>
                  {analysis.processing_time && (
                    <span className="text-xs text-slate-500">{analysis.processing_time.toFixed(1)}s</span>
                  )}
                  {analysis.error_message && (
                    <span className="text-xs text-red-400">Error</span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {analysis.content && (
                    <button
                      onClick={(e) => { e.stopPropagation(); copyToClipboard(analysis.content!, analysis.id) }}
                      className="p-1.5 rounded-lg hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
                    >
                      {copiedId === analysis.id ? <Check className="w-3.5 h-3.5 text-green-400" /> : <Copy className="w-3.5 h-3.5" />}
                    </button>
                  )}
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      runSingle.mutate({ type: analysis.analysis_type as AnalysisType, model: selectedModel })
                    }}
                    className="p-1.5 rounded-lg hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
                  >
                    <RefreshCw className="w-3.5 h-3.5" />
                  </button>
                  {expandedTypes.has(analysis.analysis_type) ? (
                    <ChevronUp className="w-4 h-4 text-slate-400" />
                  ) : (
                    <ChevronDown className="w-4 h-4 text-slate-400" />
                  )}
                </div>
              </button>

              {expandedTypes.has(analysis.analysis_type) && (
                <div className="px-6 pb-5 border-t border-slate-700/50">
                  {analysis.error_message ? (
                    <p className="text-red-400 text-sm mt-4">{analysis.error_message}</p>
                  ) : analysis.content ? (
                    <div className="prose prose-invert prose-sm max-w-none mt-4">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {analysis.content}
                      </ReactMarkdown>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2 text-slate-400 text-sm mt-4">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Generando...
                    </div>
                  )}
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
