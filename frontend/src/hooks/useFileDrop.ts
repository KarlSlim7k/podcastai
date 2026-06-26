import { useCallback, useState } from 'react'
import toast from 'react-hot-toast'

export type DroppedFileKind = 'image' | 'video' | 'audio' | 'unknown'

export interface FileDropOptions {
  onImageDrop?: (file: File) => void
  onVideoDrop?: (file: File) => void
  onAudioDrop?: (file: File) => void
}

export interface FileDropHandlers {
  dragProps: {
    onDragEnter: (e: React.DragEvent) => void
    onDragOver: (e: React.DragEvent) => void
    onDragLeave: (e: React.DragEvent) => void
    onDrop: (e: React.DragEvent) => void
  }
  isDragging: boolean
  draggedFileKind: DroppedFileKind
}

const IMAGE_MIME = ['image/png', 'image/jpeg', 'image/webp', 'image/svg+xml']
const VIDEO_MIME = ['video/mp4', 'video/quicktime', 'video/webm']
const AUDIO_MIME = ['audio/mpeg', 'audio/wav', 'audio/x-m4a']
const IMAGE_EXT = ['.png', '.jpg', '.jpeg', '.webp', '.svg']
const VIDEO_EXT = ['.mp4', '.mov', '.webm']
const AUDIO_EXT = ['.mp3', '.wav', '.m4a']

function extOf(name: string): string {
  const i = name.lastIndexOf('.')
  return i >= 0 ? name.slice(i).toLowerCase() : ''
}

/** Classify a dropped item, falling back to the filename extension since
 * `file.type` is empty for some formats/browsers. */
function classify(mime: string, name: string): DroppedFileKind {
  if (IMAGE_MIME.includes(mime) || IMAGE_EXT.includes(extOf(name))) return 'image'
  if (VIDEO_MIME.includes(mime) || VIDEO_EXT.includes(extOf(name))) return 'video'
  if (AUDIO_MIME.includes(mime) || AUDIO_EXT.includes(extOf(name))) return 'audio'
  return 'unknown'
}

const hasFiles = (e: React.DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes('Files')

/**
 * Whole-window drag & drop for the editor. Uses a dragenter/dragleave depth
 * counter rather than a boolean — the browser fires `dragleave` whenever the
 * pointer crosses into a child element, not just when it truly exits the
 * drop zone, so a plain boolean would flicker the overlay constantly.
 */
export function useFileDrop(options: FileDropOptions): FileDropHandlers {
  const [depth, setDepth] = useState(0)
  const [draggedFileKind, setDraggedFileKind] = useState<DroppedFileKind>('unknown')

  // Pre-drop, the browser only exposes `kind`/`type` (never the filename),
  // so this is a best-effort guess for the overlay copy — `type` itself can
  // be empty for some formats until the actual drop, in which case we fall
  // back to 'unknown' rather than guessing wrong.
  const peekKind = useCallback((e: React.DragEvent) => {
    const item = e.dataTransfer?.items?.[0]
    if (!item || item.kind !== 'file') return
    setDraggedFileKind(classify(item.type, ''))
  }, [])

  const onDragEnter = useCallback((e: React.DragEvent) => {
    if (!hasFiles(e)) return
    e.preventDefault()
    setDepth((d) => d + 1)
    peekKind(e)
  }, [peekKind])

  const onDragOver = useCallback((e: React.DragEvent) => {
    if (!hasFiles(e)) return
    e.preventDefault() // required for onDrop to fire
    peekKind(e)
  }, [peekKind])

  const onDragLeave = useCallback((e: React.DragEvent) => {
    if (!hasFiles(e)) return
    setDepth((d) => Math.max(0, d - 1))
  }, [])

  const onDrop = useCallback((e: React.DragEvent) => {
    if (!hasFiles(e)) return
    e.preventDefault()
    setDepth(0)
    const files = Array.from(e.dataTransfer?.files ?? [])
    if (files.length === 0) return
    if (files.length > 1) toast('Solo se procesó el primer archivo')
    const file = files[0]
    switch (classify(file.type, file.name)) {
      case 'image': options.onImageDrop?.(file); break
      case 'video': options.onVideoDrop?.(file); break
      case 'audio': options.onAudioDrop?.(file); break
      default: toast.error('Tipo de archivo no soportado')
    }
  }, [options])

  return {
    dragProps: { onDragEnter, onDragOver, onDragLeave, onDrop },
    isDragging: depth > 0,
    draggedFileKind,
  }
}
