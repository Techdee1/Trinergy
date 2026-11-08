import { useEffect, useRef, useState } from 'react'
import { prefersReducedMotion } from '../lib/hooks'

/** Tweens a number once on mount/change. Reduced motion: no tween. */
export function CountUp({ to, format = (n: number) => Math.round(n).toLocaleString('en-US'), ms = 900 }: { to: number; format?: (n: number) => string; ms?: number }) {
  const [v, setV] = useState(prefersReducedMotion() ? to : 0)
  const raf = useRef(0)
  useEffect(() => {
    if (prefersReducedMotion()) { setV(to); return }
    const t0 = performance.now()
    const tick = (t: number) => { const p = Math.min(1, (t - t0) / ms); setV(to * (1 - Math.pow(1 - p, 3))); if (p < 1) raf.current = requestAnimationFrame(tick) }
    raf.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf.current)
  }, [to, ms])
  return <span className="num">{format(v)}</span>
}
