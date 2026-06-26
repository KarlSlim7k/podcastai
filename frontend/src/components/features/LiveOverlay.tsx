import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { useSyncPlayhead } from '../../hooks/useSyncPlayhead'
import { watermarkApi } from '../../services/api'
import type { CaptionWord, VerticalSubStyle, VerticalTitlePosition, WatermarkPosition } from '../../types'

// Pixel constants mirrored from vertical_editor_service.py so the overlay
// lines up with what ffmpeg actually draws (PlayResX=1080, PlayResY=1920).
const FRAME_W = 1080
const TITLE_TOP_Y = 140
const TITLE_BOTTOM_MARGIN = 220
const WM_SIZE = 270
const WM_MARGIN = 60
const KARAOKE_CHUNK = 5

// Styles that get the word-by-word "growing highlight" treatment server-side
// (see WORD_BY_WORD_STYLES in vertical_editor_service.py). 'standard' is the
// only style rendered as a static line.
const WORD_BY_WORD_STYLES = new Set<VerticalSubStyle>(['karaoke', 'mrbeast', 'hormozi', 'tiktok_classic', 'neon'])

// mrbeast/tiktok_classic hardcode their active-word color server-side
// regardless of sub_highlight; the rest use the user's highlight color.
const FORCED_ACTIVE_COLOR: Partial<Record<VerticalSubStyle, string>> = {
  mrbeast: '#FF0000',
  tiktok_classic: '#FFFF00',
}

const WATERMARK_STYLE: Record<WatermarkPosition, (m: number) => CSSProperties> = {
  top_left: (m) => ({ top: m, left: m }),
  top_center: (m) => ({ top: m, left: '50%', transform: 'translateX(-50%)' }),
  top_right: (m) => ({ top: m, right: m }),
  center_left: (m) => ({ top: '50%', left: m, transform: 'translateY(-50%)' }),
  center: (m) => ({ top: '50%', left: '50%', transform: 'translate(-50%, -50%)' }),
  center_right: (m) => ({ top: '50%', right: m, transform: 'translateY(-50%)' }),
  bottom_left: (m) => ({ bottom: m, left: m }),
  bottom_center: (m) => ({ bottom: m, left: '50%', transform: 'translateX(-50%)' }),
  bottom_right: (m) => ({ bottom: m, right: m }),
}

export interface LiveOverlayProps {
  videoRef: React.RefObject<HTMLVideoElement>
  words?: CaptionWord[]
  subStyle: VerticalSubStyle
  subColor: string
  subOutline: string
  subHighlight: string
  subSize: number
  subPosition: number
  addTitle: boolean
  titleText: string
  titleColor: string
  titleSize: number
  titlePosition: VerticalTitlePosition
  watermarkFileId: string | null
  watermarkPosition: WatermarkPosition
  watermarkOpacity: number
}

interface WordSeg { text: string; active: boolean }

/**
 * Instant CSS approximation of subtitles/title/watermark, layered over the
 * draft <video> so style/color/position edits show with zero ffmpeg
 * round-trip. Tracks the video's currentTime itself (own RAF loop via
 * useSyncPlayhead) so a frame tick never re-renders the rest of the editor.
 */
