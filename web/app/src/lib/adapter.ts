/**
 * Shared data adapter for Mission control. BOTH the 2D replay and the future 3D scene consume only this module.
 * It turns real API payloads into (1) an ordered replay timeline and (2) a "world": wells, wellbores with
 * trajectories, reports positioned along their wellbore, and the record -> report mapping.
 * Nothing here invents data. Order and payloads are real; `durationMs` is presentation pacing only.
 */
import type { Archive, ContextTrace, ModelCall, QuestionDetail, RouterTrace, StageEvent, Station, Trajectories, VerifyTrace } from '../api/types'
import { modelFamily } from './format'

// ───────────────────────── replay timeline ─────────────────────────
export type StageKind = 'parse' | 'route' | 'gate' | 'context' | 'draft' | 'verify' | 'second_pass' | 'escalate' | 'arbitrate' | 'answer'

export interface ReplayStage {
  index: number
  kind: StageKind
  title: string
  plain: string                 // one-line plain-language meaning
  realMs: number | null         // t_ms of the first source event (server clock), null if synthesised from the final detail
  durationMs: number            // presentation dwell at 1x speed
  seq: number[]                 // source event seq numbers
  payload: any                  // see ReplayPayload below
}
/** payload by kind: parse/route/gate: RouterTrace · context: ContextTrace · draft: ModelCall[] · verify: VerifyTrace[]
 *  second_pass: {reason} · escalate: {trigger,model,context_pass,reason} · arbitrate: {retry,model,context_pass,reason}
 *  answer: {status, confidence, source, flags, detail?: QuestionDetail} */
export interface ReplayTimeline { question: string; stages: ReplayStage[]; complete: boolean; final: QuestionDetail | null }

const COPY: Record<StageKind, { title: string; plain: string; ms: number }> = {
  parse: { title: 'Read the question', plain: 'Code pulls out the well, date and topic.', ms: 1800 },
  route: { title: 'Pick the reports', plain: 'The router chooses which daily reports to open. The rest stay closed.', ms: 2800 },
  gate: { title: 'Ask for more detail', plain: 'The question is too vague to search, so no model is called.', ms: 2400 },
  context: { title: 'Gather the evidence', plain: 'Records, computed totals and notes about missing fields go into the context.', ms: 2800 },
  draft: { title: 'Draft the answer', plain: 'A small model phrases an answer from that evidence and cites records.', ms: 2600 },
  verify: { title: 'Verify every claim', plain: 'Code checks citations, numbers and abstentions against the records.', ms: 3000 },
  second_pass: { title: 'Second pass', plain: 'The context was enriched and the question asked again.', ms: 2400 },
  escalate: { title: 'Escalate', plain: 'The verifier objected, so a larger model tries with the same evidence.', ms: 2600 },
  arbitrate: { title: 'Arbitrate', plain: 'Two drafts disagreed. An arbiter picks the one the records support.', ms: 2600 },
  answer: { title: 'Resolve', plain: 'The answer and its rule-based confidence settle.', ms: 3200 },
}

