/**
 * Classifies which form fields in the vertical editor need a server-side
 * draft re-render (ffmpeg) vs. which can be approximated instantly with a
 * client-side CSS overlay (see LiveOverlay.tsx).
 *
 * Structural fields change the actual video pixels (background compositing,
 * subtitle box geometry, main-video transform) and can't be faked in CSS —
 * they still go through the debounced draft render. Live-overlay fields only
 * change colors/text/position of things that can be drawn on top of the
 * existing draft frame, so the UI can reflect them with zero latency.
 */
export const STRUCTURAL_FIELDS = [
  'layout', 'bgStyle', 'bgColor', 'bgColor2', 'subStyle', 'videoTransform',
] as const

export type StructuralField = typeof STRUCTURAL_FIELDS[number]

export const LIVE_OVERLAY_FIELDS = [
  'subColor', 'subOutline', 'subHighlight', 'subSize', 'subPosition',
  'addTitle', 'titleText', 'titleColor', 'titleSize', 'titlePosition',
  'watermarkOpacity', 'watermarkPosition',
] as const

export type LiveOverlayField = typeof LIVE_OVERLAY_FIELDS[number]

export function isStructuralField(field: string): field is StructuralField {
  return (STRUCTURAL_FIELDS as readonly string[]).includes(field)
}
