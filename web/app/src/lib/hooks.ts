import { useEffect, useState } from 'react'
import { ApiError } from '../api/client'

export interface Async<T> { data: T | null; error: ApiError | null; loading: boolean }

/** Run an API loader; re-runs when deps change. Unmounted calls are ignored. */
export function useAsync<T>(load: () => Promise<T>, deps: unknown[]): Async<T> {
  const [s, set] = useState<Async<T>>({ data: null, error: null, loading: true })
  useEffect(() => {
    let live = true
    set(p => ({ data: p.data, error: null, loading: true }))
    load().then(d => live && set({ data: d, error: null, loading: false }),
      e => live && set({ data: null, error: e instanceof ApiError ? e : new ApiError(0, 'unknown', String(e)), loading: false }))
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  return s
}

export function useKey(handler: (e: KeyboardEvent) => void, on = true) {
  useEffect(() => {
    if (!on) return
    const h = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return
      if (e.metaKey || e.ctrlKey || e.altKey) return
      handler(e)
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  })
}

export const prefersReducedMotion = () => typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches
