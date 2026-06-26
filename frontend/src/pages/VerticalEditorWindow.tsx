import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { X, Loader2, Square, Save, Smartphone, HelpCircle, Undo2, Redo2, Upload } from 'lucide-react'
import toast, { Toaster } from 'react-hot-toast'
import {
  useClip, useProject,
  useVerticalStyles, useVerticalRenders, useCreateVerticalRender, useDeleteVerticalRender,
  useVerticalPresets, useCreateVerticalPreset, useDeleteVerticalPreset, useUploadWatermark,
  useDraftPreview, useTrimClip, useClipCaptions, useSaveClipCaptions, useBatchCreateVerticalRender,
} from '../hooks/useProject'
import { useResizablePanel } from '../hooks/useResizablePanel'
import { useUndoRedo } from '../hooks/useUndoRedo'
import { useAutoSave } from '../hooks/useAutoSave'
import { useEditorShortcuts } from '../hooks/useEditorShortcuts'
import { useFileDrop } from '../hooks/useFileDrop'
import { verticalApi } from '../services/api'
import { Button } from '../components/ui/Button'
import { TimeLineV2, type TimeLineV2Handle } from '../components/features/TimeLineV2'
import { EditorPreview } from '../components/features/EditorPreview'
import { EditorRightPanel, type EditorRightPanelHandle } from '../components/features/EditorRightPanel'
import { EditorLeftSidebar } from '../components/features/EditorLeftSidebar'
import { ShortcutsModal } from '../components/features/ShortcutsModal'
import { SaveIndicator } from '../components/features/SaveIndicator'
import { cn, formatDuration } from '../utils'
import { IDENTITY_TRANSFORM, isIdentityTransform } from '../types'
import type {
  VerticalLayout, VerticalBgStyle, VerticalSubStyle, VerticalRender,
  VerticalRenderRequest, VerticalPreset, VerticalTitlePosition, WatermarkPosition,
  BrollPlacement, BrollSuggestion, VideoTransform,
} from '../types'

const clampNum = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))

/** Track the viewport width so the layout can adapt at breakpoints. */
function useWindowWidth() {
  const [w, setW] = useState(() => (typeof window !== 'undefined' ? window.innerWidth : 1440))
  useEffect(() => {
    const onResize = () => setW(window.innerWidth)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])
  return w
}

/**
 * Full-window vertical editor. Opened in a real browser popup via
 * window.open('/vertical-editor/:projectId/:clipId'). It's the same SPA
 * loaded at a dedicated URL, so it reuses the app's QueryClient.
 *
 * Layout (CapCut-style): compact header · workspace row [ left icon-rail
 * sidebar | centered fixed-height preview | tabbed right panel ] · a
 * full-width, drag-resizable multi-track timeline anchored at the bottom.
 */
