import { useEffect, useMemo, useRef } from 'react'
import { Link } from 'react-router-dom'
import { Check, CheckCircle2, Flag, Minus, Route as RouteIcon, SearchX, ShieldCheck, Pause, Play, RotateCcw, SkipBack, SkipForward, Gauge, ArrowUpRight, Scale, RotateCw, HelpCircle, ScanText, Cpu, FileText, MessageSquareQuote, ListChecks } from 'lucide-react'
import { buildWorld, draftLabel, viewAt, type ReplayStage, type ReplayTimeline, type World } from '../lib/adapter'
import { modeLabel, int, shortReport, wellShort } from '../lib/format'
import { roleLabel } from '../lib/trace'
import { prefersReducedMotion } from '../lib/hooks'
import type { QuestionDetail } from '../api/types'
import { ConfidenceBar } from './AnswerPanel'
import { ICON, RouterBadge, StatusBadge, VerifiedBadge } from './ui'
import { confidenceRule } from '../lib/trace'

export type ReplayApi = ReturnType<typeof import('../lib/useReplay').useReplay>

const KIND_ICON: Record<string, React.ReactNode> = {
  parse: <ScanText {...ICON} size={16} />, route: <RouteIcon {...ICON} size={16} />, gate: <HelpCircle {...ICON} size={16} />, context: <FileText {...ICON} size={16} />,
  draft: <Cpu {...ICON} size={16} />, verify: <ShieldCheck {...ICON} size={16} />, second_pass: <RotateCw {...ICON} size={16} />, escalate: <ArrowUpRight {...ICON} size={16} />,
  arbitrate: <Scale {...ICON} size={16} />, answer: <MessageSquareQuote {...ICON} size={16} />,
}

export function ReplayControls({ r, label }: { r: ReplayApi; label?: string }) {
  const done = r.idx >= r.last && r.last >= 0
  return (
    <div className="controls glass" role="group" aria-label="Replay controls">
      <div className="row-2">
        <button className="btn ghost iconbtn" aria-label="Previous stage" onClick={() => r.step(-1)} disabled={r.idx < 0}><SkipBack {...ICON} /></button>
        {r.playing
          ? <button className="btn primary iconbtn" aria-label="Pause" onClick={r.pause}><Pause {...ICON} /></button>
          : <button className="btn primary iconbtn" aria-label={done ? 'Play again' : 'Play'} onClick={r.play}><Play {...ICON} /></button>}
        <button className="btn ghost iconbtn" aria-label="Next stage" onClick={() => r.step(1)} disabled={r.idx >= r.last}><SkipForward {...ICON} /></button>
        <button className="btn ghost sm" onClick={r.replay}><RotateCcw {...ICON} size={14} />Replay</button>
      </div>
      <div className="progress" aria-hidden="true"><i style={{ width: r.last < 0 ? 0 : `${((r.idx + 1) / (r.last + 1)) * 100}%` }} /></div>
      <span className="t-12 muted num" aria-live="polite">{label ?? (r.idx < 0 ? 'Ready' : `Stage ${r.idx + 1} of ${r.last + 1}`)}</span>
      <button className="btn sm" onClick={r.cycleSpeed} aria-label={`Speed ${r.speed}x. Change speed`}><Gauge {...ICON} size={14} /><span className="num">{r.speed}×</span></button>
    </div>
  )
}

