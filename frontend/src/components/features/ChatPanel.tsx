import { useState, useRef, useEffect } from 'react'
import { MessageCircle, Send, Loader2, Trash2, Bot, User } from 'lucide-react'
import { useChatHistory, useSendMessage } from '../../hooks/useProject'
import { Button } from '../ui/Button'
import { Card, CardHeader, CardBody } from '../ui/Card'
import { cn, formatRelativeDate } from '../../utils'
import type { Project, OllamaModel } from '../../types'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { chatApi } from '../../services/api'
import { useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'

const SUGGESTIONS = [
  '¿Cuál es el tema principal del contenido?',
  '¿Qué puntos clave se mencionaron?',
  '¿Cuáles son las conclusiones principales?',
  '¿Se mencionaron fechas o números importantes?',
]

interface ChatPanelProps {
  project: Project
  models: OllamaModel[]
}

export function ChatPanel({ project, models }: ChatPanelProps) {
  const [message, setMessage] = useState('')
  const [model, setModel] = useState(models[0]?.name ?? 'qwen3:14b')
  const [isTyping, setIsTyping] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const qc = useQueryClient()

  const { data: history = [], isLoading } = useChatHistory(project.id)
  const sendMessage = useSendMessage(project.id)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [history, isTyping])

  const handleSend = async () => {
    const text = message.trim()
    if (!text || sendMessage.isPending) return
    setMessage('')
    setIsTyping(true)
    try {
      await sendMessage.mutateAsync({ message: text, model })
    } finally {
      setIsTyping(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleClear = async () => {
    await chatApi.clear(project.id)
    qc.invalidateQueries({ queryKey: ['chat-history', project.id] })
    toast.success('Historial eliminado')
  }

  const hasTranscription = !!project.transcription?.text

  if (!hasTranscription) {
    return (
      <Card>
        <CardBody className="py-12 text-center">
          <MessageCircle className="w-12 h-12 text-slate-600 mx-auto mb-3" />
          <p className="text-slate-400">Transcribe el audio primero para habilitar el chat</p>
        </CardBody>
      </Card>
    )
  }

  return (
    <Card className="flex flex-col h-[700px]">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <MessageCircle className="w-5 h-5 text-brand-400" />
            <h2 className="font-semibold text-white">Chat con la transcripción</h2>
            <span className="text-xs text-slate-500 bg-slate-800 px-2 py-0.5 rounded-full">RAG local</span>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="bg-slate-800 border border-slate-700 rounded-lg px-2 py-1 text-xs text-white"
            >
              {models.length > 0 ? models.map(m => (
                <option key={m.name} value={m.name}>{m.name}</option>
              )) : (
                <>
                  <option value="qwen3:14b">qwen3:14b</option>
                  <option value="qwen3:8b">qwen3:8b</option>
                </>
              )}
            </select>
            {history.length > 0 && (
              <button onClick={handleClear} className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-500 hover:text-red-400 transition-colors">
                <Trash2 className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      </CardHeader>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {isLoading && (
          <div className="flex justify-center py-8">
            <Loader2 className="w-6 h-6 animate-spin text-brand-400" />
          </div>
        )}

        {!isLoading && history.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center gap-4">
            <Bot className="w-16 h-16 text-slate-700" />
            <p className="text-slate-400 text-sm text-center max-w-xs">
              Pregunta cualquier cosa sobre el contenido transcrito.
              Las respuestas se basarán exclusivamente en la transcripción.
            </p>
            <div className="grid grid-cols-1 gap-2 w-full max-w-sm">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => setMessage(s)}
                  className="text-left px-4 py-2.5 rounded-xl bg-slate-800/60 border border-slate-700/50 text-sm text-slate-300 hover:text-white hover:bg-slate-700/60 transition-all"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {history.map((msg) => (
          <div key={msg.id} className={cn('flex gap-3', msg.role === 'user' ? 'justify-end' : 'justify-start')}>
            {msg.role === 'assistant' && (
              <div className="w-8 h-8 rounded-full bg-brand-600/20 border border-brand-600/30 flex items-center justify-center flex-shrink-0 mt-1">
                <Bot className="w-4 h-4 text-brand-400" />
              </div>
            )}
            <div className={cn(
              'max-w-[80%] rounded-2xl px-4 py-3 text-sm',
              msg.role === 'user'
                ? 'bg-brand-600/20 border border-brand-600/30 text-white rounded-br-sm'
                : 'bg-slate-800/80 border border-slate-700/50 text-slate-200 rounded-bl-sm'
            )}>
              {msg.role === 'assistant' ? (
                <div className="prose prose-invert prose-sm max-w-none">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                </div>
              ) : (
                <p>{msg.content}</p>
              )}
              <p className="text-xs text-slate-500 mt-1.5">{formatRelativeDate(msg.created_at)}</p>
            </div>
            {msg.role === 'user' && (
              <div className="w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center flex-shrink-0 mt-1">
                <User className="w-4 h-4 text-slate-400" />
              </div>
            )}
          </div>
        ))}

        {isTyping && (
          <div className="flex gap-3 justify-start">
            <div className="w-8 h-8 rounded-full bg-brand-600/20 border border-brand-600/30 flex items-center justify-center">
              <Bot className="w-4 h-4 text-brand-400" />
            </div>
            <div className="bg-slate-800/80 border border-slate-700/50 rounded-2xl rounded-bl-sm px-4 py-3">
              <div className="flex gap-1">
                {[0, 1, 2].map(i => (
                  <div key={i} className="w-2 h-2 rounded-full bg-brand-400 animate-bounce"
                    style={{ animationDelay: `${i * 0.15}s` }} />
                ))}
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="px-6 py-4 border-t border-slate-700/50">
        <div className="flex gap-3 items-end">
          <textarea
            ref={inputRef}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Pregunta sobre el contenido... (Enter para enviar)"
            rows={1}
            className="flex-1 bg-slate-800 border border-slate-700 rounded-xl px-4 py-3 text-sm text-white placeholder-slate-500 resize-none focus:outline-none focus:border-brand-500 transition-colors"
            style={{ minHeight: '44px', maxHeight: '120px' }}
            onInput={(e) => {
              const t = e.currentTarget
              t.style.height = 'auto'
              t.style.height = `${Math.min(t.scrollHeight, 120)}px`
            }}
          />
          <Button
            onClick={handleSend}
            disabled={!message.trim() || sendMessage.isPending}
            loading={sendMessage.isPending}
            size="md"
            className="flex-shrink-0"
          >
            <Send className="w-4 h-4" />
          </Button>
        </div>
      </div>
    </Card>
  )
}
