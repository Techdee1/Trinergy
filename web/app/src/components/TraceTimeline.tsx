import { Route as RouteIcon, FileText, Cpu, ShieldCheck, ArrowUpRight, RotateCw, Scale, Sigma, Check, Minus, Flag, DatabaseZap, Zap, SearchX, Sigma as Agg } from 'lucide-react'
import type { QuestionDetail, VerifyTrace } from '../api/types'
import { flagLabel, int, ms, modeLabel, modelFamily, shortReport, usd } from '../lib/format'
import { roleLabel } from '../lib/trace'
import { ContextBadge, ICON, RouterBadge } from './ui'

function Step({ icon, title, plain, meta, children, i }: { icon: React.ReactNode; title: string; plain: string; meta?: React.ReactNode; children?: React.ReactNode; i: number }) {
  return (
    <li className="tl-step rise" style={{ animationDelay: `${Math.min(i, 8) * 70}ms` }}>
      <span className="tl-node">{icon}</span>
      <div className="tl-body">
        <header className="row between" style={{ alignItems: 'flex-start' }}>
          <div className="stack-0"><h3 className="t-20">{title}</h3><p className="t-14 muted">{plain}</p></div>
          {meta && <div className="row-2 wrap" style={{ justifyContent: 'flex-end' }}>{meta}</div>}
        </header>
        {children}
      </div>
    </li>
  )
}

const resultIcon = (r: string) => r === 'pass' ? <Check {...ICON} size={14} /> : r === 'not_applicable' ? <Minus {...ICON} size={14} /> : <Flag {...ICON} size={14} />

function Verify({ v }: { v: VerifyTrace }) {
  const shown = v.checks.filter(c => c.result !== 'not_applicable')
  const na = v.checks.length - shown.length
  return (
    <div className="verify">
      <div className="row-2 wrap"><span className={'badge ' + (v.ok ? 'ok' : 'flag')}>{v.ok ? <ShieldCheck {...ICON} size={14} /> : <Flag {...ICON} size={14} />}{v.ok ? 'Passed' : 'Did not pass'}</span>
        <span className="t-12 faint">Checked: {v.target}</span></div>
      <ul className="checks">
        {shown.map((c, i) => (
          <li key={c.name} className={'check ' + c.result} style={{ animationDelay: `${250 + i * 90}ms` }}>
            <span className="tick">{resultIcon(c.result)}</span>
            <span className="t-14">{c.label}</span>
            {c.detail.length > 0 && <span className="t-12 faint check-detail">{c.detail.join(' · ')}</span>}
          </li>
        ))}
      </ul>
      {na > 0 && <p className="t-12 faint">{na} check{na > 1 ? 's' : ''} did not apply to this answer.</p>}
      {(v.failures.length > 0 || v.flags.length > 0) && <div className="callout flag"><Flag {...ICON} /><div className="t-14 stack-2">{[...v.failures, ...v.flags].map((m, i) => <p key={i}>{m}</p>)}</div></div>}
    </div>
  )
}

