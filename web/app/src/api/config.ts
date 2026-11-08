/**
 * Resolves the API base URL once, at start-up. Precedence:
 *   1. ?api=<url> query parameter (before or inside the #hash); remembered for this tab so hash navigation keeps it
 *   2. window.__WELL_ARCHIVE_CONFIG__.apiUrl from public/config.js (editable in a built dist/)
 *   3. build-time VITE_API_URL (.env.production for builds, .env.local / default for dev)
 *   4. http://localhost:8000
 * Only http(s) URLs are accepted. These values are public; secrets never belong in any of them.
 */
export type ApiSource = 'query' | 'config.js' | 'build' | 'default'
const KEY = 'wa-api-override'

function clean(u: unknown): string | null {
  if (typeof u !== 'string' || !u.trim()) return null
  try {
    const url = new URL(u.trim())
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return null
    return url.origin + url.pathname.replace(/\/+$/, '')
  } catch { return null }
}

function fromQuery(): string | null | 'reset' {
  const params = [new URLSearchParams(location.search), new URLSearchParams(location.hash.split('?')[1] ?? '')]
  for (const p of params) {
    if (!p.has('api')) continue
    const v = p.get('api') ?? ''
    if (v === '' || v === 'default') return 'reset'
    return clean(v)
  }
  return null
}

function resolve(): { url: string; source: ApiSource } {
  const q = fromQuery()
  try {
    if (q === 'reset') sessionStorage.removeItem(KEY)
    else if (q) { sessionStorage.setItem(KEY, q); return { url: q, source: 'query' } }
    const kept = clean(sessionStorage.getItem(KEY)); if (kept) return { url: kept, source: 'query' }
  } catch { if (q && q !== 'reset') return { url: q, source: 'query' } }
  const cfg = clean((window as any).__WELL_ARCHIVE_CONFIG__?.apiUrl)
  if (cfg) return { url: cfg, source: 'config.js' }
  const build = clean((import.meta as any).env?.VITE_API_URL)
  if (build) return { url: build, source: 'build' }
  return { url: 'http://localhost:8000', source: 'default' }
}

export const API_CONFIG = resolve()