/** Build the stage list from stage events (works for a partial list while streaming). Consecutive model_call and verify events merge. */
export function buildTimeline(question: string, events: StageEvent[], final: QuestionDetail | null = null): ReplayTimeline {
  const stages: ReplayStage[] = []
  const push = (kind: StageKind, e: StageEvent | null, payload: any) =>
    stages.push({ index: stages.length, kind, ...COPY[kind], durationMs: COPY[kind].ms, realMs: e?.t_ms ?? null, seq: e ? [e.seq] : [], payload })
  const last = () => stages[stages.length - 1]
  for (const e of events) {
    switch (e.stage) {
      case 'route': push('parse', e, e.data); push('route', e, e.data); break
      case 'gate': push('gate', e, e.data); break
      case 'context_built': push('context', e, e.data); break
      case 'model_call':
        if (last()?.kind === 'draft') { last().payload.push(e.data); last().seq.push(e.seq) } else push('draft', e, [e.data])
        break
      case 'verify':
        if (last()?.kind === 'verify') { last().payload.push(e.data); last().seq.push(e.seq) } else push('verify', e, [e.data])
        break
      case 'second_pass': push('second_pass', e, e.data); break
      case 'escalate': push('escalate', e, e.data); break
      case 'arbitrate': push('arbitrate', e, e.data); break
      case 'result': push('answer', e, { ...e.data, detail: final }); break
      default: break // aggregates_added (already inside ContextTrace), warning
    }
  }
  if (final && !stages.some(s => s.kind === 'answer')) push('answer', null, { status: final.status, confidence: final.confidence, source: final.source, flags: final.flags, detail: final })
  return { question, stages, complete: !!final || stages.some(s => s.kind === 'answer'), final }
}

export const timelineFromDetail = (d: QuestionDetail) => buildTimeline(d.question, d.trace.events, d)

// ───────────────────────── derived replay state (pure function of stage index) ─────────────────────────
export interface ReplayView {
  router: RouterTrace | null
  parsed: boolean; routed: boolean
  selected: Set<string>; candidates: Set<string>; contextCount: Map<string, number>
  contexts: ContextTrace[]; aggregates: { id: string; text: string }[]; absent: ContextTrace['absent']
  drafts: ModelCall[]; citedIds: string[]; citedReports: Set<string>
  verifies: VerifyTrace[]; verifying: boolean
  second: any | null; escalations: any[]; arbitrations: any[]
  gate: any | null; answered: boolean; answer: ReplayStage['payload'] | null
}
export function viewAt(tl: ReplayTimeline, idx: number): ReplayView {
  const v: ReplayView = { router: null, parsed: false, routed: false, selected: new Set(), candidates: new Set(), contextCount: new Map(), contexts: [], aggregates: [], absent: [],
    drafts: [], citedIds: [], citedReports: new Set(), verifies: [], verifying: false, second: null, escalations: [], arbitrations: [], gate: null, answered: false, answer: null }
  const recReport = new Map<string, string>()
  tl.stages.slice(0, idx + 1).forEach((s, i) => {
    if (s.kind === 'parse') { v.parsed = true; v.router = s.payload }
    else if (s.kind === 'route') {
      v.routed = true; v.router = s.payload
      if (s.payload.gate) return // clarification gate: nothing was opened
      for (const r of s.payload.reports_selected) v.selected.add(r.report)
      const named = s.payload.wells_considered.map((w: any) => w.well)
      named.forEach((w: string) => v.candidates.add(w))
      for (const r of s.payload.reports_selected) v.candidates.add(r.well)
    } else if (s.kind === 'gate') v.gate = s.payload
    else if (s.kind === 'context') {
      const c = s.payload as ContextTrace; v.contexts.push(c)
      c.records.forEach(r => { recReport.set(r.id, r.report); v.contextCount.set(r.report, (v.contextCount.get(r.report) ?? 0) + (c.final || v.contexts.length === 1 ? 1 : 0)) })
      v.aggregates = c.aggregates.map(a => ({ id: a.id, text: a.text })); v.absent = c.absent
    } else if (s.kind === 'draft') { v.drafts.push(...s.payload); s.payload.forEach((m: ModelCall) => (m.reply_cited ?? []).forEach(id => { if (!v.citedIds.includes(id)) v.citedIds.push(id) })) }
    else if (s.kind === 'verify') { v.verifies.push(...s.payload); v.verifying = i === idx }
    else if (s.kind === 'second_pass') v.second = s.payload
    else if (s.kind === 'escalate') v.escalations.push(s.payload)
    else if (s.kind === 'arbitrate') v.arbitrations.push(s.payload)
    else if (s.kind === 'answer') { v.answered = true; v.answer = s.payload }
  })
  if (v.answered && tl.final && tl.final.status !== 'not_evaluated') { v.citedIds = tl.final.trace.cited.final.slice(); }
  v.citedIds.forEach(id => { const r = recReport.get(id) ?? tl.final?.cited_records.find(c => c.id === id)?.report; if (r) v.citedReports.add(r) })
  return v
}

