import { useEffect } from 'react'

export interface EditorShortcutHandlers {
  onPlayPause?: () => void
  onStepSecond?: (dir: 1 | -1) => void
  onStepFrame?: (dir: 1 | -1) => void
  onSplit?: () => void
  onToggleTrim?: () => void
  onFit?: () => void
  onZoom?: (dir: 1 | -1) => void
  onPlayheadZero?: () => void
  onUndo?: () => void
  onRedo?: () => void
  onShowHelp?: () => void
  onEscape?: () => void
  enabled?: boolean
  /** When a full-screen modal (shortcuts help, save preset) is open, it owns
   * the keyboard — every shortcut below is suppressed except Escape. */
  modalOpen?: boolean
}

function isTypingTarget(el: EventTarget | null): boolean {
  const node = el as HTMLElement | null
  if (!node) return false
  const tag = node.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || node.isContentEditable
}

/**
 * Global keyboard shortcuts for the editor. Most shortcuts are suppressed
 * while the user is typing in a field; Esc and undo/redo always work, and the
 * help modal opens on `?`.
 */
export function useEditorShortcuts(h: EditorShortcutHandlers) {
  const { enabled = true } = h
  useEffect(() => {
    if (!enabled) return
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey
      const typing = isTypingTarget(e.target)

      // Always-available: Esc. Everything else is owned by the modal while open.
      if (e.key === 'Escape') { h.onEscape?.(); return }
      if (h.modalOpen) return

      if (mod && (e.key === 'z' || e.key === 'Z')) {
        e.preventDefault()
        if (e.shiftKey) h.onRedo?.(); else h.onUndo?.()
        return
      }
      if (mod && (e.key === 'y' || e.key === 'Y')) { e.preventDefault(); h.onRedo?.(); return }

      // Split: Ctrl/Cmd+K works even with the toolbar focused.
      if (mod && (e.key === 'k' || e.key === 'K')) { e.preventDefault(); h.onSplit?.(); return }

      if (typing) return  // the rest are single-key and must not fire mid-typing
      if (mod) return     // leave other browser combos (copy/paste/etc) alone

      switch (e.key) {
        case ' ':
        case 'k': case 'K': e.preventDefault(); h.onPlayPause?.(); break
        case 'l': case 'L': case 'ArrowRight': e.preventDefault(); h.onStepSecond?.(1); break
        case 'j': case 'J': case 'ArrowLeft': e.preventDefault(); h.onStepSecond?.(-1); break
        case '.': e.preventDefault(); h.onStepFrame?.(1); break
        case ',': e.preventDefault(); h.onStepFrame?.(-1); break
        case 's': case 'S': e.preventDefault(); h.onSplit?.(); break
        case 't': case 'T': h.onToggleTrim?.(); break
        case 'z': case 'Z': h.onFit?.(); break
        case '1': h.onZoom?.(1); break
        case '2': h.onZoom?.(-1); break
        case '0': h.onPlayheadZero?.(); break
        case '?': h.onShowHelp?.(); break
        case '/': if (e.shiftKey) h.onShowHelp?.(); break
        default: break
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [h, enabled])
}

/** Single source of truth for the shortcut list (used by the help modal). */
export const SHORTCUT_GROUPS: { title: string; items: [string, string][] }[] = [
  {
    title: 'Reproducción',
    items: [
      ['Space / K', 'Play / pausa'],
      ['J / L', 'Retroceder / avanzar 1s'],
      ['← / →', 'Retroceder / avanzar 1s'],
      [', / .', 'Retroceder / avanzar 1 frame'],
      ['0', 'Ir al inicio'],
    ],
  },
  {
    title: 'Edición',
    items: [
      ['S  ·  Ctrl/⌘+K', 'Cortar B-roll en el cursor'],
      ['T', 'Modo recorte'],
      ['Supr / ⌫', 'Eliminar B-roll seleccionado'],
      ['Ctrl/⌘+Z', 'Deshacer'],
      ['Ctrl/⌘+Shift+Z', 'Rehacer'],
    ],
  },
  {
    title: 'Timeline',
    items: [
      ['Z', 'Ajustar a la pantalla'],
      ['1 / 2', 'Acercar / alejar'],
      ['? ', 'Ver atajos'],
      ['Esc', 'Cerrar diálogos'],
    ],
  },
]
