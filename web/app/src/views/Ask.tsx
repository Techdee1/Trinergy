import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUp, CloudOff, HelpCircle, Hourglass, PiggyBank, ServerCrash, ShieldAlert, Square, WifiOff } from 'lucide-react'
import { api, ApiError, askStream } from '../api/client'
import type { QuestionDetail, StageEvent } from '../api/types'
import { useAsync } from '../lib/hooks'
import { buildTimeline, buildWorld } from '../lib/adapter'
import { useReplay } from '../lib/useReplay'
import { AnswerPanel } from '../components/AnswerPanel'
import { Replay2D, ReplayControls } from '../components/Replay2D'
import { useHealth } from '../components/Shell'
import { ICON, Loading, PageHead } from '../components/ui'

const MAX = 400
type Fail = { kind: 'rate' | 'budget' | 'timeout' | 'invalid' | 'offline' | 'other'; msg: string; retry?: number }
const classify = (e: ApiError): Fail =>
  e.status === 429 || e.code === 'rate_limited' ? { kind: 'rate', msg: e.message, retry: e.retryAfter ?? 60 }
  : e.code === 'budget_exhausted' ? { kind: 'budget', msg: e.message }
  : e.status === 504 || e.code === 'timeout' ? { kind: 'timeout', msg: e.message }
  : e.status === 422 ? { kind: 'invalid', msg: e.message }
  : e.status === 0 || e.code === 'unreachable' || e.code === 'stream_broken' ? { kind: 'offline', msg: e.message }
  : { kind: 'other', msg: e.message }

export default function Ask() {
  const health = useHealth()
  const list = useAsync(() => api.questions(), [])
  const arch = useAsync(() => api.archive(), [])
  const traj = useAsync(() => api.trajectories().catch(() => null), [])
  const world = useMemo(() => (arch.data ? buildWorld(arch.data, traj.data) : null), [arch.data, traj.data])
  const [text, setText] = useState('')
  const [running, setRunning] = useState(false)
  const [events, setEvents] = useState<StageEvent[]>([])
  const [result, setResult] = useState<QuestionDetail | null>(null)
  const [asked, setAsked] = useState('')
  const [fail, setFail] = useState<Fail | null>(null)
  const [run, setRun] = useState(0)
  const abort = useRef<(() => void) | null>(null)
  const t0 = useRef(0)
  const tl = useMemo(() => buildTimeline(asked, events, result), [asked, events, result])
  const r = useReplay(tl, { follow: running, resetKey: String(run) })

  const suggestions = useMemo(() => {
    const q = list.data?.questions ?? []
    const pick = (f: (x: typeof q[number]) => boolean) => q.find(f)
    return [
      { tag: 'Answered', q: pick(x => x.set === 'challenge' && x.status === 'answered' && x.router_mode === 'single_report' && !x.flags.length)?.question },
      { tag: 'Multi-report', q: pick(x => x.set === 'challenge' && x.router_mode === 'multi_report' && x.status === 'answered')?.question },
      { tag: 'Abstains', q: pick(x => x.set === 'challenge' && x.status === 'abstain')?.question },
      { tag: 'Too vague', q: 'What happened?' },
    ].filter((s): s is { tag: string; q: string } => !!s.q)
  }, [list.data])

  const ask = (q: string) => {
    const question = q.trim()
    if (!question || running) return
    if (question.length > MAX) { setFail({ kind: 'invalid', msg: `Questions are limited to ${MAX} characters.` }); return }
    abort.current?.(); setText(question); setAsked(question); setEvents([]); setResult(null); setFail(null); setRun(n => n + 1); setRunning(true); t0.current = performance.now()
    abort.current = askStream(question, {
      onStage: e => setEvents(es => [...es, e]),
      onResult: d => { setResult(d); setRunning(false) },
      onError: e => { setFail(classify(e)); setRunning(false) },
    })
  }
  useEffect(() => () => abort.current?.(), [])
  // fast (cached) runs: replay from the start so the stages are visible
  useEffect(() => { if (result && performance.now() - t0.current < 2500) r.replay() }, [result]) // eslint-disable-line react-hooks/exhaustive-deps
  const stop = () => { abort.current?.(); setRunning(false) }
  const over = text.length > MAX
  const clar = result?.clarification

  return (
    <div className="page">
      <PageHead eyebrow="Ask" title="Ask the archive anything" lead="Name a well, a date or a field. You will see each stage as it happens, then the answer with its evidence." />
      {health && !health.live_mode && <div className="callout abstain rise" role="status" style={{ marginBottom: 'var(--s-5)' }}><CloudOff {...ICON} /><div><b>Live mode is off</b><p className="t-14 muted">Only questions the archive has already answered can be replayed. A new question is reported as NOT EVALUATED, never guessed.</p></div></div>}

      <form className="card ask-box rise rise-1" onSubmit={e => { e.preventDefault(); ask(text) }}>
        <label className="sr" htmlFor="q">Your question</label>
        <textarea id="q" className="textarea" placeholder="For well 15/9-F-1-C on 2014-03-26, what was the density of the NaCl brine?" value={text} onChange={e => setText(e.target.value)} rows={3}
          onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); ask(text) } }} aria-invalid={over} aria-describedby="q-count" />
        <div className="row between wrap">
          <div className="chips" aria-label="Suggested questions">
            <span className="t-12 faint" style={{ alignSelf: 'center' }}>Try</span>
            {suggestions.map(s => <button type="button" key={s.tag} className="chip interactive" onClick={() => ask(s.q)} title={s.q}>{s.tag}</button>)}
          </div>
          <div className="row-2"><span id="q-count" className={'t-12 num ' + (over ? 'over' : 'faint')}>{text.length} / {MAX}</span>
            {running ? <button type="button" className="btn" onClick={stop}><Square {...ICON} size={14} />Stop</button>
              : <button type="submit" className="btn primary" disabled={!text.trim() || over}><ArrowUp {...ICON} />Ask <span className="kbd" style={{ background: 'transparent', color: 'inherit', borderColor: 'color-mix(in srgb, currentColor 40%, transparent)' }}>⌘↵</span></button>}</div>
        </div>
      </form>

      {fail && <FailCard f={fail} onRetry={() => ask(asked || text)} />}

      {asked && !fail?.kind.match(/^(invalid)$/) && (
        <div className="stack-5" style={{ marginTop: 'var(--s-6)' }}>
          {!world ? <Loading /> : <>
            <Replay2D tl={tl} world={world} r={r} live={running} />
            <ReplayControls r={r} label={running ? 'Live' : undefined} />
          </>}
          {result && clar && <Clarify c={clar} onPick={ask} />}
          {result && !clar && result.status === 'not_evaluated' && <NotEvaluated d={result} />}
          {result && !clar && result.status !== 'not_evaluated' && <AnswerPanel d={result} />}
        </div>
      )}
    </div>
  )
}

