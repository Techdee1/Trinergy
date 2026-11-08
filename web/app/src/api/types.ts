// Types mirror web/server/API.md. Optional where the API may omit a field.
export type Status = 'answered' | 'partial' | 'abstain' | 'not_evaluated'
export type RouterMode = 'single_report' | 'multi_report' | 'archive_wide' | string

export interface Health {
  status: string; live_mode: boolean; models: { primary: string; escalation: string }
  version: string; attribution: string; budget_remaining_usd: number
  details: { records: number; reports: number; catalog_questions: number; warm_seconds?: number
    rate_limit?: { per_minute: number; per_day: number }; server_budget_usd?: number; key_configured?: boolean; [k: string]: unknown }
}
export interface QuestionRow { id: string; set: 'challenge' | 'unseen' | 'adhoc'; question: string; status: Status; confidence: number; flags: string[]; router_mode: RouterMode }
export interface QuestionList { count: number; sets: Record<string, number>; questions: QuestionRow[] }

export interface Evidence {
  kind: 'pdf' | 'xml_only' | 'absent'; label: string; pdf_file?: string | null; page?: number | null; section?: string | null
  xml_file?: string | null; xml_only_paths?: string[]; page_url?: string | null; boxes_url?: string | null
}
export interface CitedRecord { id: string; type: string; text: string; report?: string; well?: string; report_date?: string; evidence: Evidence }

export interface ReportSel { report: string; well: string; date: string; reason: string }
export interface RouterTrace {
  mode: RouterMode; confidence: { level: 'high' | 'medium' | 'low'; basis: string }; reason: string
  wells_named: string[]; dates_named: string[]; date_range: [string, string] | null; topics: string[]
  early_abstain: boolean; wells_considered: { well: string; in_archive: boolean; reports_available: number }[]
  reports_selected: ReportSel[]; unmatched: unknown[]; gate: string | null
}
export interface ContextTrace {
  pass_name: string; final: boolean; est_tokens: number; lines: number; truncated: boolean; notes: string[]
  records: { id: string; type: string; report: string }[]
  aggregates: { id: string; text: string; sources: string[] }[]
  absent: { id: string; kind: string; reports_searched: number; records_searched: number; considered_and_rejected: { id: string; what: string; reason: string }[] }[]
}
export interface ModelCall {
  n: number; purpose: string; role: string; run: string; model: string; context_pass: string; outcome: string; cache_hit: boolean
  prompt_tokens: number | null; completion_tokens: number | null; tokens_source: string; context_tokens_estimate?: number
  latency_ms: number | null; cost_usd: number | null; incurred_usd: number | null; reply_status?: string; reply_cited?: string[]; error?: string | null
}
export interface VerifyCheck { name: string; label: string; result: 'pass' | 'fail' | 'flag' | 'not_applicable'; detail: string[] }
export interface VerifyTrace { n: number; target: string; target_call?: number; ok: boolean; checks: VerifyCheck[]; failures: string[]; flags: string[] }
export interface StageEvent { seq: number; stage: string; t_ms: number; data: any }
export interface Trace {
  router: RouterTrace; contexts: ContextTrace[]; model_calls: ModelCall[]; verifier: VerifyTrace[]
  retries: unknown[]; escalations: { seq: number; kind: string; trigger: string; model: string; reason: string; call?: number }[]
  second_pass: { ran: boolean; reason: string | null; used_for_answer: boolean; outcome: string | null }
  arbitration: { ran: boolean; retried: boolean; calls: number[]; outcome: string | null }
  cited: { model_cited: string[]; final: string[]; aggregates_cited: string[]; absent_cited: string[] }
  decisions: string[]; warnings: { code: string; message: string }[]
  totals: { model_calls: number; live_calls: number; cache_hits: number; prompt_tokens: number; completion_tokens: number
    calls_without_token_report: number; generation_cost_usd: number; incurred_cost_usd: number; model_latency_ms: number; wall_ms: number }
  events: StageEvent[]
}
export interface QuestionDetail {
  id: string; set: string; question: string; status: Status; answer: string; rationale: string | null; confidence: number
  verified: boolean; flags: string[]; router_mode: RouterMode; source: 'cache' | 'live' | 'mixed' | 'none'; evidence: string
  cited_records: CitedRecord[]; trace: Trace; clarification?: { message: string; examples: string[] } | null
}
export interface Boxes {
  record_id: string; pdf_file: string; page: number; section: string; match: string; page_width: number; page_height: number
  boxes: { x0: number; y0: number; x1: number; y1: number; nx0: number; ny0: number; nx1: number; ny1: number }[]; png_url: string
}
export interface ArchiveReport { file: string; pdf_file: string; well: string; wellbore: string; date: string; period_start: string; period_end: string; pages: number; records: number }
export interface Archive {
  wells: { well: string; wellbores: string[]; reports: number }[]
  wellbores: { wellbore: string; well: string; reports: number; first_report: string; last_report: string }[]
  reports: ArchiveReport[]
  record_counts: { by_type: Record<string, number>; total: number; derived_notes: number }
}
export interface Station { record_id: string; report_date: string; md: number; incl?: number; azi?: number; x: number; y: number; tvd: number }
export interface Trajectories {
  method: string; approximate: boolean; caveats: string[]
  wellbores: { wellbore: string; approximate: boolean; stations_used: number; status: string; reason: string | null; stations: Station[] }[]
}
export interface Costs {
  ledger: { calls: number; prompt_tokens: number; completion_tokens: number; cost_usd: number; label: string }
  derived_from_cache: { entries: number; cost_usd: number; cost_per_challenge_question_usd: number }
  per_question: { question_id: string; set: string; calls: number; prompt_tokens: number; completion_tokens: number; cost_usd: number }[]
  model_mix: { model: string; calls: number; prompt_tokens: number; completion_tokens: number; cost_usd: number; share_of_calls: number; share_of_cost: number }[]
  by_role: Record<string, { calls: number; cost_usd: number }>
  cache_hit_rate: { asks: any; startup_replay: any; note: string }
  budget: { server_budget_usd: number; spent_usd: number; remaining_usd: number; live_requests: number; ask_live_enabled: boolean }
}
export interface GenQuestion {
  id: string; question: string; category: string; kind: string; score: number; baseline_score: number; status: Status
  mode: string; confidence: number; verified: boolean; cost_usd: number; answer: string; evidence: string; detail_url: string
}
export interface Generalisation {
  available: boolean; message: string | null
  summary: null | { questions: number; mean_score: number; baseline_mean_score: number
    by_category: Record<string, { n: number; mean_score: number; baseline_mean_score?: number }>
    status_counts: Record<string, number>; cost_usd: number; scoring: string }
  questions: GenQuestion[]
}