export function VerticalEditorWindow() {
  const params = useParams<{ projectId: string; clipId: string }>()
  const projectId = Number(params.projectId)
  const clipId = Number(params.clipId)

  const clipQuery = useClip(projectId, clipId)
  const clip = clipQuery.data
  const projectQuery = useProject(projectId)

  const stylesQuery = useVerticalStyles()
  const rendersQuery = useVerticalRenders(projectId, clipId)
  const createRender = useCreateVerticalRender(projectId)
  const deleteRender = useDeleteVerticalRender(projectId)
  const presetsQuery = useVerticalPresets()
  const createPreset = useCreateVerticalPreset()
  const deletePreset = useDeleteVerticalPreset()
  const uploadWatermark = useUploadWatermark()
  const trimClip = useTrimClip(projectId)
  const draftMutation = useDraftPreview(projectId, clipId)
  const captionsQuery = useClipCaptions(projectId, clipId)
  const saveCaptions = useSaveClipCaptions(projectId)
  const styles = stylesQuery.data

  // Active <video> for timeline ↔ playhead sync (whichever preview is mounted).
  const activeVideoRef = useRef<HTMLVideoElement>(null)

  // ── Form state ──────────────────────────────────────────────────────────
  const [layout, setLayout] = useState<VerticalLayout>('split')
  const [bgStyle, setBgStyle] = useState<VerticalBgStyle>('blur')
  const [bgColor, setBgColor] = useState('#1a1a1a')
  const [bgColor2, setBgColor2] = useState('#16213e')
  const [subStyle, setSubStyle] = useState<VerticalSubStyle>('karaoke')
  const [subColor, setSubColor] = useState('#FFFFFF')
  const [subOutline, setSubOutline] = useState('#000000')
  const [subHighlight, setSubHighlight] = useState('#FFD700')
  const [subSize, setSubSize] = useState(64)
  const [subPosition, setSubPosition] = useState(200)
  const [addTitle, setAddTitle] = useState(true)
  const [titleText, setTitleText] = useState('')
  const [titleColor, setTitleColor] = useState('#FFFFFF')
  const [titleSize, setTitleSize] = useState(72)
  const [titlePosition, setTitlePosition] = useState<VerticalTitlePosition>('top')
  const [watermarkPath, setWatermarkPath] = useState<string | null>(null)
  const [watermarkFileId, setWatermarkFileId] = useState<string | null>(null)
  const [watermarkPosition, setWatermarkPosition] = useState<WatermarkPosition>('bottom_right')
  const [watermarkOpacity, setWatermarkOpacity] = useState(0.8)
  const [brollPlacements, setBrollPlacements] = useState<BrollPlacement[]>([])
  const [videoTransform, setVideoTransform] = useState<VideoTransform>(IDENTITY_TRANSFORM)
  const [transformMode, setTransformMode] = useState(false)
  const [showShortcuts, setShowShortcuts] = useState(false)

  const timelineRef = useRef<TimeLineV2Handle>(null)
  const rightPanelRef = useRef<EditorRightPanelHandle>(null)
  const batchRender = useBatchCreateVerticalRender(projectId)

  // Seed the title from the clip once it loads (without clobbering user edits).
  const seededRef = useRef(false)
  useEffect(() => {
    if (clip && !seededRef.current) {
      setTitleText(clip.title)
      setPendingStart(clip.start)
      setPendingEnd(clip.end)
      seededRef.current = true
    }
  }, [clip])

  // ── UI / layout state ─────────────────────────────────────────────────────
  const [showSavePreset, setShowSavePreset] = useState(false)
  const [presetName, setPresetName] = useState('')
  const [leftCollapsed, setLeftCollapsed] = useState(true)
  const vw = useWindowWidth()
  const narrow = vw < 800
  const rightWidthClass = vw < 1400 ? 'w-[280px]' : 'w-[320px]'
  const timeline = useResizablePanel({
    initialSize: 220, min: 100, max: () => Math.round(window.innerHeight * 0.5),
  })

  // ── Trim state ──────────────────────────────────────────────────────────────
  const [pendingStart, setPendingStart] = useState(0)
  const [pendingEnd, setPendingEnd] = useState(0)

  // ── Preview state ─────────────────────────────────────────────────────────
  const [previewRender, setPreviewRender] = useState<VerticalRender | null>(null)
  const [draftUrl, setDraftUrl] = useState<string | null>(null)
  const [draftError, setDraftError] = useState<string | null>(null)
  const [previewMode, setPreviewMode] = useState<'draft' | 'final'>('draft')
  const [compareMode, setCompareMode] = useState(false)
  // Bumped whenever the active video source changes so the timeline playhead
  // snaps back to 0 in lock-step with the freshly-mounted <video> (which always
  // starts at currentTime=0). Without this the playhead would linger at its old
  // position until the new video reports a frame.
  const [playheadResetSignal, setPlayheadResetSignal] = useState(0)

  const clipDuration = clip ? clip.end - clip.start : 0

  // Trim window: ±30s around the clip, clamped to the source audio length.
  const trimWindow = useMemo(() => {
    if (!clip) return { start: 0, end: 0 }
    const audioDuration = projectQuery.data?.audio_duration ?? clip.end + 30
    return { start: Math.max(0, clip.start - 30), end: Math.min(audioDuration, clip.end + 30) }
  }, [clip, projectQuery.data])

  // When a render completes, surface it in the final preview.
  useEffect(() => {
    if (!rendersQuery.data) return
    const completed = rendersQuery.data.find((r) => r.status === 'completed')
    if (completed && (!previewRender || completed.id !== previewRender.id)) {
      setPreviewRender(completed)
    }
  }, [rendersQuery.data])

  // CaptionEditor calls this after a save/reset; captions only show on a
  // re-render, so there's nothing to do here beyond letting drafts refresh.
  const onChangeForm = () => {}

  // ── Request builders ──────────────────────────────────────────────────────
  const baseRequest = (): VerticalRenderRequest => ({
    layout,
    bg_style: bgStyle,
    bg_color: bgColor,
    bg_color2: bgColor2,
    sub_style: subStyle,
    sub_color: subColor,
    sub_highlight: subHighlight,
    sub_outline: subOutline,
    sub_size: subSize,
    sub_position: subPosition,
    add_title: addTitle,
    title_text: titleText || null,
    title_color: titleColor,
    title_size: titleSize,
    title_position: titlePosition,
    watermark_path: null,
    watermark_position: watermarkPosition,
    watermark_opacity: watermarkOpacity,
    broll_placements: [],
    video_transform: isIdentityTransform(videoTransform) ? null : videoTransform,
  })

  const buildDraftRequest = (): VerticalRenderRequest => baseRequest()

  const buildFinalRequest = (): VerticalRenderRequest => ({
    ...baseRequest(),
    watermark_path: watermarkPath,
    broll_placements: brollPlacements,
  })

  // ── Live draft preview (debounced) ────────────────────────────────────────
  // Subtitle/title/watermark colors, size, and position are reflected
  // instantly via <LiveOverlay> (no ffmpeg round-trip). Only structural
  // changes — layout, background, sub style, and the video transform —
  // can't be approximated in CSS and still trigger a fast (800ms) draft
  // re-render. Overlay-only fields still eventually re-sync the draft so
  // its baked-in subtitles don't drift forever from the overlay, but on a
  // much longer (2.5s) debounce so it never feels like a wait.
  const [overlaySyncing, setOverlaySyncing] = useState(false)

  const fireDraft = () => {
    setDraftError(null)
    draftMutation.mutate(buildDraftRequest(), {
      onSuccess: (blob) => {
        const newUrl = URL.createObjectURL(blob)
        setDraftUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return newUrl })
        setOverlaySyncing(false)
      },
      onError: (e: Error) => setDraftError(e.message || 'Error al generar preview'),
    })
  }

  useEffect(() => {
    if (!draftUrl) return // don't auto-fire before the user generates the first preview
    const timer = setTimeout(fireDraft, 800)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layout, bgStyle, bgColor, bgColor2, subStyle, videoTransform])

  useEffect(() => {
    if (!draftUrl) return
    setOverlaySyncing(true)
    const timer = setTimeout(fireDraft, 2500)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    subColor, subOutline, subHighlight, subSize, subPosition,
    addTitle, titleText, titleColor, titleSize, titlePosition,
    watermarkOpacity, watermarkPosition,
  ])

  // Revoke the blob URL on unmount.
  useEffect(() => () => { setDraftUrl((p) => { if (p) URL.revokeObjectURL(p); return null }) }, [])

  // ── B-roll handlers ───────────────────────────────────────────────────────
  const addBrollFromSuggestion = (s: BrollSuggestion) => {
    if (brollPlacements.some((p) => p.url === s.full_url)) return
    setBrollPlacements((prev) => [...prev, { url: s.full_url, start: 0, end: Math.min(3, clipDuration), opacity: 1.0 }])
    toast.success('B-roll añadido · ajusta su tiempo en la timeline')
  }
  const updateBrollPlacement = (idx: number, patch: Partial<BrollPlacement>) =>
    setBrollPlacements((prev) => prev.map((p, i) => (i === idx ? { ...p, ...patch } : p)))
  const removeBrollPlacement = (idx: number) =>
    setBrollPlacements((prev) => prev.filter((_, i) => i !== idx))
  const isSuggestionAdded = (s: BrollSuggestion) => brollPlacements.some((p) => p.url === s.full_url)

  // Split the b-roll at `idx` into two pieces at clip-relative time `at`.
  const splitBrollPlacement = (idx: number, at: number) => {
    const before = brollPlacements
    setBrollPlacements((prev) => {
      const b = prev[idx]
      if (!b) return prev
      const copy = [...prev]
      copy.splice(idx, 1, { ...b, end: at }, { ...b, start: at })
      return copy
    })
    toast((t) => (
      <span className="flex items-center gap-3 text-sm">
        B-roll cortado en {at.toFixed(1)}s
        <button className="text-brand-300 underline" onClick={() => { setBrollPlacements(before); toast.dismiss(t.id) }}>
          Deshacer
        </button>
      </span>
    ))
  }
  const duplicateBrollPlacement = (idx: number) => {
    setBrollPlacements((prev) => {
      const b = prev[idx]
      if (!b) return prev
      const dur = b.end - b.start
      const ns = Math.min(b.start + 0.1, Math.max(0, clipDuration - dur))
      const copy = [...prev]
      copy.splice(idx + 1, 0, { ...b, start: ns, end: ns + dur })
      return copy
    })
    toast.success('B-roll duplicado')
  }

  // ── Render / preset / watermark ───────────────────────────────────────────
  const handleRender = () => createRender.mutate({ clipId, request: buildFinalRequest() }, {
    onSuccess: () => { autosave.clear(); baselineRef.current = JSON.stringify(snapshotRef.current) },
  })

  const applyPreset = (p: VerticalPreset) => {
    setLayout(p.layout); setBgStyle(p.bg_style); setBgColor(p.bg_color); setBgColor2(p.bg_color2 || '#16213e')
    setSubStyle(p.sub_style); setSubColor(p.sub_color); setSubOutline(p.sub_outline || '#000000')
    setSubHighlight(p.sub_highlight); setSubSize(p.sub_size); setSubPosition(p.sub_position)
    setAddTitle(!!p.add_title); setTitleText(p.title_text || (clip?.title ?? ''))
    setTitleColor(p.title_color); setTitleSize(p.title_size); setTitlePosition(p.title_position || 'top')
    if (p.watermark_path) setWatermarkPath(p.watermark_path)
    if (p.watermark_position) setWatermarkPosition(p.watermark_position as WatermarkPosition)
    if (p.watermark_opacity != null) setWatermarkOpacity(p.watermark_opacity)
    toast.success(`Preset "${p.name}" aplicado`)
  }

  const handleSavePreset = () => {
    const name = presetName.trim()
    if (!name) return
    createPreset.mutate({
      name, description: null,
      layout, bg_style: bgStyle, bg_color: bgColor, bg_color2: bgColor2,
      sub_style: subStyle, sub_color: subColor, sub_highlight: subHighlight,
      sub_outline: subOutline, sub_size: subSize, sub_position: subPosition,
      add_title: addTitle ? 1 : 0, title_text: titleText, title_color: titleColor,
      title_size: titleSize, title_position: titlePosition, watermark_path: watermarkPath,
      watermark_position: watermarkPosition, watermark_opacity: watermarkOpacity,
    }, { onSuccess: () => { setShowSavePreset(false); setPresetName('') } })
  }

  const handleWatermarkUpload = async (file: File) => {
    const res = await uploadWatermark.mutateAsync(file)
    setWatermarkPath(res.path); setWatermarkFileId(res.file_id)
    toast.success('Watermark subido')
  }
  const handleWatermarkRemove = () => {
    setWatermarkPath(null); setWatermarkFileId(null)
    toast('Marca de agua eliminada', { icon: '🗑️' })
  }

  // Fired once when a transform drag gesture ends (not on every frame).
  const handleTransformCommit = () => {
    if (!isIdentityTransform(videoTransform)) {
      toast('Transform aplicado · renderiza para ver el video final', { icon: '↔️' })
    }
  }
  const handleResetTransform = () => {
    setVideoTransform(IDENTITY_TRANSFORM)
    toast('Transform reiniciado')
  }

  // ── Drag & drop files onto the editor ─────────────────────────────────────
  // Images go straight to the watermark slot (the only place a dropped image
  // can be used today); if one is already set, ask before clobbering it.
  const handleImageDrop = (file: File) => {
    if (!watermarkPath) { void handleWatermarkUpload(file); return }
    toast((t) => (
      <span className="flex items-center gap-3 text-sm">
        ¿Reemplazar la marca de agua actual?
        <button className="text-brand-300 underline" onClick={() => { void handleWatermarkUpload(file); toast.dismiss(t.id) }}>
          Reemplazar
        </button>
        <button className="text-slate-400 underline" onClick={() => toast.dismiss(t.id)}>Cancelar</button>
      </span>
    ), { duration: 8000 })
  }
  const handleVideoDrop = () => toast('Próximamente: importar video como nuevo clip', { icon: 'ℹ️' })
  const handleAudioDrop = () => toast('Próximamente: importar audio', { icon: 'ℹ️' })
  const fileDrop = useFileDrop({
    onImageDrop: handleImageDrop,
    onVideoDrop: handleVideoDrop,
    onAudioDrop: handleAudioDrop,
  })

  // ── Trim handlers ─────────────────────────────────────────────────────────
  const trimChanged = clip
    ? Math.abs(pendingStart - clip.start) > 0.01 || Math.abs(pendingEnd - clip.end) > 0.01
    : false
  const handleApplyTrim = () => trimClip.mutate({ clipId, start: pendingStart, end: pendingEnd })

  // ── Caption word edits from the timeline inspector ──────────────────────────
  // The captions API only supports replacing the full word list, so patch the
  // cached words and save the whole array back.
  const handleUpdateCaptionWord = (index: number, patch: Partial<{ start: number; end: number; word: string }>) => {
    const words = captionsQuery.data?.words
    if (!words) return
    const next = words.map((w, i) => (i === index ? { ...w, ...patch } : w))
    saveCaptions.mutate({ clipId, words: next })
  }
  const handleDeleteCaptionWord = (index: number) => {
    const words = captionsQuery.data?.words
    if (!words) return
    saveCaptions.mutate({ clipId, words: words.filter((_, i) => i !== index) })
  }

  // ── Click-to-edit: timeline blocks drive the right panel ────────────────────
  const handleVideoTrackClick = () => {
    setTransformMode(true)
    rightPanelRef.current?.switchToTab('video')
  }
  const handleCaptionBlockClick = () => rightPanelRef.current?.focusSection('caption')
  const handleTitleBlockClick = () => rightPanelRef.current?.focusSection('title')

  const renders = rendersQuery.data ?? []
  const anyInProgress = renders.some((r) => r.status === 'pending' || r.status === 'processing')
  const previewUrl = previewRender
    ? verticalApi.downloadUrl(projectId, previewRender.id) + `?t=${previewRender.id}`
    : null

  // Reset playback + the timeline playhead whenever the on-screen video source
  // changes (new draft, new final render, or draft↔final toggle).
  useEffect(() => {
    const v = activeVideoRef.current
    if (v) v.currentTime = 0
    setPlayheadResetSignal((n) => n + 1)
  }, [draftUrl, previewUrl, previewMode])

  // Copy a previous render's settings back into the editor.
  const copyRenderSettings = (r: VerticalRender) => {
    setLayout(r.layout); setBgStyle(r.bg_style); setBgColor(r.bg_color); setBgColor2(r.bg_color2 || '#16213e')
    setSubStyle(r.sub_style); setSubColor(r.sub_color); setSubOutline(r.sub_outline || '#000000')
    setSubHighlight(r.sub_highlight); setSubSize(r.sub_size); setSubPosition(r.sub_position)
    setAddTitle(!!r.add_title); setTitleText(r.title_text || (clip?.title ?? ''))
    setTitleColor(r.title_color); setTitleSize(r.title_size); setTitlePosition(r.title_position || 'top')
    setBrollPlacements(r.broll_placements ?? [])
    setVideoTransform(r.video_transform ?? IDENTITY_TRANSFORM)
    toast.success(`Ajustes del render #${r.id} copiados`)
  }

  // Map a caption word's clip-relative start time to its speaker (if the
  // transcription was diarized). Segments are in absolute project seconds, so
  // shift by clip.start. Returns undefined entirely when there's no speaker
  // data — the timeline then renders no speaker badges.
  const transcriptionSegments = projectQuery.data?.transcription?.segments
  const speakerForClipTime = useMemo(() => {
    if (!clip || !transcriptionSegments?.some((s) => s.speaker)) return undefined
    const segs = transcriptionSegments.filter((s) => s.speaker)
    return (clipRelStart: number): string | null => {
      const abs = clip.start + clipRelStart
      for (const s of segs) {
        if (abs >= s.start && abs <= s.end) return s.speaker ?? null
      }
      return null
    }
  }, [clip, transcriptionSegments])

  const otherClips = projectQuery.data?.clips ?? []
  const applyToAllClips = () => {
    const ids = otherClips.map((c) => c.id)
    if (!ids.length) return
    batchRender.mutate({ clipIds: ids, request: buildFinalRequest() })
  }

  // ── Undo / redo over a snapshot of all tracked form state ───────────────────
  const snapshot = useMemo(() => ({
    layout, bgStyle, bgColor, bgColor2,
    subStyle, subColor, subOutline, subHighlight, subSize, subPosition,
    addTitle, titleText, titleColor, titleSize, titlePosition,
    watermarkPath, watermarkPosition, watermarkOpacity,
    brollPlacements, videoTransform, pendingStart, pendingEnd,
  }), [
    layout, bgStyle, bgColor, bgColor2, subStyle, subColor, subOutline, subHighlight,
    subSize, subPosition, addTitle, titleText, titleColor, titleSize, titlePosition,
    watermarkPath, watermarkPosition, watermarkOpacity, brollPlacements, videoTransform,
    pendingStart, pendingEnd,
  ])
  type Snapshot = typeof snapshot
  const applySnapshot = useCallback((s: Snapshot) => {
    setLayout(s.layout); setBgStyle(s.bgStyle); setBgColor(s.bgColor); setBgColor2(s.bgColor2)
    setSubStyle(s.subStyle); setSubColor(s.subColor); setSubOutline(s.subOutline); setSubHighlight(s.subHighlight)
    setSubSize(s.subSize); setSubPosition(s.subPosition)
    setAddTitle(s.addTitle); setTitleText(s.titleText); setTitleColor(s.titleColor)
    setTitleSize(s.titleSize); setTitlePosition(s.titlePosition)
    setWatermarkPath(s.watermarkPath); setWatermarkPosition(s.watermarkPosition); setWatermarkOpacity(s.watermarkOpacity)
    setBrollPlacements(s.brollPlacements); setVideoTransform(s.videoTransform)
    setPendingStart(s.pendingStart); setPendingEnd(s.pendingEnd)
  }, [])
  const history = useUndoRedo<Snapshot>(snapshot, applySnapshot)

  // ── Auto-save the draft to localStorage every 30s ───────────────────────────
  const autosave = useAutoSave<Snapshot>(`vertical-editor-draft-${projectId}-${clipId}`, snapshot)
  const [restoreDismissed, setRestoreDismissed] = useState(false)

  // ── Warn before closing with unsaved changes ────────────────────────────────
  // Baseline is captured once, a tick after the clip-seeding effect commits
  // (via rAF) so the initial seed itself never counts as a "change".
  const snapshotRef = useRef(snapshot)
  snapshotRef.current = snapshot
  const baselineRef = useRef<string | null>(null)
  const baselineCapturedRef = useRef(false)
  useEffect(() => {
    if (!clip || baselineCapturedRef.current) return
    baselineCapturedRef.current = true
    const raf = requestAnimationFrame(() => { baselineRef.current = JSON.stringify(snapshotRef.current) })
    return () => cancelAnimationFrame(raf)
  }, [clip])
  useEffect(() => {
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (baselineRef.current != null && JSON.stringify(snapshot) !== baselineRef.current) {
        e.preventDefault()
        e.returnValue = ''
      }
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [snapshot])

  // ── Keyboard shortcuts ──────────────────────────────────────────────────────
  const playPause = () => { const v = activeVideoRef.current; if (!v) return; v.paused ? void v.play() : v.pause() }
  const stepBy = (seconds: number) => {
    const v = activeVideoRef.current
    if (v) v.currentTime = clampNum(v.currentTime + seconds, 0, clipDuration)
  }
  useEditorShortcuts({
    onPlayPause: playPause,
    onStepSecond: (d) => stepBy(d),
    onStepFrame: (d) => stepBy(d / 30),
    onSplit: () => timelineRef.current?.split(),
    onToggleTrim: () => timelineRef.current?.toggleTrim(),
    onFit: () => timelineRef.current?.fit(),
    onZoom: (d) => (d > 0 ? timelineRef.current?.zoomIn() : timelineRef.current?.zoomOut()),
    onPlayheadZero: () => { const v = activeVideoRef.current; if (v) v.currentTime = 0 },
    onUndo: history.undo,
    onRedo: history.redo,
    onShowHelp: () => setShowShortcuts(true),
    onEscape: () => {
      if (showShortcuts) setShowShortcuts(false)
      else if (showSavePreset) setShowSavePreset(false)
    },
    modalOpen: showShortcuts || showSavePreset,
  })

  // ── Toast when a render finishes (with a download link) or fails ─────────────
  const notifiedCompletedRef = useRef<Set<number> | null>(null)
  const notifiedErrorRef = useRef<Set<number> | null>(null)
  useEffect(() => {
    if (!rendersQuery.data) return
    const completedIds = rendersQuery.data.filter((r) => r.status === 'completed').map((r) => r.id)
    const errored = rendersQuery.data.filter((r) => r.status === 'error')
    if (notifiedCompletedRef.current === null) {
      // seed on first load, no toast for renders that already finished before this window opened
      notifiedCompletedRef.current = new Set(completedIds)
      notifiedErrorRef.current = new Set(errored.map((r) => r.id))
      return
    }
    for (const id of completedIds) {
      if (!notifiedCompletedRef.current.has(id)) {
        notifiedCompletedRef.current.add(id)
        toast.success((t) => (
          <span className="flex items-center gap-3 text-sm">
            Render #{id} listo
            <a href={verticalApi.downloadUrl(projectId, id)} download
              className="text-brand-300 underline" onClick={() => toast.dismiss(t.id)}>Descargar</a>
          </span>
        ))
      }
    }
    for (const r of errored) {
      if (!notifiedErrorRef.current!.has(r.id)) {
        notifiedErrorRef.current!.add(r.id)
        toast.error(`Render falló: ${(r.error_message ?? 'error desconocido').slice(0, 80)}`)
      }
    }
  }, [rendersQuery.data, projectId])

  // ── Loading / error gates ─────────────────────────────────────────────────
  if (clipQuery.isLoading || stylesQuery.isLoading) {
    return (
      <div className="fixed inset-0 bg-slate-950 flex items-center justify-center">
        <Loader2 className="w-10 h-10 text-brand-400 animate-spin" />
      </div>
    )
  }
  if (!clip) {
    return (
      <div className="fixed inset-0 bg-slate-950 flex flex-col items-center justify-center gap-3 text-slate-300">
        <Square className="w-12 h-12 text-slate-600" />
        <p>No se encontró el clip #{clipId}.</p>
        <Button variant="secondary" onClick={() => window.close()}>Cerrar ventana</Button>
      </div>
    )
  }

  const previewEl = (
    <EditorPreview
      previewMode={previewMode} setPreviewMode={setPreviewMode}
      compareMode={compareMode} toggleCompare={() => setCompareMode((v) => !v)}
      draftUrl={draftUrl} previewUrl={previewUrl}
      draftPending={draftMutation.isPending} draftError={draftError}
      onRefresh={fireDraft} previewRender={previewRender}
      videoRef={activeVideoRef} brollCount={brollPlacements.length}
      transform={videoTransform} onTransformChange={setVideoTransform}
      onTransformCommit={handleTransformCommit} transformMode={transformMode}
      overlaySyncing={overlaySyncing}
      liveOverlay={{
        words: captionsQuery.data?.words,
        subStyle, subColor, subOutline, subHighlight, subSize, subPosition,
        addTitle, titleText, titleColor, titleSize, titlePosition,
        watermarkFileId, watermarkPosition, watermarkOpacity,
      }}
    />
  )

  const rightPanelEl = (
    <EditorRightPanel
      ref={rightPanelRef}
      styles={styles}
      layout={layout} setLayout={setLayout}
      bgStyle={bgStyle} setBgStyle={setBgStyle}
      bgColor={bgColor} setBgColor={setBgColor}
      bgColor2={bgColor2} setBgColor2={setBgColor2}
      subStyle={subStyle} setSubStyle={setSubStyle}
      subColor={subColor} setSubColor={setSubColor}
      subOutline={subOutline} setSubOutline={setSubOutline}
      subHighlight={subHighlight} setSubHighlight={setSubHighlight}
      subSize={subSize} setSubSize={setSubSize}
      subPosition={subPosition} setSubPosition={setSubPosition}
      addTitle={addTitle} setAddTitle={setAddTitle}
      titleText={titleText} setTitleText={setTitleText}
      titleColor={titleColor} setTitleColor={setTitleColor}
      titleSize={titleSize} setTitleSize={setTitleSize}
      titlePosition={titlePosition} setTitlePosition={setTitlePosition}
      projectId={projectId} clipId={clipId} clipDuration={clipDuration} onChangeForm={onChangeForm}
      watermarkPath={watermarkPath} watermarkFileId={watermarkFileId}
      watermarkPosition={watermarkPosition} setWatermarkPosition={setWatermarkPosition}
      watermarkOpacity={watermarkOpacity} setWatermarkOpacity={setWatermarkOpacity}
      onWatermarkUpload={handleWatermarkUpload} onWatermarkRemove={handleWatermarkRemove}
      uploadPending={uploadWatermark.isPending}
      transform={videoTransform} setTransform={setVideoTransform} onResetTransform={handleResetTransform}
      transformMode={transformMode} setTransformMode={setTransformMode}
      clip={clip}
      onRender={handleRender} renderPending={createRender.isPending} anyInProgress={anyInProgress}
      previewRender={previewRender} rendersCount={renders.length}
      recentRenders={renders} onCopyRenderSettings={copyRenderSettings}
    />
  )

  const leftSidebarEl = (
    <EditorLeftSidebar
      collapsed={leftCollapsed} onToggleCollapsed={() => setLeftCollapsed((v) => !v)}
      projectId={projectId} clip={clip} renders={renders}
      previewRenderId={previewRender?.id ?? null}
      onSelectRender={(r) => { setPreviewRender(r); setPreviewMode('final') }}
      onDeleteRender={(id) => deleteRender.mutate({ renderId: id, clipId })}
      clipId={clipId} onPickBroll={addBrollFromSuggestion} isBrollAdded={isSuggestionAdded}
      presets={presetsQuery.data ?? []} onApplyPreset={applyPreset}
      onDeletePreset={(id) => deletePreset.mutate(id)} onSavePreset={() => setShowSavePreset(true)}
      otherClipsCount={otherClips.length}
      onApplyToAllClips={applyToAllClips} applyingToAll={batchRender.isPending}
    />
  )

  return (
    <div className="fixed inset-0 bg-slate-950 flex flex-col text-slate-100" {...fileDrop.dragProps}>
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-3 border-b border-slate-800 bg-slate-900">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-pink-500 to-purple-600 flex items-center justify-center flex-shrink-0">
            <Smartphone className="w-5 h-5 text-white" />
          </div>
          <div className="min-w-0">
            <h1 className="font-semibold text-white text-lg leading-tight">Editor Vertical 9:16</h1>
            <p className="text-xs text-slate-400 truncate">
              {clip.title} · {formatDuration(clip.start)}–{formatDuration(clip.end)} ({clipDuration.toFixed(0)}s)
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <SaveIndicator lastSavedAt={autosave.lastSavedAt} saving={autosave.saving} />
          <button onClick={history.undo} disabled={!history.canUndo}
            className="p-2 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white disabled:opacity-30 focus-visible:ring-2 focus-visible:ring-brand-500" title="Deshacer (Ctrl/⌘+Z)">
            <Undo2 className="w-4 h-4" />
          </button>
          <button onClick={history.redo} disabled={!history.canRedo}
            className="p-2 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white disabled:opacity-30 focus-visible:ring-2 focus-visible:ring-brand-500" title="Rehacer (Ctrl/⌘+Shift+Z)">
            <Redo2 className="w-4 h-4" />
          </button>
          <button onClick={() => setShowShortcuts(true)}
            className="p-2 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white focus-visible:ring-2 focus-visible:ring-brand-500" title="Atajos de teclado (?)">
            <HelpCircle className="w-5 h-5" />
          </button>
          <Button variant="secondary" size="sm" onClick={() => setShowSavePreset(true)}>
            <Save className="w-4 h-4" />Guardar preset
          </Button>
          <button onClick={() => window.close()} className="p-2 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white focus-visible:ring-2 focus-visible:ring-brand-500" title="Cerrar ventana">
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Restore-draft banner (auto-save) */}
      {autosave.available && !restoreDismissed && (
        <div className="flex items-center justify-between gap-3 px-6 py-2 bg-brand-900/40 border-b border-brand-700/40 text-sm">
          <span className="text-brand-100">
            Se encontró un borrador sin guardar de {new Date(autosave.available.savedAt).toLocaleString('es-ES')}.
          </span>
          <div className="flex items-center gap-2">
            <Button size="sm" onClick={() => { if (autosave.available) applySnapshot(autosave.available.data); setRestoreDismissed(true); toast.success('Borrador restaurado') }}>
              Restaurar
            </Button>
            <Button variant="secondary" size="sm" onClick={() => { autosave.clear(); setRestoreDismissed(true) }}>Descartar</Button>
          </div>
        </div>
      )}

      {/* Body: workspace row + a full-width, drag-resizable timeline at the bottom */}
      <div className="flex-1 flex flex-col overflow-hidden min-h-0">
        {/* Workspace */}
        {narrow ? (
          <div className="flex-1 min-h-0 flex flex-col">
            <div className="flex-1 min-h-0">{previewEl}</div>
            <div className="h-[45%] min-h-0 border-t border-slate-700/50">{rightPanelEl}</div>
          </div>
        ) : (
          <div className="flex-1 min-h-0 flex">
            {leftSidebarEl}
            <div className="flex-1 min-h-0">{previewEl}</div>
            <div className={cn('flex-shrink-0 h-full min-h-0', rightWidthClass)}>{rightPanelEl}</div>
          </div>
        )}

        {/* Resize handle between the workspace and the timeline */}
        <div {...timeline.handleProps}
          className={cn('group relative h-1 flex-shrink-0 cursor-row-resize bg-slate-800 hover:bg-brand-500/50 transition-colors touch-none',
            timeline.dragging && 'bg-brand-500/60')}>
          <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-10 h-0.5 rounded-full bg-slate-600 group-hover:bg-brand-300" />
        </div>

        {/* Timeline (resizable height) */}
        <div className="flex-shrink-0 min-h-0" style={{ height: timeline.size }}>
          <TimeLineV2
            clipDuration={clipDuration}
            clipStart={clip.start}
            clipEnd={clip.end}
            trimWindowStart={trimWindow.start}
            trimWindowEnd={trimWindow.end}
            pendingStart={pendingStart}
            pendingEnd={pendingEnd}
            onTrimChange={(s, e) => { setPendingStart(s); setPendingEnd(e) }}
            onApplyTrim={handleApplyTrim}
            trimApplying={trimClip.isPending}
            trimChanged={trimChanged}
            brollPlacements={brollPlacements}
            onBrollUpdate={updateBrollPlacement}
            onBrollRemove={removeBrollPlacement}
            onBrollSplit={splitBrollPlacement}
            onBrollDuplicate={duplicateBrollPlacement}
            onSplitMiss={() => toast('Mueve el cursor sobre un B-roll para cortarlo')}
            words={captionsQuery.data?.words}
            onUpdateCaptionWord={handleUpdateCaptionWord}
            onDeleteCaptionWord={handleDeleteCaptionWord}
            addTitle={addTitle}
            titleText={titleText}
            setTitleText={setTitleText}
            titleColor={titleColor}
            setTitleColor={setTitleColor}
            titlePosition={titlePosition}
            setTitlePosition={setTitlePosition}
            onVideoTrackClick={handleVideoTrackClick}
            onCaptionBlockClick={handleCaptionBlockClick}
            onTitleBlockClick={handleTitleBlockClick}
            onResetTransform={handleResetTransform}
            videoTransform={videoTransform}
            setVideoTransform={setVideoTransform}
            speakerForClipTime={speakerForClipTime}
            playheadResetSignal={playheadResetSignal}
            videoRef={activeVideoRef}
            disabled={showShortcuts || showSavePreset}
            ref={timelineRef}
          />
        </div>
      </div>

      {/* Save preset dialog */}
      {showSavePreset && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[60] p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 w-full max-w-md shadow-2xl">
            <h3 className="text-lg font-semibold text-white mb-2">Guardar preset</h3>
            <p className="text-sm text-slate-400 mb-4">Guarda la configuración actual para reutilizarla con 1 click.</p>
            <input type="text" value={presetName} onChange={(e) => setPresetName(e.target.value)} autoFocus
              onKeyDown={(e) => { if (e.key === 'Enter') handleSavePreset() }}
              placeholder="Nombre del preset (ej. 'Mi estilo dorado')"
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-brand-500" />
            <div className="flex items-center gap-2 mt-4 justify-end">
              <Button variant="secondary" size="sm" onClick={() => setShowSavePreset(false)}>Cancelar</Button>
              <Button size="sm" onClick={handleSavePreset} disabled={!presetName.trim() || createPreset.isPending} loading={createPreset.isPending}>
                <Save className="w-4 h-4" />Guardar
              </Button>
            </div>
          </div>
        </div>
      )}

      {showShortcuts && <ShortcutsModal onClose={() => setShowShortcuts(false)} />}

      {/* Drag & drop overlay */}
      {fileDrop.isDragging && (
        <div className="fixed inset-0 bg-brand-600/20 backdrop-blur-sm z-50 flex items-center justify-center pointer-events-none">
          <div className={cn('bg-slate-900 border-2 border-dashed rounded-2xl p-8 text-center',
            fileDrop.draggedFileKind === 'unknown' ? 'border-rose-400' : 'border-brand-400')}>
            <Upload className={cn('w-12 h-12 mx-auto mb-3',
              fileDrop.draggedFileKind === 'unknown' ? 'text-rose-400' : 'text-brand-400')} />
            <p className="text-white font-medium">
              {fileDrop.draggedFileKind === 'image' && 'Suelta para subir como marca de agua'}
              {fileDrop.draggedFileKind === 'video' && 'Suelta para importar como nuevo clip'}
              {fileDrop.draggedFileKind === 'audio' && 'Suelta para importar audio'}
              {fileDrop.draggedFileKind === 'unknown' && 'Tipo de archivo no soportado'}
            </p>
          </div>
        </div>
      )}

      <Toaster position="bottom-right" toastOptions={{
        style: { background: '#1e293b', color: '#f1f5f9', border: '1px solid rgba(100,116,139,0.3)', borderRadius: '12px' },
        success: { iconTheme: { primary: '#22c55e', secondary: '#f1f5f9' } },
        error: { iconTheme: { primary: '#ef4444', secondary: '#f1f5f9' } },
      }} />
    </div>
  )
}
