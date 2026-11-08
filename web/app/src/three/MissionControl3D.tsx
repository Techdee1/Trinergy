import { useEffect, useMemo, useRef, useState } from 'react'
import { Check, CheckCircle2, Circle, FileText, Info, LocateFixed, SearchX, Square, X, Route as RouteIcon, Sigma } from 'lucide-react'
import type { ReplayTimeline, World } from '../lib/adapter'
import { recordToReport, viewAt } from '../lib/adapter'
import { AnswerResolve, KIND_ICON, NowCard, type ReplayApi } from '../components/Replay2D'
import { ICON, StatusBadge, VerifiedBadge } from '../components/ui'
import { int, wellShort } from '../lib/format'
import { Engine, type Hover } from './engine'
import './three.css'

/**
 * Mission control 3D. Contract (unchanged): draws `world`, follows `replay.idx` over `timeline.stages`, never fetches.
 * `onFallback` (optional) is called with a short reason when WebGL fails or the frame rate stays low; the parent flips back to 2D.
 */
export interface MissionControl3DProps { timeline: ReplayTimeline; world: World; replay: ReplayApi; onFallback?: (reason: string) => void }

export default function MissionControl3D({ timeline: tl, world, replay: r, onFallback }: MissionControl3DProps) {
  const host = useRef<HTMLDivElement>(null)
  const overlay = useRef<HTMLDivElement>(null)
  const wrap = useRef<HTMLDivElement>(null)
  const engine = useRef<Engine | null>(null)
  const [hover, setHover] = useState<{ h: Hover; x: number; y: number } | null>(null)
  const [picked, setPicked] = useState<string | null>(null)
  const [moved, setMoved] = useState(false)
  const v = useMemo(() => viewAt(tl, r.idx), [tl, r.idx])
  const stage = tl.stages[r.idx]
  const rec2rep = useMemo(() => recordToReport(tl), [tl])

  useEffect(() => {
    if (!host.current || !overlay.current) return
    let e: Engine
    try {
      e = new Engine(host.current, overlay.current, world, {
        onHover: (h, x, y) => setHover(h ? { h, x, y } : null),
        onPick: s => setPicked(s),
        onLowFps: fps => onFallback?.(`The 3D view ran at ${Math.round(fps)} frames per second on this machine, so the 2D replay is shown instead.`),
        onUserMove: m => setMoved(m),
      })
    } catch {
      onFallback?.('3D graphics (WebGL) are not available in this browser, so the 2D replay is shown instead.')
      return
    }
    engine.current = e
    ;(window as any).__wa3d = e
    const mo = new MutationObserver(() => e.applyTheme())
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => { mo.disconnect(); e.dispose(); engine.current = null }
  }, [world]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { engine.current?.apply(tl, r.idx, v, r.speed) }, [tl, r.idx, v, r.speed])
  useEffect(() => { engine.current?.pick(picked) }, [picked])

  // cited records travel from their node to the answer card (verify stage), as in 2D
  const flown = useRef('')
  useEffect(() => {
    if (stage?.kind !== 'verify' || !engine.current || !wrap.current || matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const key = tl.question + r.idx; if (flown.current === key) return; flown.current = key
    const root = wrap.current, layer = root.querySelector<HTMLElement>('.fly-layer'), anchor = root.querySelector<HTMLElement>('.answer-anchor')
    if (!layer || !anchor || !host.current) return
    const base = root.getBoundingClientRect(), hb = host.current.getBoundingClientRect(), to = anchor.getBoundingClientRect()
    ;[...v.citedReports].slice(0, 16).forEach((stem, i) => {
      const p = engine.current!.screenOf(stem); if (!p) return
      const x0 = hb.left - base.left + p.x, y0 = hb.top - base.top + p.y, x1 = to.left - base.left + 24 + i * 5, y1 = to.top - base.top + 24
      const dot = document.createElement('i'); dot.className = 'fly'; layer.appendChild(dot)
      const a = dot.animate([{ transform: `translate(${x0}px,${y0}px)`, opacity: 1 }, { transform: `translate(${(x0 + x1) / 2}px,${Math.min(y0, y1) - 60}px) scale(1.3)`, opacity: 1, offset: 0.5 }, { transform: `translate(${x1}px,${y1}px) scale(0.6)`, opacity: 0 }],
        { duration: 1200 / r.speed, delay: (300 + i * 120) / r.speed, easing: 'cubic-bezier(0.16,1,0.3,1)', fill: 'both' })
      a.onfinish = () => dot.remove()
    })
  }, [stage?.kind, r.idx]) // eslint-disable-line react-hooks/exhaustive-deps

  const d = tl.final
  const total = world.reportByStem.size
  const pn = picked ? engine.current?.layout.byStem.get(picked) ?? null : null
  const pickedRecords = useMemo(() => {
    if (!picked) return []
    const ctx = v.contexts[v.contexts.length - 1]
    return ctx ? ctx.records.filter(x => x.report === picked) : []
  }, [picked, v.contexts])
  const secondary = stage && ['escalate', 'second_pass', 'arbitrate'].includes(stage.kind)
  void rec2rep

  return (
    <div className="mc3-wrap" ref={wrap} style={{ ['--rs' as any]: r.speed }}>
      <div className="fly-layer" aria-hidden="true" />
      <ol className="stepper" aria-label="Pipeline stages">
        {tl.stages.map(s => {
          const same = tl.stages.filter(x => x.kind === s.kind)
          return <li key={s.index}><button className={'step ' + (s.index < r.idx ? 'done' : s.index === r.idx ? 'now' : 'todo')} onClick={() => r.goto(s.index)} aria-current={s.index === r.idx ? 'step' : undefined}>
            <span className="step-dot">{s.index < r.idx ? <Check {...ICON} size={12} /> : KIND_ICON[s.kind]}</span><span>{s.title}{same.length > 1 ? ` ${same.indexOf(s) + 1}` : ''}</span></button></li>
        })}
      </ol>
      <div className="mc">
        <section className="card flush mc3" aria-label="3D view of the archive: wells and reports">
          <div className="mc3-host" ref={host} />
          <div className="mc3-overlay" ref={overlay} aria-hidden="true" />
          <header className="mc3-q glass">
            <p className="t-14 mc3-qtext">{tl.question}</p>
            {v.parsed && v.router && <div className="chips parse on">
              {v.router.wells_named.map((w, i) => <span key={w} className="chip pop" style={{ ['--i' as any]: i }}>well <b className="mono">{w}</b></span>)}
              {v.router.dates_named.map((w, i) => <span key={w} className="chip pop" style={{ ['--i' as any]: i + 2 }}>date <b className="num">{w}</b></span>)}
              {v.router.date_range && <span className="chip pop">range <b className="num">{v.router.date_range.join(' → ')}</b></span>}
              {v.router.topics.map((w, i) => <span key={w} className="chip pop" style={{ ['--i' as any]: i + 4 }}>topic <b>{w}</b></span>)}
              {!v.router.wells_named.length && !v.router.dates_named.length && !v.router.date_range && <span className="chip pop">no well or date named</span>}
            </div>}
          </header>
          {secondary && <div className="mc3-banner badge flag" key={stage!.index}>{stage!.title}: {String(stage!.payload?.reason ?? '').slice(0, 120)}</div>}
          {v.absent.length > 0 && r.idx >= 0 && <div className="mc3-absent callout abstain" key={'abs' + r.idx}><SearchX {...ICON} /><div className="t-12">
            {v.absent.map(a => <p key={a.id}><b className="mono">{a.id}</b>: searched {a.reports_searched} report{a.reports_searched === 1 ? '' : 's'}, {a.records_searched} records. No “{a.kind}” field.</p>)}</div></div>}
          {hover && <div className="mc3-tip" style={{ transform: `translate(${hover.x + 14}px, ${hover.y + 14}px)` }} role="tooltip">
            {hover.h?.kind === 'node' ? <>
              <b className="mono">{hover.h.node.pdfFile}</b>
              <span>{hover.h.node.wellbore} · {hover.h.node.date} · {hover.h.node.records} records</span>
              <span className="faint">{hover.h.node.placement === 'survey' ? `Deepest survey that day: ${int(hover.h.node.md)} m MD, ${int(hover.h.node.tvd)} m TVD` : 'No depth in the data: placed in date order along the path'}</span>
              <span className="faint">Click to see its records</span>
            </> : hover.h?.kind === 'well' ? <><b className="mono">{hover.h.well.name}</b><span className="faint">Path from survey stations (approximate)</span></> : null}
          </div>}
          <div className="mc3-tools">
            <button className="btn sm glass" onClick={() => engine.current?.resetView(v)} disabled={!moved} title="Return to the choreographed camera"><LocateFixed {...ICON} size={14} />Reset view</button>
          </div>
          <footer className="mc3-foot glass">
            <div className="legend3">
              <span className="lg"><Circle {...ICON} size={12} fill="currentColor" />At surveyed depth</span>
              <span className="lg"><Circle {...ICON} size={12} />Placed by date (no depth)</span>
              <span className="lg route"><RouteIcon {...ICON} size={12} />Router-selected</span>
              <span className="lg ctx"><FileText {...ICON} size={12} />Context record</span>
              <span className="lg route"><Square {...ICON} size={12} />Aggregate</span>
              <span className="lg abstain"><SearchX {...ICON} size={12} />ABSENT</span>
              <span className="lg ok"><CheckCircle2 {...ICON} size={12} />Cited</span>
            </div>
            <p className="t-12 faint"><Info {...ICON} size={12} style={{ display: 'inline', verticalAlign: '-1px' }} /> Schematic surface layout. Well paths from survey data (approximate). Node tint: older reports darker, newer lighter.</p>
          </footer>
        </section>

        <aside className="mc-side">
          {pn ? (
            <div className="card now-card stack">
              <div className="row between"><div className="eyebrow">Report</div><button className="btn ghost iconbtn sm" aria-label="Close report" onClick={() => setPicked(null)}><X {...ICON} size={14} /></button></div>
              <h3 className="t-20 mono" style={{ fontWeight: 560 }}>{wellShort(pn.wellbore)} · {pn.date}</h3>
              <dl className="kv"><dt>File</dt><dd className="mono">{pn.pdfFile}</dd><dt>Records</dt><dd className="num">{pn.records}</dd><dt>Depth</dt><dd>{pn.placement === 'survey' ? `${int(pn.md)} m MD · ${int(pn.tvd)} m TVD (deepest survey that day)` : 'not in the data (placed by date)'}</dd></dl>
              {pickedRecords.length ? <div className="stack-2"><div className="eyebrow">In this question's context ({pickedRecords.length})</div>
                <div className="chips">{pickedRecords.slice(0, 40).map(x => <span key={x.id} className={'chip mono' + (v.citedIds.includes(x.id) ? ' cited' : '')}>{x.id}</span>)}{pickedRecords.length > 40 && <span className="chip">+{pickedRecords.length - 40}</span>}</div></div>
                : <p className="t-14 muted">{v.contexts.length ? 'The router did not open this report for this question, so none of its records are in the context.' : 'Records appear here once the context is built.'}</p>}
            </div>
          ) : (
            <div className="card now-card" aria-live="polite" key={stage?.index ?? -1}>
              {!stage ? <><div className="eyebrow">Ready</div><p className="t-16 muted" style={{ marginTop: 8 }}>Press play to watch the search move through the archive.</p></> : <NowCard stage={stage} v={v} total={total} />}
            </div>
          )}
          <div className={'card answer-mini' + (v.answered && d?.status === 'abstain' ? ' abstain' : '')}>
            <div className="answer-anchor" />
            <div className="card-title"><h3>Answer</h3>{v.answered && d && <StatusBadge status={d.status} flags={d.flags} />}</div>
            {v.citedIds.length > 0 && <div className="stack-2" style={{ marginBottom: 'var(--s-3)' }}><div className="eyebrow">Cited records</div>
              <div className="chips">{v.citedIds.slice(0, 6).map((id, i) => <span key={id} className="chip mono cite-in" style={{ ['--i' as any]: i }}>{id}</span>)}{v.citedIds.length > 6 && <span className="chip">+{v.citedIds.length - 6}</span>}</div></div>}
            {v.verifies.length > 0 && <div className="row-2" style={{ marginBottom: 'var(--s-3)' }}>{v.verifying ? <span className="badge ctx">Checking…</span> : <VerifiedBadge ok={v.verifies[v.verifies.length - 1].ok} />}</div>}
            {v.answered && d ? <AnswerResolve d={d} /> : <div className="stack-2"><div className="skeleton" style={{ height: 14, width: '80%' }} /><div className="skeleton" style={{ height: 14, width: '55%' }} /></div>}
            {v.aggregates.length > 0 && <p className="t-12 faint row-2" style={{ marginTop: 8 }}><Sigma {...ICON} size={12} />{v.aggregates.length} computed aggregate{v.aggregates.length > 1 ? 's' : ''} in context</p>}
          </div>
        </aside>
      </div>
    </div>
  )
}
