import { useUi } from '../lib/ui-state'
import { Sun, Moon, Search, Play, Route as RouteIcon } from 'lucide-react'
import { StatusBadge, VerifiedBadge, RouterBadge, ContextBadge, XmlOnlyBadge, FlagBadge, ICON, Stat } from '../components/ui'
import { Mark } from '../components/Mark'

const SWATCH = (v: string, name: string, note?: string) => (
  <div className="sg-sw"><i style={{ background: `var(${v})` }} /><div><b>{name}</b><span className="mono faint">{v}</span>{note && <span className="faint t-12">{note}</span>}</div></div>
)

export default function StyleGuide() {
  const { theme, toggleTheme } = useUi()
  return (
    <div className="page sg">
      <header className="page-head">
        <div className="eyebrow">Design system</div>
        <div className="row between"><h1 className="t-64">Style sheet</h1>
          <button className="btn" onClick={toggleTheme}>{theme === 'dark' ? <Sun {...ICON} /> : <Moon {...ICON} />}{theme === 'dark' ? 'Light' : 'Dark'} theme</button></div>
        <p className="lead">Tokens first. Heirs red marks action and selection (under 5% of any screen). Status has its own colours, each with an icon and a label.</p>
      </header>

      <section className="section"><header><div className="eyebrow">Colour</div><h2 className="t-32">Palette</h2>
        <p className="t-14 muted">Brand source: heirsenergies.com site CSS (#FE0000, #E61100) and Pillow extraction from the logo and favicon (dominant #F80000).</p></header>
        <div className="grid">
          <div className="card c-4 stack"><h3 className="t-16">Surfaces</h3>{SWATCH('--bg', 'Canvas')}{SWATCH('--surface-1', 'Surface 1', 'rail, cards')}{SWATCH('--surface-2', 'Surface 2', 'raised, inputs')}{SWATCH('--surface-3', 'Surface 3', 'hover, active')}</div>
          <div className="card c-4 stack"><h3 className="t-16">Text and lines</h3>{SWATCH('--text', 'Text', 'AA 15:1')}{SWATCH('--text-2', 'Text 2', 'AA 8:1')}{SWATCH('--text-3', 'Text 3', 'AA 5:1')}{SWATCH('--line-strong', 'Hairline')}</div>
          <div className="card c-4 stack"><h3 className="t-16">Brand (action only)</h3>{SWATCH('--brand', 'Heirs red', 'accent, rings')}{SWATCH('--brand-fill', 'Red fill', 'buttons, white text')}{SWATCH('--brand-text', 'Red text', 'AA on dark')}{SWATCH('--brand-soft', 'Red wash')}</div>
          <div className="card c-12"><h3 className="t-16" style={{ marginBottom: 16 }}>Status (never red for failure)</h3>
            <div className="row wrap" style={{ gap: 16 }}>
              <StatusBadge status="answered" /><VerifiedBadge ok /><StatusBadge status="abstain" /><RouterBadge>Router selected</RouterBadge><ContextBadge>Context record</ContextBadge><FlagBadge flag="needs_review" /><XmlOnlyBadge />
            </div>
            <div className="sg-status" style={{ marginTop: 24 }}>
              {SWATCH('--ok', 'Verified', 'green · check')}{SWATCH('--abstain', 'Abstain', 'amber · minus')}{SWATCH('--route', 'Router-selected', 'blue · route')}{SWATCH('--flag', 'Flag', 'violet · flag')}{SWATCH('--ctx', 'Context', 'neutral · file')}
            </div></div>
        </div>
      </section>

      <section className="section"><header><div className="eyebrow">Type</div><h2 className="t-32">Scale</h2>
        <p className="t-14 muted">Inter Variable for interface and display, JetBrains Mono for record IDs. Tight tracking when large, open when small. Tabular figures throughout.</p></header>
        <div className="card stack-5">
          {[['64', 't-64', 'Facts first'], ['48', 't-48', 'Evidence on every claim'], ['32', 't-32', 'The archive does not say'], ['24', 't-24', 'Verified against two records'], ['20', 't-20', 'Router selected 4 of 32 reports'], ['16', 't-16', 'Body text for explanation and reading.'], ['14', 't-14', 'Interface text, tables, controls.'], ['12', 't-12', 'Captions and metadata, 12 pt.']].map(([n, c, s]) => (
            <div className="sg-type" key={n}><span className="mono faint">{n}</span><span className={c}>{s}</span></div>
          ))}
          <div className="sg-type"><span className="mono faint">mono</span><span className="mono">F1C-20140326-FLUID-01 · 1.03 g/cm3 · 4,094 m MD</span></div>
          <div className="sg-type"><span className="mono faint">tnum</span><span className="num t-32">0.021696  1,783  72  $2.00</span></div>
        </div>
      </section>

      <section className="section"><header><div className="eyebrow">Space, shape, depth</div><h2 className="t-32">Foundations</h2></header>
        <div className="grid">
          <div className="card c-6"><h3 className="t-16" style={{ marginBottom: 16 }}>8 pt scale</h3>
            <div className="stack-2">{[4, 8, 16, 24, 32, 48, 64].map(n => <div className="row" key={n}><span className="mono faint" style={{ width: 32 }}>{n}</span><i className="sg-bar" style={{ width: n * 4 }} /></div>)}</div></div>
          <div className="card c-6"><h3 className="t-16" style={{ marginBottom: 16 }}>Radius family and elevation</h3>
            <div className="row" style={{ gap: 24, alignItems: 'flex-end' }}>
              {[['6', 'var(--r-1)'], ['10', 'var(--r-2)'], ['14', 'var(--r-3)']].map(([n, r]) => <div key={n} className="stack-2" style={{ justifyItems: 'center' }}><i className="sg-box" style={{ borderRadius: r }} /><span className="mono faint">{n}</span></div>)}
              <div className="stack-2" style={{ justifyItems: 'center' }}><i className="sg-box" style={{ boxShadow: 'var(--elev-1)' }} /><span className="mono faint">elev 1</span></div>
              <div className="stack-2" style={{ justifyItems: 'center' }}><i className="sg-box" style={{ boxShadow: 'var(--elev-2)' }} /><span className="mono faint">elev 2</span></div>
            </div></div>
          <div className="card c-12"><h3 className="t-16" style={{ marginBottom: 16 }}>12-column grid</h3>
            <div className="grid sg-cols">{Array.from({ length: 12 }, (_, i) => <i key={i}>{i + 1}</i>)}</div></div>
        </div>
      </section>

      <section className="section"><header><div className="eyebrow">Components</div><h2 className="t-32">Controls</h2></header>
        <div className="grid">
          <div className="card c-6 stack"><h3 className="t-16">Buttons</h3>
            <div className="row wrap"><button className="btn primary lg"><Play {...ICON} />Watch it work</button><button className="btn"><Search {...ICON} />Ask</button><button className="btn ghost">Ghost</button><button className="btn sm">Small</button><button className="btn" disabled>Disabled</button></div>
            <div className="row wrap"><div className="seg" role="group" aria-label="Demo"><button aria-pressed="true">2D</button><button aria-pressed="false">3D</button></div>
              <span className="chip interactive" aria-pressed="true"><b>Single report</b> 55</span><span className="chip interactive" aria-pressed="false">Abstained 15</span><span className="chip"><RouteIcon {...ICON} size={14} />15/9-F-1-C</span></div>
          </div>
          <div className="card c-6 stack"><h3 className="t-16">Input</h3>
            <label className="field">Question<input className="input" placeholder="What was the density of the NaCl brine on 15/9-F-1-C?" /></label>
          </div>
          <div className="card c-6 stack"><h3 className="t-16">Callouts</h3>
            <div className="callout abstain"><span className="faint">!</span><div><b>Abstain</b><p className="t-14 muted">The archive has no mud logging field. Searched 1 report, 50 records.</p></div></div>
            <div className="callout ok"><span className="faint">✓</span><div><b>Verified</b><p className="t-14 muted">Every number appears in a cited record.</p></div></div>
          </div>
          <div className="card c-6"><h3 className="t-16" style={{ marginBottom: 16 }}>Data</h3>
            <div className="grid" style={{ gridTemplateColumns: 'repeat(3,1fr)' }}><Stat label="Questions" value="72" /><Stat label="Records" value="1,783" /><Stat label="Cost" value="$0.65" sub="of $2.00" /></div>
            <hr className="rule" style={{ margin: '24px 0 8px' }} />
            <table className="table"><thead><tr><th>Record</th><th>Type</th><th className="r">Value</th></tr></thead><tbody>
              <tr><td className="mono">F1C-20140326-FLUID-01</td><td>fluid</td><td className="r num">1.03 g/cm3</td></tr>
              <tr><td className="mono">19A-19970829-LOG-01</td><td>log</td><td className="r num">—</td></tr></tbody></table></div>
        </div>
      </section>
      <section className="section"><header><div className="eyebrow">Brand</div><h2 className="t-32">Mark and icons</h2></header>
        <div className="card row" style={{ gap: 32 }}><Mark size={48} /><span className="t-14 muted">Product mark: a wellbore landing on a record. Icons: Lucide line set at one 1.6 stroke weight.</span></div></section>
    </div>
  )
}
