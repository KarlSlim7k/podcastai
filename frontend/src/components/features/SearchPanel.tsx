import { useState, useMemo } from 'react'
import { Search, Clock, User, Filter, Loader2, ChevronDown, ChevronUp, FileText, ArrowRight } from 'lucide-react'
import { useTranscriptionSearch, useSpeakers } from '../../hooks/useProject'
import { Card, CardBody, CardHeader } from '../ui/Card'
import { cn, formatDuration } from '../../utils'
import type { Project, SearchHit } from '../../types'

interface SearchPanelProps {
  project: Project
}

export function SearchPanel({ project }: SearchPanelProps) {
  const [query, setQuery] = useState('')
  const [submittedQuery, setSubmittedQuery] = useState('')
  const [selectedSpeaker, setSelectedSpeaker] = useState<string | null>(null)
  const [expandedHit, setExpandedHit] = useState<number | null>(null)

  const hasTranscription = !!project.transcription?.text
  const speakersQuery = useSpeakers(project.id, hasTranscription)
  const speakers = speakersQuery.data?.speakers ?? []

  const searchQuery = useTranscriptionSearch(
    project.id,
    { q: submittedQuery, speaker: selectedSpeaker },
    hasTranscription && submittedQuery.length > 0
  )

  const handleSearch = (e?: React.FormEvent) => {
    e?.preventDefault()
    setSubmittedQuery(query.trim())
  }

  const handleSpeakerFilter = (speaker: string | null) => {
    setSelectedSpeaker(speaker === selectedSpeaker ? null : speaker)
  }

  // Group consecutive hits (within 30s) so the user can scan easier
  const groupedHits = useMemo(() => {
    if (!searchQuery.data?.hits) return []
    const hits = searchQuery.data.hits
    const groups: { hits: SearchHit[]; startSec: number; endSec: number }[] = []
    for (const h of hits) {
      const last = groups[groups.length - 1]
      if (last && h.start - last.endSec < 30) {
        last.hits.push(h)
        last.endSec = Math.max(last.endSec, h.end)
      } else {
        groups.push({ hits: [h], startSec: h.start, endSec: h.end })
      }
    }
    return groups
  }, [searchQuery.data])

  if (!hasTranscription) {
    return (
      <Card>
        <CardBody className="py-12 text-center">
          <Search className="w-12 h-12 text-slate-600 mx-auto mb-3" />
          <p className="text-slate-400">Transcribe el audio primero para habilitar la búsqueda</p>
        </CardBody>
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      {/* Search bar */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Search className="w-5 h-5 text-brand-400" />
            <h2 className="font-semibold text-white">Búsqueda en la transcripción</h2>
          </div>
        </CardHeader>
        <CardBody className="space-y-4">
          <form onSubmit={handleSearch} className="flex gap-2">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Buscar palabra o frase (ej: 'Red Bull', 'selección mexicana', 'gol')"
                className="w-full bg-slate-800 border border-slate-700 rounded-lg pl-10 pr-3 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-brand-500"
              />
            </div>
            <button
              type="submit"
              disabled={!query.trim() || searchQuery.isFetching}
              className="px-4 py-2.5 bg-brand-600 hover:bg-brand-700 disabled:bg-slate-700 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium transition-colors"
            >
              {searchQuery.isFetching ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Buscar'}
            </button>
          </form>

          {/* Speaker filter chips */}
          {speakers.length > 0 && (
            <div className="flex items-center gap-2 flex-wrap">
              <div className="flex items-center gap-1.5 text-xs text-slate-400">
                <Filter className="w-3.5 h-3.5" />
                <span>Filtrar por hablante:</span>
              </div>
              <button
                onClick={() => setSelectedSpeaker(null)}
                className={cn(
                  'px-2.5 py-1 rounded-md text-xs font-medium border transition-colors',
                  !selectedSpeaker
                    ? 'bg-brand-600/30 text-brand-200 border-brand-500/50'
                    : 'bg-slate-800/60 text-slate-400 border-slate-700/40 hover:text-slate-200'
                )}
              >
                Todos
              </button>
              {speakers.map((sp) => (
                <button
                  key={sp.speaker}
                  onClick={() => handleSpeakerFilter(sp.speaker)}
                  className={cn(
                    'px-2.5 py-1 rounded-md text-xs font-medium border transition-colors',
                    selectedSpeaker === sp.speaker
                      ? 'bg-brand-600/30 text-brand-200 border-brand-500/50'
                      : 'bg-slate-800/60 text-slate-400 border-slate-700/40 hover:text-slate-200'
                  )}
                >
                  {sp.speaker}
                </button>
              ))}
            </div>
          )}

          {searchQuery.data && (
            <div className="flex items-center justify-between text-xs text-slate-500 pt-1">
              <span>
                {searchQuery.data.total === 0
                  ? submittedQuery ? 'Sin resultados' : 'Introduce un término para buscar'
                  : `${searchQuery.data.total} resultado${searchQuery.data.total !== 1 ? 's' : ''} para "${searchQuery.data.query}"`}
              </span>
              {searchQuery.data.total > 0 && (
                <span className="flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  Tiempos en el video original
                </span>
              )}
            </div>
          )}
        </CardBody>
      </Card>

      {/* Results */}
      {searchQuery.isLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 text-brand-400 animate-spin" />
        </div>
      )}

      {groupedHits.length > 0 && (
        <div className="space-y-3">
          {groupedHits.map((group, gi) => {
            const isExpanded = expandedHit === gi
            return (
              <Card key={gi}>
                <button
                  onClick={() => setExpandedHit(isExpanded ? null : gi)}
                  className="w-full px-6 py-4 flex items-start gap-4 hover:bg-slate-700/10 transition-colors rounded-xl text-left"
                >
                  {/* Time range pill */}
                  <div className="flex-shrink-0 w-24 pt-0.5">
                    <div className="bg-brand-600/20 border border-brand-500/30 rounded-md px-2 py-1.5 text-center">
                      <div className="text-[10px] uppercase tracking-wide text-brand-300/80">Tiempo</div>
                      <div className="text-xs font-mono text-brand-200 font-medium">
                        {formatDuration(group.startSec)}
                      </div>
                      <div className="text-[10px] text-slate-500">→ {formatDuration(group.endSec)}</div>
                    </div>
                  </div>

                  {/* Hit content */}
                  <div className="flex-1 min-w-0">
                    {group.hits.map((h, hi) => (
                      <div key={hi} className={cn(hi > 0 && 'mt-2 pt-2 border-t border-slate-700/40')}>
                        <p className="text-sm text-slate-200 leading-relaxed">
                          {h.context_before && (
                            <span className="text-slate-500">...{h.context_before} </span>
                          )}
                          <HighlightedText text={h.text} query={submittedQuery} />
                          {h.context_after && (
                            <span className="text-slate-500"> {h.context_after}...</span>
                          )}
                        </p>
                        <div className="flex items-center gap-3 mt-1.5 text-xs text-slate-500">
                          {h.speaker && (
                            <span className="flex items-center gap-1">
                              <User className="w-3 h-3" />
                              {h.speaker}
                            </span>
                          )}
                          <span className="flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            {formatDuration(h.start)} → {formatDuration(h.end)}
                          </span>
                        </div>
                      </div>
                    ))}
                    {group.hits.length > 1 && (
                      <p className="text-xs text-slate-500 mt-2">
                        {group.hits.length} segmentos consecutivos
                      </p>
                    )}
                  </div>

                  {/* Expand button */}
                  <div className="flex-shrink-0 pt-1">
                    {isExpanded ? (
                      <ChevronUp className="w-4 h-4 text-slate-400" />
                    ) : (
                      <ChevronDown className="w-4 h-4 text-slate-400" />
                    )}
                  </div>
                </button>

                {isExpanded && (
                  <div className="px-6 pb-5 border-t border-slate-700/50">
                    <div className="mt-4 space-y-3">
                      <div className="bg-slate-900/60 rounded-lg p-3">
                        <p className="text-xs text-slate-400 mb-2">Transcripción completa en este rango:</p>
                        <p className="text-sm text-slate-200 leading-relaxed">
                          {group.hits.map((h) => h.text).join(' ')}
                        </p>
                      </div>
                      <div className="flex items-center gap-2 text-xs text-slate-500">
                        <ArrowRight className="w-3 h-3" />
                        <span>
                          Abre el video en <span className="text-brand-300 font-mono">{formatDuration(group.startSec)}</span>
                          {' '}para saltar a este momento
                        </span>
                      </div>
                    </div>
                  </div>
                )}
              </Card>
            )
          })}
        </div>
      )}

      {searchQuery.data && searchQuery.data.total === 0 && submittedQuery && !searchQuery.isLoading && (
        <Card>
          <CardBody className="py-12 text-center">
            <FileText className="w-12 h-12 text-slate-600 mx-auto mb-3" />
            <p className="text-slate-400">No encontramos "{submittedQuery}" en la transcripción</p>
            <p className="text-xs text-slate-500 mt-2">Prueba con otra palabra o revisa la ortografía</p>
          </CardBody>
        </Card>
      )}
    </div>
  )
}

function HighlightedText({ text, query }: { text: string; query: string }) {
  if (!query.trim()) return <>{text}</>
  try {
    // Highlight all words from the query (case-insensitive)
    const words = query.trim().split(/\s+/).filter(w => w.length > 0)
    if (words.length === 0) return <>{text}</>
    const escaped = words.map(w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')
    const re = new RegExp(`(${escaped})`, 'gi')
    const parts = text.split(re)
    return (
      <>
        {parts.map((part, i) =>
          re.test(part) ? (
            <mark key={i} className="bg-yellow-500/30 text-yellow-200 px-0.5 rounded">
              {part}
            </mark>
          ) : (
            <span key={i}>{part}</span>
          )
        )}
      </>
    )
  } catch {
    return <>{text}</>
  }
}
