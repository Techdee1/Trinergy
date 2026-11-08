import { useMemo } from 'react'
import { api } from '../api/client'
import { useAsync } from '../lib/hooks'
import { ErrorState, Loading, PageHead, Section } from '../components/ui'
import { int, modelFamily, pct, usd, usd2 } from '../lib/format'
import { roleLabel } from '../lib/trace'

function Split({ label, parts }: { label: string; parts: { name: string; share: number; tone: string }[] }) {
  return (
    <div className="split" role="img" aria-label={`${label}: ${parts.map(p => `${p.name} ${pct(p.share)}`).join(', ')}`}>
      <span className="t-12 faint split-l">{label}</span>
      <div className="split-bar">{parts.map(p => <div key={p.name} style={{ width: pct(p.share), background: p.tone }}><span className="t-12 num">{p.name} {pct(p.share)}</span></div>)}</div>
    </div>
  )
}

export default function Cost() {
  const { data: c, error } = useAsync(() => api.costs(), [])
  const dots = useMemo(() => c ? [...c.per_question].sort((a, b) => a.cost_usd - b.cost_usd) : [], [c])
  if (error) return <div className="page"><ErrorState title="Could not load costs" body={error.message} /></div>
  if (!c) return <div className="page"><PageHead eyebrow="Cost" title="What each answer costs" /><Loading lines={5} /></div>
  const haiku = c.model_mix.find(m => /haiku/i.test(m.model)), others = c.model_mix.filter(m => m !== haiku)
  const tones = ['var(--route)', 'var(--flag)', 'var(--ctx)']
  const parts = (key: 'share_of_calls' | 'share_of_cost') => c.model_mix.map((m, i) => ({ name: modelFamily(m.model), share: m[key], tone: `color-mix(in srgb, ${tones[i % 3]} 35%, var(--surface-3))` }))
  const median = dots.length ? dots[Math.floor(dots.length / 2)].cost_usd : 0
  const max = dots.length ? dots[dots.length - 1].cost_usd : 1
  const cheap = dots.filter(d => d.cost_usd < 0.02).length
  const roles = Object.entries(c.by_role)
  const rmax = Math.max(...roles.map(([, v]) => v.cost_usd), 0.0001)
  const rep = c.cache_hit_rate.startup_replay
  const SW = 1000, SH = 260, PL = 56, PB = 28, PT = 12
  const x = (i: number) => PL + (i / Math.max(1, dots.length - 1)) * (SW - PL - 16), y = (v: number) => PT + (1 - v / (max * 1.08)) * (SH - PT - PB)
  const setShape = (s: string, cx: number, cy: number) => s === 'challenge' ? <circle cx={cx} cy={cy} r={4} className="d-ch" /> : s === 'unseen' ? <rect x={cx - 3.5} y={cy - 3.5} width={7} height={7} className="d-un" /> : <path d={`M${cx} ${cy - 5}L${cx + 5} ${cy}L${cx} ${cy + 5}L${cx - 5} ${cy}Z`} className="d-ad" />
  return (
    <div className="page">
      <PageHead eyebrow="Cost" title="Cheap by design" lead={haiku ? `A small model makes ${pct(haiku.share_of_calls)} of the calls and accounts for ${pct(haiku.share_of_cost)} of the cost. The larger model is called only when a check fails.` : undefined} />
      <div className="grid rise rise-1">
        <div className="card c-4"><div className="eyebrow">Challenge set, all calls</div><div className="t-64 num" style={{ margin: 'var(--s-2) 0' }}>{usd2(c.ledger.cost_usd)}</div><div className="t-14 muted"><span className="num">{usd(c.derived_from_cache.cost_per_challenge_question_usd, 4)}</span> per question · <span className="num">{int(c.ledger.calls)}</span> model calls</div>
          <div className="t-12 faint" style={{ marginTop: 'var(--s-3)' }}><span className="num">{int(c.ledger.prompt_tokens)}</span> prompt and <span className="num">{int(c.ledger.completion_tokens)}</span> reply tokens, as reported by the provider.</div></div>
        <div className="card c-8 stack"><div className="card-title" style={{ marginBottom: 0 }}><h3>Model mix</h3><span className="t-12 faint">share of all calls, then of all cost</span></div>
          <Split label="Calls" parts={parts('share_of_calls')} /><Split label="Cost" parts={parts('share_of_cost')} />
          <p className="t-12 faint">{c.model_mix.map(m => `${modelFamily(m.model)}: ${int(m.calls)} calls, ${usd2(m.cost_usd)}`).join(' · ')}</p></div>
      </div>

      <Section eyebrow="Per question" title={`${cheap} of ${dots.length} questions cost under two cents`} lead="One mark per question, cheapest to dearest. Shape tells the set. The line is the median.">
        <div className="card">
          <svg viewBox={`0 0 ${SW} ${SH}`} width="100%" role="img" aria-label={`Cost per question, median ${usd(median, 4)}, maximum ${usd(max, 4)}`}>
            {[0, 0.5, 1].map(f => { const v = max * f; return <g key={f}><line x1={PL} x2={SW - 16} y1={y(v)} y2={y(v)} className="gl" /><text x={PL - 8} y={y(v) + 4} textAnchor="end" className="ax-year">{usd(v, 3)}</text></g> })}
            <line x1={PL} x2={SW - 16} y1={y(median)} y2={y(median)} className="med" /><text x={SW - 20} y={y(median) - 6} textAnchor="end" className="med-t">median {usd(median, 4)}</text>
            {dots.map((d, i) => <g key={d.question_id + i}>{setShape(d.set, x(i), y(d.cost_usd))}<title>{d.question_id} · {usd(d.cost_usd, 5)} · {d.calls} calls</title></g>)}
            {dots.slice(-3).filter((_, i) => i !== 1).map((d, i) => <text key={d.question_id} x={x(dots.length - 3 + i) - 8} y={y(d.cost_usd) - 10 - (i % 2) * 0} textAnchor="end" className="ax-well">{d.question_id}</text>)}
            <text x={PL} y={SH - 6} className="ax-year">cheapest</text><text x={SW - 16} y={SH - 6} textAnchor="end" className="ax-year">dearest</text>
          </svg>
          <div className="row-2 t-12 muted" style={{ marginTop: 'var(--s-3)', gap: 'var(--s-5)' }}>
            <span className="row-2"><svg width="12" height="12"><circle cx="6" cy="6" r="4" className="d-ch" /></svg>Challenge</span>
            <span className="row-2"><svg width="12" height="12"><rect x="2.5" y="2.5" width="7" height="7" className="d-un" /></svg>Unseen</span>
            <span className="row-2"><svg width="12" height="12"><path d="M6 1L11 6L6 11L1 6Z" className="d-ad" /></svg>Asked live</span>
          </div>
        </div>
      </Section>

      <div className="grid" style={{ marginTop: 'var(--s-9)' }}>
        <div className="card c-5"><div className="card-title"><h3>Cost by role</h3><span className="t-12 faint">cost when generated</span></div>
          <div className="hbars">{roles.map(([k, v]) => <div key={k} className="hb" style={{ gridTemplateColumns: '150px 1fr 64px' }}><span className="t-12 muted">{roleLabel(k)} <span className="faint num">· {v.calls}</span></span><span className="bar"><i className="cur" style={{ width: `${(v.cost_usd / rmax) * 100}%`, background: k === 'escalation' ? 'var(--flag)' : 'var(--route)' }} /></span><b className="num t-12" style={{ textAlign: 'right' }}>{usd2(v.cost_usd)}</b></div>)}</div>
          <p className="t-12 faint" style={{ marginTop: 'var(--s-3)' }}>Counts after each name are calls.</p></div>
        <div className="card c-4 stack"><div className="eyebrow">Cache</div><div className="t-48 num">{rep?.hit_rate != null ? pct(rep.hit_rate) : '—'}</div>
          <p className="t-14 muted">of <span className="num">{rep?.model_calls ?? 0}</span> model lookups in the start-up replay of all 72 questions were answered from stored results, at no cost.</p>
          <p className="t-12 faint">Live questions since the server started: <span className="num">{c.cache_hit_rate.asks?.requests ?? 0}</span>.</p></div>
        <div className="card c-3 stack"><div className="eyebrow">Live budget</div><div className="t-48 num">{usd2(c.budget.remaining_usd)}</div>
          <span className="bar" style={{ height: 8 }}><i className="cur" style={{ width: pct(c.budget.spent_usd / c.budget.server_budget_usd), background: 'var(--abstain)', minWidth: 3 }} /></span>
          <p className="t-12 faint"><span className="num">{usd(c.budget.spent_usd, 4)}</span> spent of a <span className="num">{usd2(c.budget.server_budget_usd)}</span> cap. {c.budget.ask_live_enabled ? 'Live questions are on.' : 'Live questions are off.'}</p></div>
      </div>
    </div>
  )
}