function Clarify({ c, onPick }: { c: NonNullable<QuestionDetail['clarification']>; onPick: (q: string) => void }) {
  return (
    <section className="card state clarify rise" aria-labelledby="cl-h">
      <HelpCircle size={28} strokeWidth={1.5} />
      <div className="stack">
        <span className="badge abstain">Needs clarification · no model was called</span>
        <h2 id="cl-h" className="t-24">I need a bit more to go on</h2>
        <p className="t-16 muted" style={{ maxWidth: '64ch' }}>{c.message.split(/ For example:/)[0]}</p>
        <div className="stack-2"><div className="eyebrow">Try one of these</div>
          {c.examples.map((e, i) => <button key={i} className="example" onClick={() => onPick(e)}><span className="num faint">{i + 1}</span><span>{e}</span><ArrowUp {...ICON} size={16} /></button>)}</div>
      </div>
    </section>
  )
}

function NotEvaluated({ d }: { d: QuestionDetail }) {
  return (
    <section className="card state rise" aria-labelledby="ne-h">
      <Hourglass size={28} strokeWidth={1.5} />
      <div className="stack">
        <span className="badge ctx">NOT EVALUATED</span>
        <h2 id="ne-h" className="t-24">This question has not been answered, and it will not be guessed</h2>
        <p className="t-16 muted" style={{ maxWidth: '64ch' }}>{d.answer.replace(/^NOT EVALUATED:\s*/, '')}</p>
        <p className="t-14 faint">Confidence 0. No evidence is cited, because none was produced. Questions already in the archive's answer set still replay in full: see the <Link className="link" to="/questions">results board</Link>.</p>
      </div>
    </section>
  )
}

function FailCard({ f, onRetry }: { f: Fail; onRetry: () => void }) {
  const [left, setLeft] = useState(f.retry ?? 0)
  useEffect(() => { setLeft(f.retry ?? 0); if (!f.retry) return; const t = setInterval(() => setLeft(l => Math.max(0, l - 1)), 1000); return () => clearInterval(t) }, [f])
  const M = {
    rate: { icon: <Hourglass size={28} strokeWidth={1.5} />, tag: 'Rate limited', h: 'Slow down a moment', body: 'To keep the demo available for everyone, each visitor can ask only a few questions a minute.', tone: 'abstain' },
    budget: { icon: <PiggyBank size={28} strokeWidth={1.5} />, tag: 'Budget reached', h: 'Live questions have used up their budget', body: 'The spending cap for this demo is spent. Questions already in the archive still replay in full. New ones cannot be answered right now.', tone: 'abstain' },
    timeout: { icon: <ServerCrash size={28} strokeWidth={1.5} />, tag: 'Timed out', h: 'That took too long', body: 'The question was cut off before it finished. Try a narrower one: name a single well and date.', tone: 'ctx' },
    offline: { icon: <WifiOff size={28} strokeWidth={1.5} />, tag: 'Connection lost', h: 'Cannot reach the archive server', body: 'The server may be asleep or restarting. It can take up to a minute to wake.', tone: 'ctx' },
    invalid: { icon: <ShieldAlert size={28} strokeWidth={1.5} />, tag: 'Check the question', h: 'That question cannot be sent', body: f.msg, tone: 'ctx' },
    other: { icon: <ServerCrash size={28} strokeWidth={1.5} />, tag: 'Something went wrong', h: 'The archive could not answer', body: f.msg, tone: 'ctx' },
  }[f.kind]
  return (
    <section className="card state rise" role="alert" style={{ marginTop: 'var(--s-5)' }} data-state={f.kind}>
      {M.icon}
      <div className="stack">
        <span className={'badge ' + M.tone}>{M.tag}</span>
        <h2 className="t-24">{M.h}</h2><p className="t-16 muted" style={{ maxWidth: '64ch' }}>{M.body}</p>
        {f.kind === 'rate' && <p className="t-14"><span className="num">{left > 0 ? `You can ask again in ${left} s.` : 'You can ask again now.'}</span></p>}
        {(f.kind === 'rate' || f.kind === 'offline' || f.kind === 'timeout') && <div><button className="btn" onClick={onRetry} disabled={f.kind === 'rate' && left > 0}>Try again</button></div>}
      </div>
    </section>
  )
}
