import { forwardRef, useImperativeHandle, useRef, useState } from 'react'
import {
  Palette, Type, Square, Heading1, Captions, ImageIcon, Upload, Trash2,
  Wand2, Download, Loader2, SlidersHorizontal, Move, RotateCcw, Crop,
} from 'lucide-react'
import { Button } from '../ui/Button'
import { CaptionEditor } from './CaptionEditor'
import { PublishButtons, SocialMockBanner } from './PublishButtons'
import { StylePicker, ColorRow, SliderRow } from './VerticalEditorParts'
import { verticalApi, watermarkApi } from '../../services/api'
import { cn } from '../../utils'
import { isIdentityTransform } from '../../types'
import type {
  Clip, VerticalLayout, VerticalBgStyle, VerticalSubStyle, VerticalTitlePosition,
  WatermarkPosition, VerticalRender, VerticalStylesResponse, VideoTransform,
} from '../../types'

const WATERMARK_POSITIONS: [WatermarkPosition, string][] = [
  ['top_left', '↖ Sup. Izq.'], ['top_center', '↑ Superior'], ['top_right', '↗ Sup. Der.'],
  ['center_left', '← Centro Izq.'], ['center', '● Centro'], ['center_right', '→ Centro Der.'],
  ['bottom_left', '↙ Inf. Izq.'], ['bottom_center', '↓ Inferior'], ['bottom_right', '↘ Inf. Der.'],
]
const TITLE_POSITIONS: [VerticalTitlePosition, string][] = [
  ['top', '↑ Arriba'], ['center', '● Centro'], ['bottom', '↓ Abajo'],
]

type RightTab = 'estilo' | 'video' | 'watermark' | 'exportar'

/** Imperative API so the timeline's click-to-edit can drive this panel. */
export interface EditorRightPanelHandle {
  switchToTab: (tab: RightTab) => void
  focusSection: (section: 'title' | 'subtitle' | 'caption' | 'layout' | 'bg') => void
}

export interface EditorRightPanelProps {
  styles?: VerticalStylesResponse
  // Estilo — layout / background
  layout: VerticalLayout; setLayout: (v: VerticalLayout) => void
  bgStyle: VerticalBgStyle; setBgStyle: (v: VerticalBgStyle) => void
  bgColor: string; setBgColor: (v: string) => void
  bgColor2: string; setBgColor2: (v: string) => void
  // Estilo — subtitles
  subStyle: VerticalSubStyle; setSubStyle: (v: VerticalSubStyle) => void
  subColor: string; setSubColor: (v: string) => void
  subOutline: string; setSubOutline: (v: string) => void
  subHighlight: string; setSubHighlight: (v: string) => void
  subSize: number; setSubSize: (v: number) => void
  subPosition: number; setSubPosition: (v: number) => void
  // Estilo — title
  addTitle: boolean; setAddTitle: (v: boolean) => void
  titleText: string; setTitleText: (v: string) => void
  titleColor: string; setTitleColor: (v: string) => void
  titleSize: number; setTitleSize: (v: number) => void
  titlePosition: VerticalTitlePosition; setTitlePosition: (v: VerticalTitlePosition) => void
  // Caption editor
  projectId: number; clipId: number; clipDuration: number; onChangeForm: () => void
  // Watermark
  watermarkPath: string | null; watermarkFileId: string | null
  watermarkPosition: WatermarkPosition; setWatermarkPosition: (v: WatermarkPosition) => void
  watermarkOpacity: number; setWatermarkOpacity: (v: number) => void
  onWatermarkUpload: (file: File) => void; onWatermarkRemove: () => void; uploadPending: boolean
  // Video transform (Priority 1)
  transform: VideoTransform; setTransform: (t: VideoTransform) => void
  onResetTransform: () => void
  transformMode: boolean; setTransformMode: (v: boolean) => void
  // Export
  clip: Clip
  onRender: () => void; renderPending: boolean; anyInProgress: boolean
  previewRender: VerticalRender | null; rendersCount: number
  // Recent renders (Priority 6) — click to copy settings into the editor
  recentRenders: VerticalRender[]
  onCopyRenderSettings: (r: VerticalRender) => void
}

function TabButton({ active, onClick, icon, label }: {
  active: boolean; onClick: () => void; icon: React.ReactNode; label: string
}) {
  return (
    <button onClick={onClick}
      className={cn('flex-1 flex items-center justify-center gap-1.5 px-2 py-2 text-xs font-medium border-b-2 transition-colors',
        active
          ? 'border-brand-500 text-brand-200 bg-brand-600/10'
          : 'border-transparent text-slate-400 hover:text-slate-200')}>
      {icon}<span>{label}</span>
    </button>
  )
}

const clampNum = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))

