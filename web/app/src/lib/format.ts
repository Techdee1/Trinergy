export const usd = (n: number | null | undefined, d = 4) => n == null ? '—' : '$' + n.toFixed(d)
export const usd2 = (n: number | null | undefined) => n == null ? '—' : '$' + n.toFixed(2)
export const int = (n: number | null | undefined) => n == null ? '—' : Math.round(n).toLocaleString('en-US')
export const pct = (n: number | null | undefined, d = 0) => n == null ? '—' : (n * 100).toFixed(d) + '%'
export const ms = (n: number | null | undefined) => n == null ? '—' : n < 1000 ? `${Math.round(n)} ms` : `${(n / 1000).toFixed(1)} s`
export const shortModel = (m: string) => m.replace(/^anthropic\//, '').replace('claude-', '').replace(/-/g, ' ').replace(/\b(\w)/g, c => c.toUpperCase()).replace(/ (\d)/, ' $1')
export const modelFamily = (m: string) => /haiku/i.test(m) ? 'Haiku' : /sonnet/i.test(m) ? 'Sonnet' : /opus/i.test(m) ? 'Opus' : m
export const statusLabel: Record<string, string> = { answered: 'Answered', partial: 'Partial', abstain: 'Abstained', not_evaluated: 'Not evaluated' }
export const modeLabel: Record<string, string> = { single_report: 'Single report', multi_report: 'Multi-report', archive_wide: 'Archive-wide' }
export const flagLabel: Record<string, string> = {
  early_abstain: 'Early abstain', needs_clarification: 'Needs clarification', not_evaluated: 'Not evaluated', verifier_failed: 'Verifier failed',
  runs_disagree: 'Runs disagree', needs_review: 'Needs review', low_confidence: 'Low confidence', second_pass: 'Second pass', escalated: 'Escalated',
  arbitrated: 'Arbitrated', d1_fallback: 'Next-day fallback', context_truncated: 'Context truncated', xml_only_evidence: 'XML-only evidence', provider_fallback: 'Provider fallback',
}
export const shortReport = (stem: string) => stem.replace(/^15_9_/, '').replace(/_(\d{4})_(\d\d)_(\d\d)$/, ' · $1-$2-$3').replace(/_/g, '-')
export const wellShort = (w: string) => w.replace(/^15\/9-/, '')
export const catLabel: Record<string, string> = { single: 'Single report', compare: 'Compare reports', archive: 'Archive-wide', absent: 'Not in the archive' }
