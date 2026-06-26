/**
 * 9:16 safe-zone guides (10% margins) drawn over the preview. Useful because
 * TikTok/Shorts/Reels overlay their own UI (captions, buttons, handle) on the
 * outer ~10% of the frame, so important content should stay inside.
 */
export function SafeAreaOverlay() {
  return (
    <div className="absolute inset-0 pointer-events-none z-20">
      {/* Outer 10% safe margin */}
      <div className="absolute border border-dashed border-cyan-400/60" style={{ inset: '10%' }} />
      {/* Center cross */}
      <div className="absolute left-1/2 top-0 bottom-0 w-px bg-cyan-400/20 -translate-x-1/2" />
      <div className="absolute top-1/2 left-0 right-0 h-px bg-cyan-400/20 -translate-y-1/2" />
      <span className="absolute left-1/2 -translate-x-1/2 text-[9px] font-mono text-cyan-300/80 bg-slate-900/70 px-1 rounded" style={{ top: 'calc(10% - 14px)' }}>
        zona segura
      </span>
    </div>
  )
}
