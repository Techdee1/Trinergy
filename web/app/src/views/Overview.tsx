import { Link } from 'react-router-dom'
import { Play, Search, MessageSquareText, ShieldCheck, MinusCircle, ArrowRight, Orbit, FileQuestion, Gauge } from 'lucide-react'
import { api } from '../api/client'
import { useAsync } from '../lib/hooks'
import { useHealth } from '../components/Shell'
import { CountUp } from '../components/CountUp'
import { ICON, PageHead, Section } from '../components/ui'
import { usd, usd2 } from '../lib/format'

const PRINCIPLES = [
  { icon: Search, title: 'Code finds the facts', body: 'A router and a record index locate the exact report, section and field. No model searches the archive.' },
  { icon: MessageSquareText, title: 'AI only phrases', body: 'A small model turns the evidence into a sentence. A larger one steps in only when a check fails.' },
  { icon: ShieldCheck, title: 'A verifier checks every claim', body: 'Code confirms each cited record exists and each number appears in it, before anything is shown.' },
  { icon: MinusCircle, title: 'Abstention is a valid answer', body: 'When the archive has no such field, the system says so and names exactly what it searched.' },
]
const STORIES = [
  { id: 'T2-016', title: 'The date-window trap', body: 'A report dated D covers D-1 to D. Pick the wrong day and the number is wrong.' },
  { id: 'T2-032', title: 'The Western Atlas trap', body: 'A logging company is in the report, but not a mud-logging one. The right answer is no.' },
  { id: 'T2-017', title: 'A multi-report sequence', body: 'Four reports across four wells, read in order to follow a rig move.' },
]

export default function Overview() {
  const health = useHealth()
  const qs = useAsync(() => api.questions(), [])
  const arch = useAsync(() => api.archive(), [])
  const costs = useAsync(() => api.costs(), [])
  const rows = qs.data?.questions ?? []
  const verified = rows.filter(r => r.status !== 'not_evaluated' && !r.flags.includes('verifier_failed')).length
  const answered = rows.filter(r => r.status === 'answered').length
  const abstained = rows.filter(r => r.status === 'abstain').length
  const c = costs.data
  return (
    <div className="page">
      <section className="hero rise">
        <div className="eyebrow">NAPE AICE 2026 · Track 2 · Intelligent Well Archive</div>
        <h1 className="t-64 hero-h">Ask the archive.<br />Get the evidence, or an honest <span className="no">“not here”</span>.</h1>
        <p className="lead">Thirty-two daily drilling reports, 1,783 records. Every answer cites the file, the page and the section it came from. When the archive cannot support an answer, the system says so instead of guessing.</p>
        <div className="row wrap" style={{ marginTop: 'var(--s-3)' }}>
          <Link className="btn primary lg" to="/mission/T2-017"><Play {...ICON} />Watch it work</Link>
          <Link className="btn lg" to="/questions"><FileQuestion {...ICON} />Browse all 72 answers</Link>
          <Link className="btn ghost lg" to="/ask">Ask your own<ArrowRight {...ICON} /></Link>
        </div>
      </section>

      <section className="counters rise rise-2" aria-label="Live from the archive">
        <div className="counter"><div className="eyebrow">Questions</div><div className="t-64 num"><CountUp to={rows.length || 72} /></div><div className="t-12 faint">32 challenge + 40 unseen</div></div>
        <div className="counter"><div className="eyebrow">Reports</div><div className="t-64 num"><CountUp to={arch.data?.reports.length ?? 32} /></div><div className="t-12 faint">{arch.data ? `${arch.data.wellbores.length} wellbores` : 'daily drilling reports'}</div></div>
        <div className="counter"><div className="eyebrow">Records indexed</div><div className="t-64 num"><CountUp to={health?.details.records ?? 1783} /></div><div className="t-12 faint">each with page and section</div></div>
        <div className="counter"><div className="eyebrow">Verified answers</div><div className="t-64 num"><CountUp to={verified} /><span className="t-24 faint"> / {rows.length || 72}</span></div><div className="t-12 faint">{answered} answered, {abstained} abstained</div></div>
        <div className="counter"><div className="eyebrow">Total cost</div><div className="t-64 num">{c ? <CountUp to={c.ledger.cost_usd} format={n => '$' + n.toFixed(2)} /> : '—'}</div>
          <div className="t-12 faint">{c ? `${usd(c.derived_from_cache.cost_per_challenge_question_usd)} per question · ` : ''}live cap {c ? usd2(c.budget.server_budget_usd) : '—'}</div></div>
      </section>

      <Section eyebrow="How it works" title="Four rules the system never breaks">
        <div className="grid principles">
          {PRINCIPLES.map((p, i) => (
            <div key={p.title} className={'card c-3 principle rise rise-' + (i + 1)}><span className="p-ico"><p.icon size={22} strokeWidth={1.6} /></span><h3 className="t-20">{p.title}</h3><p className="t-14 muted">{p.body}</p></div>
          ))}
        </div>
        <div className="flow card" aria-label="Pipeline">
          {['Question', 'Router', 'Evidence', 'Draft', 'Verifier', 'Answer or abstain'].map((s, i, a) => (
            <div key={s} className="flow-step"><span className="flow-dot num">{i + 1}</span><span className="t-14">{s}</span>{i < a.length - 1 && <i className="flow-line" />}</div>
          ))}
        </div>
      </Section>

      <Section eyebrow="Watch it work" title="Three runs worth watching" lead="Each replay is driven by the real trace: the reports the router opened, the records it gathered, and the checks that ran.">
        <div className="grid">
          {STORIES.map(s => (
            <Link key={s.id} to={`/mission/${s.id}`} className="card c-4 story">
              <span className="mono t-12 faint">{s.id}</span><h3 className="t-24">{s.title}</h3><p className="t-14 muted">{s.body}</p>
              <span className="story-go"><Orbit {...ICON} size={16} />Replay<ArrowRight {...ICON} size={16} /></span>
            </Link>
          ))}
        </div>
        <p className="t-14 faint row-2"><Gauge {...ICON} size={16} />Presenting? Open <Link className="link" to="/present">Presenter mode</Link> for a guided tour.</p>
      </Section>
    </div>
  )
}