// ───────────────────────── world: wells, trajectories, reports, record mapping ─────────────────────────
export interface WorldReport { stem: string; file: string; pdfFile: string; wellbore: string; date: string; t: number; ordinal: number; records: number; pages: number
  /** position along its wellbore: 0..1 by report date between first and last report of that wellbore */
  along: number
  /** nearest surveyed station on/before this report's date, if any (x east m, y north m, tvd m, md m) */
  anchor: { x: number; y: number; tvd: number; md: number | null; approximate: boolean } | null }
export interface WorldWellbore { name: string; well: string; reports: WorldReport[]; first: string; last: string
  trajectory: { status: string; reason: string | null; approximate: boolean; stations: Station[] } | null }
export interface World { wellbores: WorldWellbore[]; reportByStem: Map<string, WorldReport>; maxOrdinal: number; approximate: boolean; caveats: string[] }

export const stemOf = (file: string) => file.replace(/\.(xml|pdf)$/, '')

export function buildWorld(archive: Archive, traj: Trajectories | null): World {
  const byWb = new Map<string, WorldWellbore>()
  for (const w of archive.wellbores) byWb.set(w.wellbore, { name: w.wellbore, well: w.well, reports: [], first: w.first_report, last: w.last_report, trajectory: null })
  const reportByStem = new Map<string, WorldReport>()
  for (const r of [...archive.reports].sort((a, b) => a.date.localeCompare(b.date))) {
    const wb = byWb.get(r.wellbore); if (!wb) continue
    const rep: WorldReport = { stem: stemOf(r.file), file: r.file, pdfFile: r.pdf_file, wellbore: r.wellbore, date: r.date, t: Date.parse(r.date), ordinal: wb.reports.length, records: r.records, pages: r.pages, along: 0, anchor: null }
    wb.reports.push(rep); reportByStem.set(rep.stem, rep)
  }
  const tw = new Map((traj?.wellbores ?? []).map(t => [t.wellbore, t]))
  for (const wb of byWb.values()) {
    const t = tw.get(wb.name)
    wb.trajectory = t ? { status: t.status, reason: t.reason, approximate: t.approximate, stations: t.stations } : null
    const t0 = wb.reports[0]?.t ?? 0, t1 = wb.reports[wb.reports.length - 1]?.t ?? 1
    for (const rep of wb.reports) {
      rep.along = t1 > t0 ? (rep.t - t0) / (t1 - t0) : 0
      const st = wb.trajectory?.stations ?? []
      let pick: Station | null = null
      for (const s of st) if (s.report_date <= rep.date) pick = s
      if (pick) rep.anchor = { x: pick.x, y: pick.y, tvd: pick.tvd, md: pick.md ?? null, approximate: true }
    }
  }
  const wellbores = [...byWb.values()].sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }))
  return { wellbores, reportByStem, maxOrdinal: Math.max(1, ...wellbores.map(w => w.reports.length)), approximate: traj?.approximate ?? true, caveats: traj?.caveats ?? [] }
}

/** record id -> report stem, from every context in the timeline and the final cited records */
export function recordToReport(tl: ReplayTimeline): Map<string, string> {
  const m = new Map<string, string>()
  for (const s of tl.stages) if (s.kind === 'context') (s.payload as ContextTrace).records.forEach(r => m.set(r.id, r.report))
  tl.final?.cited_records.forEach(c => { if (c.report) m.set(c.id, c.report) })
  return m
}

export const draftLabel = (m: ModelCall) => `${modelFamily(m.model)}${m.cache_hit ? ' · replayed' : ' · live'}`