function NumberRow({ label, value, onChange, step = 1, min, max }: {
  label: string; value: number; onChange: (v: number) => void; step?: number; min?: number; max?: number
}) {
  return (
    <label className="flex items-center gap-1.5 text-[11px] text-slate-400">
      <span className="w-14">{label}</span>
      <input type="number" value={Number.isFinite(value) ? value : 0} step={step} min={min} max={max}
        onChange={(e) => { const n = Number(e.target.value); if (!Number.isNaN(n)) onChange(n) }}
        className="flex-1 w-0 bg-slate-800 border border-slate-700 rounded px-2 py-1 text-white font-mono text-[11px] focus:outline-none focus:border-brand-500" />
    </label>
  )
}

function Section({ icon, title, children, action }: {
  icon: React.ReactNode; title: string; children: React.ReactNode; action?: React.ReactNode
}) {
  return (
    <div className="rounded-lg border border-slate-700/50 bg-slate-900/40">
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-700/40">
        <div className="flex items-center gap-2">{icon}<p className="text-sm font-medium text-white">{title}</p></div>
        {action}
      </div>
      <div className="p-3 space-y-2">{children}</div>
    </div>
  )
}

/** Tabbed right panel: Estilo / Watermark / Exportar. */
export const EditorRightPanel = forwardRef<EditorRightPanelHandle, EditorRightPanelProps>(function EditorRightPanel(p, ref) {
  const [tab, setTab] = useState<RightTab>('estilo')
  const [showCaptionEditor, setShowCaptionEditor] = useState(false)
  const subHasHighlight = ['karaoke', 'mrbeast', 'hormozi', 'tiktok_classic', 'neon'].includes(p.subStyle)

  const layoutSectionRef = useRef<HTMLDivElement>(null)
  const bgSectionRef = useRef<HTMLDivElement>(null)
  const subtitleSectionRef = useRef<HTMLDivElement>(null)
  const titleSectionRef = useRef<HTMLDivElement>(null)
  const titleInputRef = useRef<HTMLInputElement>(null)

  useImperativeHandle(ref, () => ({
    switchToTab: (t) => setTab(t),
    focusSection: (section) => {
      setTab('estilo')
      if (section === 'caption') setShowCaptionEditor(true)
      // Wait a tick so the tab/section just switched to has mounted.
      requestAnimationFrame(() => {
        const refMap = {
          title: titleSectionRef, subtitle: subtitleSectionRef,
          caption: subtitleSectionRef, layout: layoutSectionRef, bg: bgSectionRef,
        }
        refMap[section].current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
        if (section === 'title') titleInputRef.current?.focus()
      })
    },
  }))

  return (
    <div className="flex flex-col h-full min-h-0 bg-slate-900 border-l border-slate-700/50">
      {/* Tab bar */}
      <div className="flex bg-slate-900 border-b border-slate-700/50 flex-shrink-0">
        <TabButton active={tab === 'estilo'} onClick={() => setTab('estilo')} icon={<Palette className="w-3.5 h-3.5" />} label="Estilo" />
        <TabButton active={tab === 'video'} onClick={() => setTab('video')} icon={<Move className="w-3.5 h-3.5" />} label="Video" />
        <TabButton active={tab === 'watermark'} onClick={() => setTab('watermark')} icon={<ImageIcon className="w-3.5 h-3.5" />} label="Marca" />
        <TabButton active={tab === 'exportar'} onClick={() => setTab('exportar')} icon={<Wand2 className="w-3.5 h-3.5" />} label="Exportar" />
      </div>

      <div key={tab} className="flex-1 overflow-y-auto p-3 space-y-3 tab-fade">
        {tab === 'estilo' && (
          <>
            <div ref={layoutSectionRef}>
              <Section icon={<Square className="w-4 h-4 text-brand-400" />} title="Layout">
                <StylePicker options={p.styles?.layouts ?? []} value={p.layout} onChange={(v) => p.setLayout(v as VerticalLayout)} />
              </Section>
            </div>

            <div ref={bgSectionRef}>
              <Section icon={<Palette className="w-4 h-4 text-brand-400" />} title="Fondo">
                <StylePicker options={p.styles?.backgrounds ?? []} value={p.bgStyle} onChange={(v) => p.setBgStyle(v as VerticalBgStyle)} />
                {(p.bgStyle === 'solid' || p.bgStyle === 'gradient') && <ColorRow label="Color 1" value={p.bgColor} onChange={p.setBgColor} />}
                {p.bgStyle === 'gradient' && <ColorRow label="Color 2" value={p.bgColor2} onChange={p.setBgColor2} />}
              </Section>
            </div>

            <div ref={subtitleSectionRef}>
              <Section icon={<Type className="w-4 h-4 text-brand-400" />} title="Subtítulos"
                action={
                  <button onClick={() => setShowCaptionEditor((v) => !v)} className="text-xs text-brand-400 hover:underline flex items-center gap-1">
                    <Captions className="w-3.5 h-3.5" />{showCaptionEditor ? 'Ocultar' : 'Editar palabras'}
                  </button>
                }>
                <StylePicker options={p.styles?.subtitle_styles ?? []} value={p.subStyle} onChange={(v) => p.setSubStyle(v as VerticalSubStyle)} />
                <ColorRow label="Texto" value={p.subColor} onChange={p.setSubColor} />
                <ColorRow label="Contorno" value={p.subOutline} onChange={p.setSubOutline} />
                {subHasHighlight && <ColorRow label="Highlight" value={p.subHighlight} onChange={p.setSubHighlight} />}
                <SliderRow label="Tamaño" min={32} max={120} value={p.subSize} onChange={p.setSubSize} display={String(p.subSize)} />
                <SliderRow label="Altura" min={40} max={900} step={10} value={p.subPosition} onChange={p.setSubPosition}
                  display={`${p.subPosition}px`} hint="Distancia desde el borde inferior" />
                {showCaptionEditor && (
                  <div className="pt-2 border-t border-slate-700/40">
                    <CaptionEditor projectId={p.projectId} clipId={p.clipId} clipDuration={p.clipDuration} onChanged={p.onChangeForm} />
                  </div>
                )}
              </Section>
            </div>

            <div ref={titleSectionRef}>
            <Section icon={<Heading1 className="w-4 h-4 text-brand-400" />} title="Título al inicio"
              action={<input type="checkbox" checked={p.addTitle} onChange={(e) => p.setAddTitle(e.target.checked)} className="w-4 h-4 accent-brand-500" />}>
              {p.addTitle ? (
                <>
                  <input ref={titleInputRef} type="text" value={p.titleText} onChange={(e) => p.setTitleText(e.target.value)} placeholder="Título del clip"
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-brand-500" />
                  <ColorRow label="Color" value={p.titleColor} onChange={p.setTitleColor} />
                  <SliderRow label="Tamaño" min={36} max={140} value={p.titleSize} onChange={p.setTitleSize} display={String(p.titleSize)} />
                  <div className="pt-1">
                    <p className="text-xs text-slate-400 mb-1">Posición</p>
                    <div className="grid grid-cols-3 gap-1">
                      {TITLE_POSITIONS.map(([val, label]) => (
                        <button key={val} onClick={() => p.setTitlePosition(val)}
                          className={cn('px-2 py-1.5 text-[11px] rounded border transition-colors',
                            p.titlePosition === val ? 'bg-brand-500 border-brand-500 text-white' : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-white')}>
                          {label}
                        </button>
                      ))}
                    </div>
                  </div>
                </>
              ) : (
                <p className="text-xs text-slate-500">Activa la casilla para añadir un título al inicio del clip.</p>
              )}
            </Section>
            </div>
          </>
        )}

        {tab === 'video' && (
          <Section icon={<Move className="w-4 h-4 text-brand-400" />} title="Transformar video"
            action={
              <button onClick={p.onResetTransform} disabled={isIdentityTransform(p.transform)}
                className="text-xs text-brand-400 hover:underline flex items-center gap-1 disabled:opacity-40 disabled:no-underline">
                <RotateCcw className="w-3.5 h-3.5" />Reiniciar
              </button>
            }>
            <button onClick={() => p.setTransformMode(!p.transformMode)}
              className={cn('w-full flex items-center justify-center gap-2 px-3 py-2 text-sm rounded-lg border transition-colors',
                p.transformMode ? 'bg-brand-600 border-brand-500 text-white' : 'bg-slate-800 border-slate-700 text-slate-300 hover:text-white')}>
              <Crop className="w-4 h-4" />{p.transformMode ? 'Edición visual activa' : 'Editar en el preview'}
            </button>
            <p className="text-[11px] text-slate-500">
              Arrastra el recuadro en el preview para mover, las esquinas para escalar y el tirador superior para rotar.
            </p>
            <div className="grid grid-cols-2 gap-2 pt-1">
              <NumberRow label="X" value={p.transform.x} step={1}
                onChange={(v) => p.setTransform({ ...p.transform, x: v })} />
              <NumberRow label="Y" value={p.transform.y} step={1}
                onChange={(v) => p.setTransform({ ...p.transform, y: v })} />
              <NumberRow label="Escala %" value={p.transform.scale} step={1} min={10} max={400}
                onChange={(v) => p.setTransform({ ...p.transform, scale: clampNum(v, 10, 400) })} />
              <NumberRow label="Rotación °" value={p.transform.rotation} step={1} min={-180} max={180}
                onChange={(v) => p.setTransform({ ...p.transform, rotation: clampNum(v, -180, 180) })} />
            </div>
          </Section>
        )}

        {tab === 'watermark' && (
          <Section icon={<ImageIcon className="w-4 h-4 text-brand-400" />} title="Marca de agua">
            <div className="flex items-center gap-2">
              <label className="cursor-pointer">
                <input type="file" accept="image/png,image/jpeg,image/svg+xml" className="hidden"
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) p.onWatermarkUpload(f); e.target.value = '' }} />
                <span className={cn('inline-flex items-center gap-2 px-3 py-1.5 text-xs rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-100 border border-slate-600',
                  p.uploadPending && 'opacity-60')}>
                  {p.uploadPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                  {p.watermarkPath ? 'Cambiar' : 'Subir'} PNG
                </span>
              </label>
              {p.watermarkPath && (
                <>
                  {p.watermarkFileId && (
                    <img src={watermarkApi.fileUrl(p.watermarkFileId)} alt="watermark" className="w-10 h-10 object-contain bg-slate-950 rounded border border-slate-700" />
                  )}
                  <button onClick={p.onWatermarkRemove} className="p-1 text-slate-500 hover:text-red-400" title="Quitar marca">
                    <Trash2 className="w-3 h-3" />
                  </button>
                </>
              )}
            </div>
            {p.watermarkPath ? (
              <>
                <div className="pt-2">
                  <p className="text-xs text-slate-400 mb-1">Posición</p>
                  <div className="grid grid-cols-3 gap-1">
                    {WATERMARK_POSITIONS.map(([val, label]) => (
                      <button key={val} onClick={() => p.setWatermarkPosition(val)}
                        className={cn('px-2 py-1 text-[10px] rounded border transition-colors',
                          p.watermarkPosition === val ? 'bg-brand-500 border-brand-500 text-white' : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-white')}>
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
                <SliderRow label="Opacidad" min={10} max={100} step={5}
                  value={Math.round(p.watermarkOpacity * 100)} onChange={(v) => p.setWatermarkOpacity(v / 100)}
                  display={`${Math.round(p.watermarkOpacity * 100)}%`} />
              </>
            ) : (
              <p className="text-xs text-slate-500">Sube un PNG con transparencia para superponerlo en el render final.</p>
            )}
          </Section>
        )}

        {tab === 'exportar' && (
          <>
            <SocialMockBanner />
            <Button onClick={p.onRender} disabled={p.renderPending || p.anyInProgress}
              loading={p.renderPending || p.anyInProgress} className="w-full" size="lg">
              <Wand2 className="w-4 h-4" />
              {p.anyInProgress ? 'Render en progreso...' : 'Renderizar video vertical'}
            </Button>
            {p.anyInProgress && (
              <p className="text-xs text-amber-400 text-center animate-pulse">
                <Loader2 className="w-3 h-3 inline animate-spin mr-1" />Procesando con ffmpeg. 10-30s.
              </p>
            )}
            <p className="text-[11px] text-slate-500 flex items-center gap-1">
              <SlidersHorizontal className="w-3 h-3" />{p.rendersCount} render(s) · galería en la barra izquierda
            </p>

            {p.previewRender && (
              <a href={verticalApi.downloadUrl(p.projectId, p.previewRender.id)} download
                className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-slate-800 hover:bg-slate-700 rounded-lg text-sm text-slate-200 transition-colors">
                <Download className="w-4 h-4" />Descargar render #{p.previewRender.id}
              </a>
            )}
            {p.previewRender && (
              <PublishButtons projectId={p.projectId} verticalRenderId={p.previewRender.id}
                title={p.clip.title} description={(p.clip.description || p.clip.title) + ' #Shorts'} hashtags={[]} />
            )}

            {p.recentRenders.length > 0 && (
              <div className="pt-2 border-t border-slate-700/40">
                <p className="text-xs font-semibold text-slate-400 mb-2">Renders recientes</p>
                <div className="space-y-1">
                  {p.recentRenders.slice(0, 5).map((r) => (
                    <button key={r.id} onClick={() => p.onCopyRenderSettings(r)}
                      title="Copiar ajustes de este render al editor"
                      className="w-full flex items-center justify-between gap-2 px-2 py-1.5 rounded-lg bg-slate-800/40 border border-slate-700/40 hover:bg-slate-800/70 text-left">
                      <span className="text-[11px] text-slate-300 truncate">#{r.id} · {r.layout}/{r.sub_style}</span>
                      <span className={cn('text-[10px] px-1.5 py-0.5 rounded flex-shrink-0',
                        r.status === 'completed' ? 'bg-green-900/70 text-green-200'
                          : r.status === 'error' ? 'bg-red-900/70 text-red-200'
                          : 'bg-amber-900/70 text-amber-200')}>{r.status}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
})
