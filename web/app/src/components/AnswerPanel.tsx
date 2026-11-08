import { Link } from 'react-router-dom'
import { Info } from 'lucide-react'
import type { QuestionDetail } from '../api/types'
import { confidenceRule } from '../lib/trace'
import { flagLabel, modeLabel, usd } from '../lib/format'
import { EvidenceLens } from './EvidenceLens'
import { TraceTimeline } from './TraceTimeline'
import { FlagBadge, ICON, RouterBadge, Section, StatusBadge, VerifiedBadge } from './ui'

export function ConfidenceBar({ value, wide }: { value: number; wide?: boolean }) {
  return <span className={'confbar' + (wide ? ' wide' : '')} role="img" aria-label={`Confidence ${value.toFixed(2)} of 1`}><i style={{ width: `${value * 100}%` }} /></span>
}

export function AnswerPanel({ d, showTrace = true }: { d: QuestionDetail; showTrace?: boolean }) {
  const rule = confidenceRule(d)
  const abstain = d.status === 'abstain'
  const flags = d.flags.filter(f => !['needs_clarification', 'not_evaluated'].includes(f))
  return (
    <div className="stack-5">
      <div className="grid">
        <article className={'card c-8 answer-card' + (abstain ? ' abstain' : '')} aria-labelledby="ans-h">
          <div className="row-2 wrap" style={{ marginBottom: 'var(--s-4)' }}>
            <StatusBadge status={d.status} flags={d.flags} />{d.status !== 'not_evaluated' && <VerifiedBadge ok={d.verified} />}
            <RouterBadge>{modeLabel[d.router_mode] ?? d.router_mode}</RouterBadge>
            {flags.map(f => <FlagBadge key={f} flag={f} />)}
          </div>
          <h2 id="ans-h" className="eyebrow">{abstain ? 'The archive does not support an answer' : 'Answer'}</h2>
          <p className={'answer-text ' + ((d.answer?.length ?? 0) > 180 ? 't-20' : 't-32')}>{d.answer}</p>
          {d.rationale && <div className="stack-2" style={{ marginTop: 'var(--s-5)' }}><h3 className="eyebrow">Rationale</h3><p className="t-16 muted" style={{ maxWidth: '70ch' }}>{d.rationale}</p></div>}
          {d.evidence && <div className="stack-2" style={{ marginTop: 'var(--s-5)' }}><h3 className="eyebrow">Evidence string</h3><p className="mono t-12 muted" style={{ overflowWrap: 'anywhere' }}>{d.evidence}</p></div>}
        </article>
        <aside className="c-4 stack">
          <div className="card">
            <div className="eyebrow">Confidence</div>
            <div className="row" style={{ alignItems: 'baseline', gap: 'var(--s-3)', margin: 'var(--s-2) 0' }}>
              <span className="t-64 num">{d.confidence.toFixed(2)}</span><span className="t-14 faint">of 1.00</span>
            </div>
            <ConfidenceBar value={d.confidence} wide />
            <h3 className="t-16" style={{ marginTop: 'var(--s-4)' }}>{rule.headline}</h3>
            <p className="t-14 muted" style={{ marginTop: 4 }}>{rule.rule}</p>
          </div>
          <div className="card stack-2">
            <div className="eyebrow">Source of this answer</div>
            <p className="t-14 muted"><Info {...ICON} size={14} style={{ display: 'inline', verticalAlign: '-2px', marginRight: 6 }} />
              {d.source === 'cache' ? 'Replayed from stored model calls. Nothing was charged now.' : d.source === 'live' ? 'Generated live just now.' : d.source === 'mixed' ? 'Part stored, part generated live.' : 'Settled by code. No model call was made.'}
              {d.trace.totals.incurred_cost_usd > 0 && <> Paid now: <span className="num">{usd(d.trace.totals.incurred_cost_usd)}</span>.</>}</p>
          </div>
        </aside>
      </div>

      <Section eyebrow="Evidence" title="Evidence lens" lead="The cited records, on the page they came from. Boxes mark the row, value or heading that supports the answer.">
        <EvidenceLens records={d.cited_records} contexts={d.trace.contexts} />
      </Section>

      {showTrace && <Section eyebrow="Trace" title="How it got there" lead="Every stage below was observed from the pipeline's real calls, in the order it happened.">
        <TraceTimeline d={d} />
      </Section>}
    </div>
  )
}

export const QLink = ({ id }: { id: string }) => <Link className="mono" to={`/question/${id}`}>{id}</Link>
export const flagText = (f: string) => flagLabel[f] ?? f