export function LiveOverlay({
  videoRef, words, subStyle, subColor, subOutline, subHighlight, subSize, subPosition,
  addTitle, titleText, titleColor, titleSize, titlePosition,
  watermarkFileId, watermarkPosition, watermarkOpacity,
}: LiveOverlayProps) {
  const rootRef = useRef<HTMLDivElement>(null)
  const [boxW, setBoxW] = useState(0)
  const [time, setTime] = useState(0)
  useSyncPlayhead(videoRef, setTime)

  useEffect(() => {
    const el = rootRef.current
    if (!el) return
    const ro = new ResizeObserver((entries) => setBoxW(entries[0].contentRect.width))
    ro.observe(el)
    setBoxW(el.getBoundingClientRect().width)
    return () => ro.disconnect()
  }, [])

  const scale = boxW ? boxW / FRAME_W : 0
  const line = scale ? buildActiveLine(words ?? [], time, subStyle) : null

  return (
    <div ref={rootRef} className="absolute inset-0 pointer-events-none z-20 overflow-hidden">
      {line && (
        <div
          className="absolute text-center leading-tight"
          style={{
            bottom: subPosition * scale,
            left: '50%',
            transform: 'translateX(-50%)',
            fontSize: subSize * scale,
            maxWidth: boxW * 0.92,
            fontWeight: 700,
            WebkitTextStroke: `${Math.max(1, subSize * scale * 0.035)}px ${subOutline}`,
            paintOrder: 'stroke fill',
          } as CSSProperties}
        >
          {line.map((seg, i) => (
            <span key={i} style={{ color: seg.active ? (FORCED_ACTIVE_COLOR[subStyle] ?? subHighlight) : subColor }}>
              {seg.text}{i < line.length - 1 ? ' ' : ''}
            </span>
          ))}
        </div>
      )}

      {addTitle && titleText && (
        <div
          className="absolute text-center whitespace-pre-wrap rounded"
          style={{
            ...titleAnchorStyle(titlePosition, scale),
            fontSize: titleSize * scale,
            color: titleColor,
            fontWeight: 700,
            background: 'rgba(0,0,0,0.55)',
            padding: `${4 * scale}px ${24 * scale}px`,
            maxWidth: boxW * 0.92,
          }}
        >
          {titleText}
        </div>
      )}

      {watermarkFileId && (
        <img
          src={watermarkApi.fileUrl(watermarkFileId)}
          alt=""
          className="absolute object-contain"
          style={{ ...WATERMARK_STYLE[watermarkPosition](WM_MARGIN * scale), width: WM_SIZE * scale, opacity: watermarkOpacity }}
        />
      )}
    </div>
  )
}

function titleAnchorStyle(pos: VerticalTitlePosition, scale: number): CSSProperties {
  if (pos === 'center') return { top: '50%', left: '50%', transform: 'translate(-50%, -50%)' }
  if (pos === 'bottom') return { bottom: TITLE_BOTTOM_MARGIN * scale, left: '50%', transform: 'translateX(-50%)' }
  return { top: TITLE_TOP_Y * scale, left: '50%', transform: 'translateX(-50%)' }
}

/** Group words into karaoke-sized chunks (5) or sentence/line-broken groups, matching the backend, and return the chunk/line covering `t` (with a small trailing grace window). */
function buildActiveLine(words: CaptionWord[], t: number, subStyle: VerticalSubStyle): WordSeg[] | null {
  if (words.length === 0) return null
  if (WORD_BY_WORD_STYLES.has(subStyle)) {
    for (let i = 0; i < words.length; i += KARAOKE_CHUNK) {
      const chunk = words.slice(i, i + KARAOKE_CHUNK)
      const start = chunk[0].start
      const end = chunk[chunk.length - 1].end
      if (t < start - 0.05 || t > end + 0.4) continue
      let activeIdx = -1
      chunk.forEach((w, idx) => { if (t >= w.start) activeIdx = idx })
      return chunk.map((w, idx) => ({ text: w.word, active: idx <= activeIdx }))
    }
    return null
  }
  const line = groupIntoLines(words).find((l) => t >= l[0].start - 0.05 && t <= l[l.length - 1].end + 0.4)
  return line ? line.map((w) => ({ text: w.word, active: false })) : null
}

function groupIntoLines(words: CaptionWord[]): CaptionWord[][] {
  const lines: CaptionWord[][] = []
  let cur: CaptionWord[] = []
  let lineStart = words[0]?.start ?? 0
  const flush = () => { if (cur.length) lines.push(cur); cur = [] }
  for (const w of words) {
    if (cur.length && /[.!?…]$/.test(cur[cur.length - 1].word)) { flush(); lineStart = w.start }
    if (cur.length && (cur.length >= 6 || w.end - lineStart > 3.5)) { flush(); lineStart = w.start }
    cur.push(w)
  }
  flush()
  return lines
}
