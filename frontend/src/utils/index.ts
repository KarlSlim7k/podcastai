import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return '--:--'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

export function formatFileSize(bytes: number | null | undefined): string {
  if (bytes == null) return '--'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

export function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString('es-ES', {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

export function formatRelativeDate(dateStr: string): string {
  const now = new Date()
  const date = new Date(dateStr)
  const diff = now.getTime() - date.getTime()
  const mins = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)

  if (mins < 1) return 'ahora mismo'
  if (mins < 60) return `hace ${mins} min`
  if (hours < 24) return `hace ${hours} h`
  if (days < 7) return `hace ${days} días`
  return formatDate(dateStr)
}

export function analysisTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    executive_summary: 'Resumen Ejecutivo',
    main_topics: 'Temas Principales',
    key_ideas: 'Ideas Clave',
    action_items: 'Acciones Pendientes',
    important_questions: 'Preguntas Importantes',
    chapters: 'Capítulos',
    timeline: 'Timeline',
    learning_points: 'Puntos de Aprendizaje',
    facebook_post: 'Post Facebook',
    twitter_post: 'Post X/Twitter',
    linkedin_post: 'Post LinkedIn',
    blog_article: 'Artículo de Blog',
    youtube_description: 'Descripción YouTube',
    suggested_titles: 'Títulos Sugeridos',
    suggested_tags: 'Etiquetas Sugeridas',
    faq: 'FAQ',
    conclusions: 'Conclusiones',
    viral_moments: 'Momentos Virales',
    best_quotes: 'Mejores Frases',
    seo_timestamps: 'Capítulos con Timestamps',
  }
  return labels[type] ?? type
}

export function categoryLabel(category: string | null | undefined): string {
  if (!category) return ''
  const labels: Record<string, string> = {
    funny: 'Gracioso',
    insightful: 'Perspicaz',
    controversial: 'Controversial',
    emotional: 'Emocional',
    dramatic: 'Dramático',
    useful: 'Útil',
  }
  return labels[category] ?? category
}

export function categoryColor(category: string | null | undefined): string {
  const colors: Record<string, string> = {
    funny: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30',
    insightful: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
    controversial: 'bg-red-500/20 text-red-300 border-red-500/30',
    emotional: 'bg-pink-500/20 text-pink-300 border-pink-500/30',
    dramatic: 'bg-purple-500/20 text-purple-300 border-purple-500/30',
    useful: 'bg-green-500/20 text-green-300 border-green-500/30',
  }
  return colors[category ?? ''] ?? 'bg-slate-700/50 text-slate-300 border-slate-600/30'
}

export function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    created: 'Creado',
    uploading: 'Subiendo',
    extracting_audio: 'Extrayendo audio',
    transcribing: 'Transcribiendo',
    analyzing: 'Analizando',
    completed: 'Completado',
    error: 'Error',
    pending: 'Pendiente',
    processing: 'Procesando',
  }
  return labels[status] ?? status
}

export function statusColor(status: string): string {
  const colors: Record<string, string> = {
    created: 'text-slate-400',
    uploading: 'text-blue-400',
    extracting_audio: 'text-yellow-400',
    transcribing: 'text-purple-400',
    analyzing: 'text-indigo-400',
    completed: 'text-green-400',
    error: 'text-red-400',
    pending: 'text-slate-400',
    processing: 'text-blue-400',
  }
  return colors[status] ?? 'text-slate-400'
}
