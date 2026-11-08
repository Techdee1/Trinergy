import type * as T from './types'

import { API_CONFIG } from './config'

export const API_BASE: string = API_CONFIG.url
export const API_SOURCE = API_CONFIG.source

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public retryAfter?: number, public body?: any) { super(message) }
}

async function toError(r: Response): Promise<ApiError> {
  let body: any = null
  try { body = await r.json() } catch { /* not json */ }
  const d = body?.detail
  const ra = Number(r.headers.get('Retry-After')) || undefined
  return new ApiError(r.status, d?.code ?? 'http_' + r.status, d?.message ?? r.statusText, ra, body)
}

async function get<R>(path: string, signal?: AbortSignal): Promise<R> {
  let r: Response
  try { r = await fetch(API_BASE + path, { signal }) } catch (e: any) {
    if (e?.name === 'AbortError') throw e
    throw new ApiError(0, 'unreachable', 'Cannot reach the archive server.')
  }
  if (!r.ok) throw await toError(r)
  return r.json()
}

const memo = new Map<string, Promise<any>>()
/** GET once per session; failed requests are not cached. */
function cached<R>(path: string): Promise<R> {
  if (!memo.has(path)) memo.set(path, get<R>(path).catch(e => { memo.delete(path); throw e }))
  return memo.get(path)!
}

export const api = {
  health: () => get<T.Health>('/health'),
  questions: () => cached<T.QuestionList>('/questions'),
  question: (id: string) => cached<T.QuestionDetail>('/questions/' + encodeURIComponent(id)),
  boxes: (id: string) => cached<T.Boxes>('/pages/' + encodeURIComponent(id) + '/boxes'),
  archive: () => cached<T.Archive>('/archive'),
  trajectories: () => cached<T.Trajectories>('/trajectories'),
  costs: () => get<T.Costs>('/costs'),
  generalisation: () => get<T.Generalisation>('/generalisation'),
  pageUrl: (recordId: string, zoom = 1.5, highlight = true) => `${API_BASE}/pages/${encodeURIComponent(recordId)}.png?zoom=${zoom}&highlight=${highlight}`,
  async ask(question: string): Promise<T.QuestionDetail> {
    let r: Response
    try {
      r = await fetch(API_BASE + '/ask', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question }) })
    } catch { throw new ApiError(0, 'unreachable', 'Cannot reach the archive server.') }
    if (!r.ok) throw await toError(r)
    return r.json()
  },
}

export interface StreamHandlers { onStage: (e: T.StageEvent) => void; onResult: (d: T.QuestionDetail) => void; onError: (e: ApiError) => void }

/** POST /ask/stream, parse SSE by hand (EventSource cannot POST). Returns an abort function. */
export function askStream(question: string, h: StreamHandlers): () => void {
  const ctl = new AbortController()
  ;(async () => {
    let r: Response
    try {
      r = await fetch(API_BASE + '/ask/stream', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question }), signal: ctl.signal })
    } catch (e: any) { if (e?.name !== 'AbortError') h.onError(new ApiError(0, 'unreachable', 'Cannot reach the archive server.')); return }
    if (!r.ok) { h.onError(await toError(r)); return }
    const reader = r.body!.getReader(); const dec = new TextDecoder(); let buf = ''
    try {
      for (;;) {
        const { value, done } = await reader.read(); if (done) break
        buf += dec.decode(value, { stream: true })
        let i: number
        while ((i = buf.indexOf('\n\n')) >= 0) {
          const block = buf.slice(0, i); buf = buf.slice(i + 2)
          let ev = 'message'; let data = ''
          for (const line of block.split('\n')) {
            if (line.startsWith('event:')) ev = line.slice(6).trim()
            else if (line.startsWith('data:')) data += line.slice(5).trim()
          }
          if (!data) continue
          const j = JSON.parse(data)
          if (ev === 'result') h.onResult(j)
          else if (ev === 'error') h.onError(new ApiError(j.code === 'rate_limited' ? 429 : 500, j.code, j.message))
          else h.onStage(j as T.StageEvent)
        }
      }
    } catch (e: any) { if (e?.name !== 'AbortError') h.onError(new ApiError(0, 'stream_broken', 'The connection dropped.')) }
  })()
  return () => ctl.abort()
}