export function Replay2D({ tl, world, r, live }: { tl: ReplayTimeline; world: World; r: ReplayApi; live?: boolean }) {
  const wrap = useRef<HTMLDivElement>(null)
  const v = useMemo(() => viewAt(tl, r.idx), [tl, r.idx])
  const stage: ReplayStage | undefined = tl.stages[r.idx]
  const kind = stage?.kind
  const reach = (k: string) => tl.stages.slice(0, r.idx + 1).some(s => s.kind === k)
  const absentSearch = v.absent.length > 0
  const selList = [...v.selected]
  const total = world.reportByStem.size

  // cited records travel from their report node to the answer card (skipped for reduced motion)
  const flown = useRef<string>('')
  useEffect(() => {
    if (kind !== 'draft' || !wrap.current || prefersReducedMotion()) return
    const key = tl.question + ':' + r.idx
    if (flown.current === key) return
    flown.current = key
    const root = wrap.current, layer = root.querySelector<HTMLElement>('.fly-layer'), anchor = root.querySelector<HTMLElement>('.answer-anchor')
    if (!layer || !anchor) return
    const base = root.getBoundingClientRect(), to = anchor.getBoundingClientRect()
    ;[...v.citedReports].forEach((stem, i) => {
      const n = root.querySelector<HTMLElement>(`[data-stem="${CSS.escape(stem)}"]`); if (!n) return
      const a = n.getBoundingClientRect()
      const dot = document.createElement('i'); dot.className = 'fly'; layer.appendChild(dot)
      const x0 = a.left - base.left + a.width / 2, y0 = a.top - base.top + a.height / 2
      const x1 = to.left - base.left + 24 + i * 6, y1 = to.top - base.top + 24
      const anim = dot.animate([{ transform: `translate(${x0}px,${y0}px) scale(1)`, opacity: 1 }, { transform: `translate(${(x0 + x1) / 2}px,${Math.min(y0, y1) - 40}px) scale(1.4)`, opacity: 1, offset: 0.5 }, { transform: `translate(${x1}px,${y1}px) scale(0.6)`, opacity: 0 }],
        { duration: 1100 / r.speed, delay: (i * 140) / r.speed, easing: 'cubic-bezier(0.16,1,0.3,1)', fill: 'both' })
      anim.onfinish = () => dot.remove()
    })
  }, [kind, r.idx]) // eslint-disable-line react-hooks/exhaustive-deps

  const d = tl.final
  return (
    <div className="mc" ref={wrap} style={{ ['--rs' as any]: r.speed }} data-stage={kind ?? 'idle'}>
      <div className="fly-layer" aria-hidden="true" />
        <ol className="stepper" aria-label="Pipeline stages">
          {tl.stages.length === 0 && <li className="faint t-14">Waiting for the first stage…</li>}
          {tl.stages.map(s => (
            <li key={s.index}><button className={'step ' + (s.index < r.idx ? 'done' : s.index === r.idx ? 'now' : 'todo')} onClick={() => r.goto(s.index)} aria-current={s.index === r.idx ? 'step' : undefined}>
              <span className="step-dot">{s.index < r.idx ? <Check {...ICON} size={12} /> : KIND_ICON[s.kind]}</span><span>{s.title}{(() => { const same = tl.stages.filter(x => x.kind === s.kind); return same.length > 1 ? ` ${same.indexOf(s) + 1}` : '' })()}</span></button></li>
          ))}
          {live && !tl.complete && <li className="faint t-12 step-wait"><span className="dot pulse" /> receiving stages…</li>}
        </ol>
      <section className="mc-canvas card flush" aria-label="Archive map">
        <header className="mc-q">
          <div className="eyebrow">Question</div>
          <p className="t-16 mc-qtext">{tl.question}</p>
          <div className={'chips parse' + (v.parsed ? ' on' : '')} aria-live="polite">
            {v.parsed && v.router && <>
              {v.router.wells_named.map((w, i) => <span key={w} className="chip pop" style={{ ['--i' as any]: i }}>well <b className="mono">{w}</b></span>)}
              {v.router.dates_named.map((w, i) => <span key={w} className="chip pop" style={{ ['--i' as any]: i + 2 }}>date <b className="num">{w}</b></span>)}
              {v.router.date_range && <span className="chip pop" style={{ ['--i' as any]: 3 }}>range <b className="num">{v.router.date_range.join(' → ')}</b></span>}
              {v.router.topics.map((w, i) => <span key={w} className="chip pop" style={{ ['--i' as any]: i + 4 }}>topic <b>{w}</b></span>)}
              {!v.router.wells_named.length && !v.router.dates_named.length && !v.router.date_range && <span className="chip pop">no well or date named</span>}
            </>}
          </div>
        </header>
        <div className="lanes" role="list" style={{ ['--cols' as any]: world.maxOrdinal }}>
          {world.wellbores.map(wb => {
            const cand = v.routed && v.candidates.has(wb.name)
            const dim = v.routed && !cand
            return (
              <div key={wb.name} role="listitem" className={'lane' + (cand ? ' cand' : '') + (dim ? ' dim' : '')}>
                <div className="lane-label mono">{wellShort(wb.name)}</div>
                <div className="lane-track">
                  {wb.reports.map(rep => {
                    const sel = v.selected.has(rep.stem)
                    const cited = v.citedReports.has(rep.stem)
                    const ctx = v.contextCount.get(rep.stem) ?? 0
                    const sweeping = sel && reach('context') && kind === 'context' && absentSearch
                    const swept = sel && absentSearch && reach('context') && !cited
                    const ord = selList.indexOf(rep.stem)
                    return (
                      <div key={rep.stem} data-stem={rep.stem} tabIndex={-1}
                        className={'node' + (sel ? ' sel' : v.routed ? ' off' : '') + (ctx ? ' ctx' : '') + (cited ? ' cited' : '') + (sweeping ? ' sweep' : '') + (swept ? ' swept' : '')}
                        style={{ ['--i' as any]: Math.max(0, ord) }} title={`${rep.stem} · ${rep.records} records`}>
                        <span className="node-ico">{cited ? <CheckCircle2 {...ICON} size={14} /> : swept ? <SearchX {...ICON} size={14} /> : sel ? <RouteIcon {...ICON} size={14} /> : null}</span>
                        <span className="node-date num">{rep.date}</span>
                        <span className="node-sub num">{ctx ? `${ctx} in context` : `${rep.records} records`}</span>
                      </div>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </div>
        <footer className="legend" aria-label="Legend">
          <span className="lg route"><RouteIcon {...ICON} size={14} />Router-selected</span>
          <span className="lg ctx"><FileText {...ICON} size={14} />Context records</span>
          <span className="lg ok"><CheckCircle2 {...ICON} size={14} />Cited</span>
          <span className="lg abstain"><SearchX {...ICON} size={14} />Searched, not found</span>
          <span className="faint t-12" style={{ marginLeft: 'auto' }}>{world.wellbores.length} wellbores · {total} reports · each lane runs oldest to newest</span>
        </footer>
      </section>

      <aside className="mc-side">

        <div className="card now-card" aria-live="polite" key={stage?.index ?? -1}>
          {!stage ? <><div className="eyebrow">Ready</div><p className="t-16 muted" style={{ marginTop: 8 }}>Press play to watch the archive answer this question, one stage at a time.</p></> : <NowCard stage={stage} v={v} total={total} />}
        </div>

        <div className={'card answer-mini' + (v.answered && d?.status === 'abstain' ? ' abstain' : '')}>
          <div className="answer-anchor" />
          <div className="card-title"><h3>Answer</h3>{v.answered && d && <StatusBadge status={d.status} flags={d.flags} />}</div>
          {v.citedIds.length > 0 && <div className="stack-2" style={{ marginBottom: 'var(--s-3)' }}><div className="eyebrow">Cited records</div>
            <div className="chips">{v.citedIds.slice(0, 8).map((id, i) => <span key={id} className="chip mono cite-in" style={{ ['--i' as any]: i }}>{id}</span>)}{v.citedIds.length > 8 && <span className="chip">+{v.citedIds.length - 8}</span>}</div></div>}
          {v.verifies.length > 0 && <div className="row-2" style={{ marginBottom: 'var(--s-3)' }}>{v.verifying ? <span className="badge ctx">Checking…</span> : <VerifiedBadge ok={v.verifies[v.verifies.length - 1].ok} />}</div>}
          {v.answered && d ? <AnswerResolve d={d} /> : <div className="stack-2"><div className="skeleton" style={{ height: 14, width: '80%' }} /><div className="skeleton" style={{ height: 14, width: '55%' }} /></div>}
        </div>
      </aside>
    </div>
  )
}

function AnswerResolve({ d }: { d: QuestionDetail }) {
  const rule = confidenceRule(d)
  return (
    <div className="stack resolve">
      <p className={d.answer.length > 140 ? 't-16' : 't-24'} style={{ fontWeight: 560, letterSpacing: 'var(--tr-20)', overflowWrap: 'anywhere' }}>{d.answer.length > 240 ? d.answer.slice(0, 240).trimEnd() + '…' : d.answer}</p>
      <div className="row-2"><span className="t-32 num">{d.confidence.toFixed(2)}</span><div className="grow"><ConfidenceBar value={d.confidence} wide /><span className="t-12 faint">{rule.headline}</span></div></div>
      <Link className="btn sm" to={`/question/${d.id}`} style={{ justifySelf: 'start' }}>Open evidence and full trace</Link>
    </div>
  )
}

function NowCard({ stage, v, total }: { stage: ReplayStage; v: ReturnType<typeof viewAt>; total: number }) {
  const p = stage.payload
  return (
    <div className="stack">
      <div className="row-2"><span className="step-dot big">{KIND_ICON[stage.kind]}</span><div className="stack-0"><h3 className="t-20">{stage.title}</h3></div></div>
      <p className="t-14 muted">{stage.plain}</p>
      {stage.kind === 'parse' && <dl className="kv"><dt>Wells</dt><dd className="mono">{p.wells_named.join(', ') || 'none named'}</dd><dt>Dates</dt><dd className="num">{p.dates_named.join(', ') || (p.date_range ? p.date_range.join(' → ') : 'none named')}</dd><dt>Topics</dt><dd>{p.topics.join(', ') || 'none'}</dd></dl>}
      {stage.kind === 'route' && <>
        <div className="row-2 wrap"><RouterBadge>{modeLabel[p.mode] ?? p.mode}</RouterBadge><span className={'badge ' + (p.confidence.level === 'high' ? 'ok' : p.confidence.level === 'medium' ? 'abstain' : 'ctx')}>Routing confidence: {p.confidence.level}</span></div>
        <div className="big-count"><b className="num">{p.reports_selected.length}</b><span>of {total} reports opened</span></div>
        <p className="mono t-12 reason">{p.reason}</p></>}
      {stage.kind === 'gate' && <><p className="t-14">{p.message}</p>{p.examples?.length > 0 && <p className="t-12 faint">Three answered examples are offered to try instead.</p>}</>}
      {stage.kind === 'context' && <>
        <div className="chips"><span className="badge ctx"><FileText {...ICON} size={14} /><span className="num">{p.records.length}</span> records</span>
          {p.aggregates.length > 0 && <span className="badge route"><span className="num">{p.aggregates.length}</span> computed aggregates</span>}
          {p.absent.length > 0 && <span className="badge abstain"><SearchX {...ICON} size={14} />ABSENT</span>}</div>
        {p.aggregates.slice(0, 3).map((a: any) => <div key={a.id} className="agg"><span className="mono t-12">{a.id}</span><span className="t-12">{a.text.length > 140 ? a.text.slice(0, 140) + '…' : a.text}</span></div>)}
        {p.absent.map((a: any) => <div key={a.id} className="agg absent sweep-in"><span className="mono t-12">{a.id}</span><span className="t-14">Searched {a.reports_searched} report{a.reports_searched === 1 ? '' : 's'} and {a.records_searched} records. No “{a.kind}” field exists.</span></div>)}
        <p className="t-12 faint">≈ {int(p.est_tokens)} tokens of evidence (estimate).</p></>}
      {stage.kind === 'draft' && <div className="stack-2">{p.map((m: any) => <div key={m.n} className="agg"><span className="t-14" style={{ fontWeight: 560 }}>{roleLabel(m.role)} · {draftLabel(m)}</span>
        <span className="t-12 faint">{m.reply_status ?? ''}{m.reply_cited?.length ? ` · cites ${m.reply_cited.length} record${m.reply_cited.length > 1 ? 's' : ''}` : ''}{m.prompt_tokens != null ? ` · ${int(m.prompt_tokens)} prompt / ${int(m.completion_tokens)} reply tokens` : ''}</span></div>)}</div>}
      {stage.kind === 'verify' && <div className="stack-2">{p.map((vv: any, k: number) => (
        <div key={k} className="stack-2"><div className="row-2"><span className={'badge ' + (vv.ok ? 'ok' : 'flag')}>{vv.ok ? <ShieldCheck {...ICON} size={14} /> : <Flag {...ICON} size={14} />}{vv.ok ? 'Passed' : 'Did not pass'}</span><span className="t-12 faint">{vv.target}</span></div>
          <ul className="checks one">{vv.checks.filter((c: any) => c.result !== 'not_applicable').map((c: any, i: number) => (
            <li key={c.name} className={'check ' + c.result} style={{ ['--i' as any]: i + k * 6 }}><span className="tick">{c.result === 'pass' ? <Check {...ICON} size={12} /> : c.result === 'not_applicable' ? <Minus {...ICON} size={12} /> : <Flag {...ICON} size={12} />}</span><span className="t-12">{c.label}</span></li>))}</ul></div>))}</div>}
      {(stage.kind === 'escalate' || stage.kind === 'arbitrate' || stage.kind === 'second_pass') && <p className="t-14 reason-box">{p.reason ?? ''}</p>}
      {stage.kind === 'answer' && <p className="t-14 muted">{p.status === 'abstain' ? 'The archive does not support an answer, and saying so is a valid result.' : p.status === 'not_evaluated' ? 'No answer was produced, and none is guessed.' : 'Shown in the answer card, with its evidence and rule-based confidence.'}</p>}
    </div>
  )
}

export const worldFrom = buildWorld
