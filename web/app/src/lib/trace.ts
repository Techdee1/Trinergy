import type { QuestionDetail } from '../api/types'

/** Plain-language statement of verify.confidence() for this answer. The numbers are the rule's own (submission/archive_qa/verify.py). */
export function confidenceRule(d: QuestionDetail): { headline: string; rule: string } {
  const t = d.trace
  const real = d.cited_records.filter(c => c.evidence.kind !== 'absent').length
  const absent = d.cited_records.some(c => c.evidence.kind === 'absent')
  const c = d.confidence
  if (d.status === 'not_evaluated') return { headline: 'No score', rule: 'This question was not evaluated, so there is no answer and no confidence.' }
  if (t.router.early_abstain) return { headline: 'Report not in the archive', rule: 'The question names a well or date that no report covers. Abstaining is certain here, so code scores it 0.90 without calling a model.' }
  if (!d.verified) return { headline: 'Verifier failed', rule: 'The verifier rejected the answer, so code caps confidence at 0.20.' }
  if (d.status === 'abstain') return { headline: absent ? 'Field is absent from the report' : 'Abstained', rule: absent ? 'The report exists but has no such field. A cited ABSENT record backs the abstention: code scores it 0.85.' : 'Abstained without an ABSENT record: code scores it 0.75.' }
  if (d.status === 'partial') return { headline: 'Partial answer', rule: `Partial answers score 0.40, plus 0.10 per extra cited record up to 0.60. Here: ${real} cited.` }
  const mode = d.router_mode
  const base = real <= 1 ? (mode === 'single_report' ? '0.95 for one record from one report (0.90 across several reports)' : '0.90 for one record') : real <= 3 ? '0.80 for two or three records' : '0.70 for four or more records'
  return { headline: `${real} cited record${real === 1 ? '' : 's'}, verified`, rule: `Code, not the model, sets this: ${base}${t.contexts.some(x => x.truncated) ? ', minus 0.05 because the context was truncated' : ''}. Score ${c.toFixed(2)}.` }
}

export const STAGE_LABEL: Record<string, string> = {
  route: 'Router', gate: 'Clarification gate', context_built: 'Context', aggregates_added: 'Aggregates', second_pass: 'Second pass',
  escalate: 'Escalation', arbitrate: 'Arbitration', model_call: 'Model call', verify: 'Verifier', warning: 'Warning', result: 'Result',
}

export const roleLabel = (r: string) => ({ primary: 'First draft', primary_run2: 'Second draft', primary_retry: 'Retry', primary_run2_retry: 'Retry (second draft)', escalation: 'Escalation', arbiter: 'Arbiter' } as Record<string, string>)[r] ?? r