export function TraceTimeline({ d }: { d: QuestionDetail }) {
  const t = d.trace
  const r = t.router
  let i = 0
  return (
    <div className="stack-5">
      <ol className="timeline">
        <Step i={i++} icon={<RouteIcon {...ICON} size={18} />} title="Router" plain="Code reads the question and picks which daily reports to open. No model is involved."
          meta={<><RouterBadge>{modeLabel[r.mode] ?? r.mode}</RouterBadge><span className={'badge ' + (r.confidence.level === 'high' ? 'ok' : r.confidence.level === 'medium' ? 'abstain' : 'ctx')}>Routing confidence: {r.confidence.level}</span></>}>
          <p className="t-12 faint">{r.confidence.basis}</p>
          <p className="mono t-12 reason">{r.reason}</p>
          <div className="chips">
            {r.wells_named.map(w => <span key={w} className="chip">well <b className="mono">{w}</b></span>)}
            {r.dates_named.map(w => <span key={w} className="chip">date <b className="num">{w}</b></span>)}
            {r.date_range && <span className="chip">range <b className="num">{r.date_range.join(' → ')}</b></span>}
            {r.topics.map(w => <span key={w} className="chip">topic <b>{w}</b></span>)}
          </div>
          {r.wells_considered.length > 0 && <div className="chips">{r.wells_considered.map(w => <span key={w.well} className={'chip' + (w.in_archive ? '' : ' missing')}>{w.well}: {w.in_archive ? `${w.reports_available} reports in archive` : 'not in the archive'}</span>)}</div>}
          {r.reports_selected.length > 0 ? (
            <table className="table"><thead><tr><th>Selected report</th><th>Date</th><th>Why</th></tr></thead><tbody>
              {r.reports_selected.map(s => <tr key={s.report}><td><RouterBadge>{shortReport(s.report)}</RouterBadge></td><td className="num">{s.date}</td><td className="muted">{s.reason}</td></tr>)}</tbody></table>
          ) : <div className="callout abstain"><SearchX {...ICON} /><p className="t-14">No report matched, so nothing was opened and no model was called.</p></div>}
          {r.gate && <div className="callout abstain"><Flag {...ICON} /><p className="t-14">The clarification gate stopped this question before any model call: it names no well, date or field.</p></div>}
        </Step>

        {t.contexts.map(c => (
          <Step key={c.pass_name} i={i++} icon={<FileText {...ICON} size={18} />} title={c.pass_name === 'second_pass' ? 'Context, second pass' : 'Context'}
            plain="The evidence handed to the model: records from the selected reports, computed aggregates, and notes about fields that do not exist."
            meta={<>{c.final && <span className="badge ctx">Used for the answer</span>}{c.truncated && <span className="badge abstain">Truncated</span>}<span className="chip" title="Estimate: text length ÷ 4. Not a bill. The provider's exact counts are in the model calls below.">≈ <b className="num">{int(c.est_tokens)}</b> tokens (estimate)</span></>}>
            <div className="chips">
              <ContextBadge><span className="num">{c.records.length}</span> records</ContextBadge>
              {c.aggregates.length > 0 && <span className="badge route"><Agg {...ICON} size={14} /><span className="num">{c.aggregates.length}</span> computed aggregates</span>}
              {c.absent.length > 0 && <span className="badge abstain"><SearchX {...ICON} size={14} /><span className="num">{c.absent.length}</span> ABSENT record{c.absent.length > 1 ? 's' : ''}</span>}
            </div>
            {c.aggregates.map(a => <div key={a.id} className="agg"><span className="mono t-12">{a.id}</span><span className="t-14">{a.text}</span></div>)}
            {c.absent.map(a => <div key={a.id} className="agg absent"><span className="mono t-12">{a.id}</span><span className="t-14">Searched {a.reports_searched} report{a.reports_searched === 1 ? '' : 's'}, {a.records_searched} records. Field “{a.kind}” does not exist.</span></div>)}
            {c.notes.length > 0 && <ul className="t-12 faint notes">{c.notes.map((n, k) => <li key={k}>{n}</li>)}</ul>}
            <details className="more"><summary>All {c.records.length} records in context</summary><div className="chips" style={{ marginTop: 8 }}>{c.records.map(rr => <span key={rr.id} className={'chip mono' + (d.trace.cited.final.includes(rr.id) ? ' cited' : '')}>{rr.id}</span>)}</div></details>
          </Step>
        ))}

        {t.model_calls.length > 0 ? (
          <Step i={i++} icon={<Cpu {...ICON} size={18} />} title="Model calls" plain="A small model phrases the answer from the evidence. A larger one is called only when the verifier objects."
            meta={<><span className="chip"><b className="num">{t.totals.model_calls}</b> calls</span><span className="chip"><b className="num">{t.totals.cache_hits}</b> replayed from cache</span></>}>
            <div className="scroll-x"><table className="table"><thead><tr><th>#</th><th>Role</th><th>Model</th><th className="r">Prompt tokens</th><th className="r">Reply tokens</th><th className="r">Time</th><th className="r">Cost</th><th>Source</th></tr></thead><tbody>
              {t.model_calls.map(m => (
                <tr key={m.n}><td className="num">{m.n}</td><td>{roleLabel(m.role)}</td><td>{modelFamily(m.model)}</td>
                  <td className="r num">{int(m.prompt_tokens)}</td><td className="r num">{int(m.completion_tokens)}</td>
                  <td className="r num">{m.cache_hit ? 'replayed' : ms(m.latency_ms)}</td><td className="r num">{usd(m.cost_usd, 5)}</td>
                  <td>{m.cache_hit ? <span className="badge ctx"><DatabaseZap {...ICON} size={14} />Cache</span> : m.outcome === 'live' ? <span className="badge route"><Zap {...ICON} size={14} />Live</span> : <span className="badge ctx">{m.outcome}</span>}</td></tr>
              ))}</tbody></table></div>
            <p className="t-12 faint">Token counts are exactly what the provider reported. For cached calls they come from when the answer was first generated, and the cost is what that call cost then; this server paid {usd(t.totals.incurred_cost_usd)} now.</p>
          </Step>
        ) : <Step i={i++} icon={<Cpu {...ICON} size={18} />} title="No model call" plain="Code settled this question without asking a model." />}

        {t.verifier.length > 0 && (
          <Step i={i++} icon={<ShieldCheck {...ICON} size={18} />} title="Verifier" plain="Code re-checks every claim against the cited records: citations exist, numbers appear in them, abstentions cite only ABSENT records."
            meta={<span className="chip"><b className="num">{t.verifier.length}</b> run{t.verifier.length > 1 ? 's' : ''}</span>}>
            {t.verifier.map(v => <Verify key={v.n} v={v} />)}
          </Step>
        )}

        {t.escalations.length > 0 && (
          <Step i={i++} icon={<ArrowUpRight {...ICON} size={18} />} title="Escalation" plain="The verifier rejected the first draft or it was partial, so a larger model tried again with the same evidence.">
            {t.escalations.map(e => <div key={e.seq} className="agg"><span className="badge flag">{e.trigger}</span><span className="t-14">{modelFamily(e.model)}: {e.reason}</span></div>)}
          </Step>
        )}
        {t.second_pass.ran && (
          <Step i={i++} icon={<RotateCw {...ICON} size={18} />} title="Second pass" plain="The context was enriched once and the question was asked again." meta={<span className={'badge ' + (t.second_pass.used_for_answer ? 'ok' : 'ctx')}>{t.second_pass.used_for_answer ? 'Used for the answer' : 'Not used'}</span>}>
            <p className="t-14 muted">{t.second_pass.reason}</p>{t.second_pass.outcome && <p className="t-12 faint">{t.second_pass.outcome}</p>}
          </Step>
        )}
        {t.arbitration.ran && (
          <Step i={i++} icon={<Scale {...ICON} size={18} />} title="Arbitration" plain="Two drafts disagreed, so an arbiter picked the answer the evidence supports.">
            <p className="t-14 muted">{t.arbitration.outcome ?? 'Arbitration ran.'}</p>
          </Step>
        )}

        <Step i={i++} icon={<Sigma {...ICON} size={18} />} title="Totals" plain="What this question used end to end."
          meta={<span className="chip">wall time <b className="num">{ms(t.totals.wall_ms)}</b></span>}>
          <div className="totals">
            <div><span className="eyebrow">Model calls</span><b className="t-32 num">{t.totals.model_calls}</b></div>
            <div><span className="eyebrow">Prompt tokens</span><b className="t-32 num">{int(t.totals.prompt_tokens)}</b></div>
            <div><span className="eyebrow">Reply tokens</span><b className="t-32 num">{int(t.totals.completion_tokens)}</b></div>
            <div><span className="eyebrow">Cost when generated</span><b className="t-32 num">{usd(t.totals.generation_cost_usd)}</b></div>
            <div><span className="eyebrow">Paid now</span><b className="t-32 num">{usd(t.totals.incurred_cost_usd)}</b></div>
          </div>
          {t.decisions.length > 0 && <details className="more"><summary>Pipeline notes ({t.decisions.length})</summary><ul className="t-12 muted notes">{t.decisions.map((n, k) => <li key={k}>{n}</li>)}</ul></details>}
          {d.flags.length > 0 && <div className="chips">{d.flags.map(f => <span key={f} className="chip">{flagLabel[f] ?? f}</span>)}</div>}
        </Step>
      </ol>
    </div>
  )
}
