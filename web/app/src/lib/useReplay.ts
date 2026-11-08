import { useCallback, useEffect, useRef, useState } from 'react'
import type { ReplayTimeline } from './adapter'
import { prefersReducedMotion } from './hooks'

export const SPEEDS = [0.5, 1, 2, 4] as const

/** Playback over a timeline. Visible state is a pure function of `idx`, so stepping back is trivial.
 *  idx -1 = nothing yet. When `follow` is set (live stream) idx tracks the newest stage as it arrives. */
export function useReplay(tl: ReplayTimeline, opts: { autoplay?: boolean; follow?: boolean; resetKey?: string } = {}) {
  const [idx, setIdx] = useState(-1)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState<number>(1)
  const last = tl.stages.length - 1
  const timer = useRef<number | undefined>(undefined)

  useEffect(() => { setIdx(-1); setPlaying(!!opts.autoplay && !opts.follow) }, [opts.resetKey]) // eslint-disable-line react-hooks/exhaustive-deps

  // autoplay kick-off once stages exist
  useEffect(() => { if (opts.autoplay && !opts.follow && idx === -1 && last >= 0 && playing) setIdx(0) }, [last, idx, playing, opts.autoplay, opts.follow])

  // live: follow newest stage
  useEffect(() => { if (opts.follow && last >= 0) { setIdx(last); setPlaying(false) } }, [opts.follow, last])

  useEffect(() => {
    window.clearTimeout(timer.current)
    if (!playing || idx < 0) return
    if (idx >= last) { if (tl.complete) setPlaying(false); return }
    const s = tl.stages[idx]
    const dwell = (prefersReducedMotion() ? s.durationMs * 0.6 : s.durationMs) / speed
    timer.current = window.setTimeout(() => setIdx(i => Math.min(i + 1, last)), dwell)
    return () => window.clearTimeout(timer.current)
  }, [playing, idx, speed, last, tl])

  const play = useCallback(() => { if (idx >= last && last >= 0) setIdx(0); else if (idx < 0 && last >= 0) setIdx(0); setPlaying(true) }, [idx, last])
  const pause = useCallback(() => setPlaying(false), [])
  const replay = useCallback(() => { setIdx(last >= 0 ? 0 : -1); setPlaying(true) }, [last])
  const step = useCallback((d: 1 | -1) => { setPlaying(false); setIdx(i => Math.max(-1, Math.min(last, (i < 0 && d > 0 ? -1 : i) + d))) }, [last])
  const goto = useCallback((i: number) => { setPlaying(false); setIdx(Math.max(-1, Math.min(last, i))) }, [last])
  const cycleSpeed = useCallback(() => setSpeed(s => SPEEDS[(SPEEDS.indexOf(s as any) + 1) % SPEEDS.length]), [])
  return { idx, playing, speed, setSpeed, play, pause, replay, step, goto, cycleSpeed, last }
}
