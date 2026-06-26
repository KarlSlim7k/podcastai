import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Keeps a timeline playhead in sync with a <video> element and back.
 *
 * Reading time: a single requestAnimationFrame loop polls `videoRef.current`
 * every frame and reports the time only when it actually changes. Polling the
 * ref (rather than binding `timeupdate` to one element) means the hook keeps
 * working when the editor swaps the underlying <video> node — e.g. when the
 * draft blob URL changes and React mounts a fresh element via `key`.
 *
 * Writing time: `seek(t)` sets `currentTime` on whatever video is currently
 * mounted, letting the timeline scrub the player.
 */
export interface SyncPlayhead {
  /** Move the underlying video to `time` seconds (clip-relative). */
  seek: (time: number) => void
  /** Whether the underlying video is currently playing. */
  playing: boolean
}

export function useSyncPlayhead(
  videoRef: React.RefObject<HTMLVideoElement> | undefined,
  onTime: (time: number) => void,
): SyncPlayhead {
  const onTimeRef = useRef(onTime)
  onTimeRef.current = onTime
  const [playing, setPlaying] = useState(false)

  useEffect(() => {
    if (!videoRef) return
    let raf = 0
    let last = -1
    let wasPlaying = false

    const tick = () => {
      const v = videoRef.current
      if (v) {
        const t = v.currentTime
        if (!Number.isNaN(t) && t !== last) {
          last = t
          onTimeRef.current(t)
        }
        const isPlaying = !v.paused && !v.ended
        if (isPlaying !== wasPlaying) {
          wasPlaying = isPlaying
          setPlaying(isPlaying)
        }
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [videoRef])

  const seek = useCallback((time: number) => {
    const v = videoRef?.current
    if (v && Number.isFinite(time)) {
      v.currentTime = Math.max(0, time)
    }
  }, [videoRef])

  return { seek, playing }
}
