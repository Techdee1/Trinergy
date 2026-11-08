import { useState } from 'react'
import { BookOpenCheck, Compass, FileSearch, Landmark, Building2, Layers, ShieldCheck, Wrench, Cloud, KeyRound, Cpu, Info } from 'lucide-react'
import { ICON, PageHead, Section } from '../components/ui'

const USES = [
  { icon: FileSearch, title: 'Well-history lookup', body: 'A drilling engineer asks for a casing depth, mud weight or kick-off point and gets the figure with its page, not a folder of PDFs.' },
  { icon: Compass, title: 'Offset-well review', body: 'Before planning a well, compare what neighbouring wells actually did: hole problems, mud programs, rig moves.' },
  { icon: ShieldCheck, title: 'Data-integrity attestation', body: 'Trace every figure submitted to the NUPRC National Data Repository back to a source document and page.' },
  { icon: Wrench, title: 'Abandonment and reactivation', body: 'Dormant wells need their full history: what was set, what failed, what was left in the hole.' },
  { icon: BookOpenCheck, title: 'Handover and onboarding', body: 'New engineers learn an asset by asking it questions, with answers they can check themselves.' },
]
const ROAD = [
  { when: 'Today', title: 'Volve prototype', body: '32 daily reports. Evidence-cited answers, verifier, abstention.' },
  { when: 'Next', title: 'Pilot on Heirs reports', body: 'Index a small set of real daily reports. Same pipeline, measured on Heirs engineers\' own questions.' },
  { when: 'Then', title: 'More document types', body: 'Completion reports, well tests and surveys, each with page-level evidence.' },
  { when: 'Later', title: 'Across the asset base', body: 'One searchable, auditable memory for the whole well stock.' },
]

export default function Impact() {
  const [eng, setEng] = useState(20), [hrs, setHrs] = useState(3), [rate, setRate] = useState(60)
  const weekly = eng * hrs, annual = weekly * 52 * rate
  const fmt = (n: number) => '$' + Math.round(n).toLocaleString('en-US')
  return (
    <div className="page">
      <PageHead eyebrow="Impact for Heirs" title="Well history you can trust, in seconds" lead="Decades of well knowledge sit in legacy reports. This turns them into answers that carry their own proof." />

      <div className="grid rise rise-1">
        <div className="card c-7 stack">
          <div className="eyebrow">The problem</div>
          <h2 className="t-32">The answer exists. Finding it, and proving it, is the cost.</h2>
          <p className="t-16 muted" style={{ maxWidth: '60ch' }}>Well history is spread across daily reports, scanned PDFs and exports. Engineers search by hand, and nobody can easily show where a number came from. Operators also attest to the integrity of the data they submit to the NUPRC National Data Repository (NDR), so every figure needs a traceable source.</p>
        </div>
        <div className="card c-5 stack fact">
          <div className="eyebrow">Why it matters at Heirs</div>
          <div className="stack-2"><div className="t-48 num">2×</div><p className="t-14 muted">OML 17 doubled its output without new wells, and about 100 dormant wells were reactivated. <span className="faint">(Company-reported.)</span></p></div>
          <p className="t-14 muted">That kind of work depends on knowing exactly what each older well went through.</p>
        </div>
      </div>

      <Section eyebrow="Use cases" title="Five places it earns its keep">
        <div className="grid">
          {USES.map((u, i) => <div key={u.title} className={'card c-4 stack-2 rise rise-' + ((i % 4) + 1)} style={i >= 3 ? { gridColumn: 'span 6' } : undefined}><span className="p-ico"><u.icon size={20} strokeWidth={1.6} /></span><h3 className="t-20">{u.title}</h3><p className="t-14 muted">{u.body}</p></div>)}
        </div>
      </Section>

      <Section eyebrow="Deployment" title="Runs where Heirs wants it">
        <div className="grid">
          <div className="card c-4 stack-2"><span className="p-ico"><Building2 size={20} strokeWidth={1.6} /></span><h3 className="t-20">Inside Heirs</h3><p className="t-14 muted">The archive index and the page images stay on Heirs infrastructure. Questions never need to leave the building.</p></div>
          <div className="card c-4 stack-2"><span className="p-ico"><Cpu size={20} strokeWidth={1.6} /></span><h3 className="t-20">Swappable model</h3><p className="t-14 muted">The model only phrases the evidence. It can be replaced by another provider or a self-hosted one, and the verifier is unchanged.</p></div>
          <div className="card c-4 stack-2"><span className="p-ico"><KeyRound size={20} strokeWidth={1.6} /></span><h3 className="t-20">Works without a model</h3><p className="t-14 muted">Retrieval, evidence pages and stored answers run fully offline. A model is needed only for new questions.</p></div>
        </div>
      </Section>

      <Section eyebrow="Roadmap" title="Proposed path">
        <ol className="road">{ROAD.map((r, i) => <li key={r.title} className="card stack-2"><span className="eyebrow">{r.when}</span><h3 className="t-20">{r.title}</h3><p className="t-14 muted">{r.body}</p></li>)}</ol>
        <p className="t-12 faint">Proposal for discussion, not a commitment.</p>
      </Section>

      <Section eyebrow="Value" title="What time saved could be worth" lead="Change the three inputs. The result is simple arithmetic on your numbers.">
        <div className="grid">
          <div className="card c-6 stack">
            <label className="field">Engineers who search well history<input className="input" type="number" min={1} max={500} value={eng} onChange={e => setEng(Math.max(0, +e.target.value))} /></label>
            <label className="field">Hours saved per engineer per week<input className="input" type="number" min={0} max={40} step={0.5} value={hrs} onChange={e => setHrs(Math.max(0, +e.target.value))} /></label>
            <label className="field">Loaded cost per hour (USD)<input className="input" type="number" min={0} max={1000} value={rate} onChange={e => setRate(Math.max(0, +e.target.value))} /></label>
          </div>
          <div className="card c-6 stack calc-out">
            <div className="eyebrow">Illustrative, not measured</div>
            <div><div className="t-64 num">{fmt(annual)}</div><div className="t-14 muted">per year</div></div>
            <div className="row" style={{ gap: 'var(--s-6)' }}><div><div className="t-32 num">{weekly.toLocaleString('en-US')}</div><div className="t-12 faint">hours per week</div></div><div><div className="t-32 num">{(weekly * 52).toLocaleString('en-US')}</div><div className="t-12 faint">hours per year</div></div></div>
            <p className="t-12 faint"><Info {...ICON} size={12} style={{ display: 'inline', verticalAlign: '-1px' }} /> {eng} engineers × {hrs} h × 52 weeks × ${rate}. Nobody has measured these inputs at Heirs. Replace them with your own.</p>
          </div>
        </div>
      </Section>
    </div>
  )
}
