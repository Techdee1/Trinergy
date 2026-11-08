import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { FlaskConical, Info } from 'lucide-react'
import { api } from '../api/client'
import { useAsync } from '../lib/hooks'
import { ErrorState, ICON, Loading, PageHead, StatusBadge } from '../components/ui'
import { catLabel, pct } from '../lib/format'

function Pair({ label, n, cur, base }: { label: string; n: number; cur: number; base?: number }) {
  return (
    <div className="card pair">
      <div className="eyebrow">{label}</div>
      <div className="t-12 faint">{n} questions</div>
      <div className="pair-bars">
        {base != null && <div className="pbar"><span className="t-12 faint">Baseline</span><span className="bar"><i className="base" style={{ width: pct(base) }} /></span><b className="num t-14">{base.toFixed(2)}</b></div>}
        <div className="pbar"><span className="t-12">Current</span><span className="bar"><i className="cur" style={{ width: pct(cur) }} /></span><b className="num t-14">{cur.toFixed(2)}</b></div>
      </div>
    </div>
  )
}

export default function Generalisation() {
  const { data, error } = useAsync(() => api.generalisation(), [])
  const nav = useNavigate()
  const [cat, setCat] = useState<string | null>(null)
  const qs = data?.questions ?? []
  const shown = useMemo(() => qs.filter(q => !cat || q.category === cat), [qs, cat])
  // per-category baseline computed from the question rows (the summary only carries current scores)
  const baseByCat = useMemo(() => { const m: Record<string, number[]> = {}; qs.forEach(q => (m[q.category] ??= []).push(q.baseline_score)); return Object.fromEntries(Object.entries(m).map(([k, v]) => [k, v.reduce((a, b) => a + b, 0) / v.length])) }, [qs])
  if (error) return <div className="page"><ErrorState title="Could not load the unseen-question results" body={error.message} /></div>
  const s = data?.summary
  const later = s && (s as any).independent ? (s as any).independent : null
  return (
    <div className="page">
      <PageHead eyebrow="Generalisation" title="Forty questions it had not seen" lead="The pipeline was built against 32 challenge questions. These 40 unseen ones test whether the approach holds up on different wording, wells and traps." />
      {!data ? <Loading lines={5} /> : !data.available || !s ? <ErrorState title="Results are not available yet" body={data.message ?? 'The generalisation data file has not been built.'} /> : <>
        <div className="callout route rise" role="note"><FlaskConical {...ICON} /><div><b>Tuned on these questions; independent test in progress.</b>
          <p className="t-14 muted">The unseen set was used to fix failures, so these scores are not a clean held-out result. A separate test on questions nobody has seen is running.</p></div></div>

        <div className="grid gen-top rise rise-1" style={{ marginTop: 'var(--s-5)' }}>
          <div className="card c-4"><div className="eyebrow">Mean score, all {s.questions}</div>
            <div className="row" style={{ alignItems: 'baseline', gap: 'var(--s-3)', margin: 'var(--s-3) 0' }}><span className="t-64 num">{s.mean_score.toFixed(2)}</span><span className="t-14 faint">baseline <span className="num">{s.baseline_mean_score.toFixed(2)}</span></span></div>
            <div className="pbar"><span className="t-12 faint">Baseline</span><span className="bar"><i className="base" style={{ width: pct(s.baseline_mean_score) }} /></span></div>
            <div className="pbar"><span className="t-12">Current</span><span className="bar"><i className="cur" style={{ width: pct(s.mean_score) }} /></span></div>
            <p className="t-12 faint" style={{ marginTop: 'var(--s-3)' }}><Info {...ICON} size={12} style={{ display: 'inline', verticalAlign: '-1px' }} /> {s.scoring}</p></div>
          <div className="c-8 grid" style={{ gridTemplateColumns: 'repeat(4, minmax(0,1fr))', gap: 'var(--s-4)' }}>
            {Object.entries(s.by_category).map(([k, v]) => <Pair key={k} label={catLabel[k] ?? k} n={v.n} cur={v.mean_score} base={baseByCat[k]} />)}
          </div>
        </div>
        {later && <div className="card rise" style={{ marginTop: 'var(--s-5)' }}><div className="eyebrow">Independent test</div><div className="t-32 num">{Number(later.mean_score).toFixed(2)}</div><p className="t-14 muted">{later.questions} questions.</p></div>}

        <header className="row between" style={{ margin: 'var(--s-8) 0 var(--s-4)' }}>
          <h2 className="t-24">All {qs.length} questions</h2>
          <div className="chips" role="group" aria-label="Category">
            <button className="chip interactive" aria-pressed={!cat} onClick={() => setCat(null)}>All <span className="num faint">{qs.length}</span></button>
            {Object.keys(s.by_category).map(k => <button key={k} className="chip interactive" aria-pressed={cat === k} onClick={() => setCat(cat === k ? null : k)}>{catLabel[k] ?? k} <span className="num faint">{s.by_category[k].n}</span></button>)}
          </div>
        </header>
        <div className="card flush"><table className="table board"><thead><tr><th style={{ width: 80 }}>ID</th><th>Question</th><th style={{ width: 140 }}>Category</th><th style={{ width: 150 }}>Status</th><th className="r" style={{ width: 90 }}>Baseline</th><th className="r" style={{ width: 90 }}>Current</th></tr></thead>
          <tbody>{shown.map(q => (
            <tr key={q.id} className="link" onClick={() => nav(`/question/${q.id}`)}>
              <td><Link className="mono" to={`/question/${q.id}`} onClick={e => e.stopPropagation()}>{q.id}</Link></td>
              <td className="qcell"><div>{q.question}</div></td><td className="muted">{catLabel[q.category] ?? q.category}</td>
              <td><StatusBadge status={q.status} /></td><td className="r num muted">{q.baseline_score.toFixed(2)}</td>
              <td className="r num" style={{ fontWeight: 600 }}>{q.score.toFixed(2)}</td></tr>))}</tbody></table></div>
      </>}
    </div>
  )
}
