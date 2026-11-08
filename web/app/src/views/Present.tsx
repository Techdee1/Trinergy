import { lazy, Suspense, useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Box, ChevronLeft, ChevronRight, EyeOff, Keyboard, Rows3, Sun, Moon, X } from 'lucide-react'
import { api } from '../api/client'
import { useAsync, useKey } from '../lib/hooks'
import { buildWorld, timelineFromDetail } from '../lib/adapter'
import { useReplay } from '../lib/useReplay'
import { Replay2D, ReplayControls } from '../components/Replay2D'
import { Mark } from '../components/Mark'
import { useUi } from '../lib/ui-state'
import { ICON, Loading } from '../components/ui'
import { FOOTER } from '../components/Shell'

const Ask = lazy(() => import('./Ask'))
const MissionControl3D = lazy(() => import('../three/MissionControl3D'))

const STEPS = [
  { key: 'intro', label: 'Intro' },
  { key: 'a', label: 'Date window', id: 'T2-016', title: 'The date-window trap', note: 'A daily report dated D covers D−1 to D. The question asks about 2014-03-26, and the sample was taken the evening before. The router opens the report dated exactly 2014-03-26, so the sample sits inside its window.' },
  { key: 'b', label: 'Abstention', id: 'T2-032', title: 'The Western Atlas trap', note: 'A company called Western Atlas appears in the report, but it ran a wireline logging tool, not mud logging. The archive has no mud-logging field, so the right answer is to say so, and to name what was searched and rejected.' },
  { key: 'c', label: 'Multi-report', id: 'T2-017', title: 'A multi-report sequence', note: 'Four reports across four wells, read in order to follow a rig move. The first draft cited a number the records did not support, so the verifier objected and a larger model took over.' },
  { key: 'try', label: 'Your question' },
] as const

function Story({ id, title, note, allow3d }: { id: string; title: string; note: string; allow3d?: boolean }) {
  const [mode, setMode] = useState<'2d' | '3d'>('2d')
  const [notice, setNotice] = useState<string | null>(null)
  const q = useAsync(() => api.question(id), [id])
  const arch = useAsync(() => api.archive(), [])
  const traj = useAsync(() => api.trajectories().catch(() => null), [])
  const world = useMemo(() => (arch.data ? buildWorld(arch.data, traj.data) : null), [arch.data, traj.data])
  const tl = useMemo(() => (q.data ? timelineFromDetail(q.data) : { question: '', stages: [], complete: false, final: null }), [q.data])
  const r = useReplay(tl, { autoplay: true, resetKey: id + (q.data ? 'y' : 'n') })
  useKey(e => {
    if (e.key === ' ') { e.preventDefault(); r.playing ? r.pause() : r.play() }
    else if (e.key.toLowerCase() === 'r') r.replay()
    else if (e.key.toLowerCase() === 's') r.cycleSpeed()
    else if (e.key === ',') r.step(-1)
    else if (e.key === '.') r.step(1)
  })
  return (
    <div className="stack-5">
      <header className="tour-head"><div className="stack-2"><span className="eyebrow mono">{id}</span><h1 className="t-48">{title}</h1></div><p className="t-20 muted tour-note">{note}</p></header>
      {allow3d && <div className="row-2" style={{ justifyContent: 'flex-end', marginTop: 'calc(-1 * var(--s-4))' }}>
        {notice && <span className="t-12 faint">{notice}</span>}
        <div className="seg" role="group" aria-label="View"><button aria-pressed={mode === '2d'} onClick={() => setMode('2d')}><Rows3 {...ICON} size={14} />2D</button><button aria-pressed={mode === '3d'} onClick={() => { setNotice(null); setMode('3d') }}><Box {...ICON} size={14} />3D</button></div></div>}
      {!q.data || !world ? <Loading lines={5} /> : <>
        {mode === '3d' ? <Suspense fallback={<Loading />}><MissionControl3D timeline={tl} world={world} replay={r} onFallback={m => { setNotice(m); setMode('2d') }} /></Suspense> : <Replay2D tl={tl} world={world} r={r} />}
        <ReplayControls r={r} /></>}
    </div>
  )
}

export default function Present() {
  const nav = useNavigate()
  const [sp, setSp] = useSearchParams()
  const { setPresenter, hideCursor, setHideCursor, theme, toggleTheme } = useUi()
  const step = Math.min(STEPS.length - 1, Math.max(0, Number(sp.get('step') ?? 0) || 0))
  const go = (n: number) => setSp({ step: String(Math.min(STEPS.length - 1, Math.max(0, n))) }, { replace: true })
  useEffect(() => { setPresenter(true); return () => setPresenter(false) }, [setPresenter])
  const exit = () => { setPresenter(false); nav('/') }
  useKey(e => {
    if (e.key === 'ArrowRight' || e.key === 'PageDown') go(step + 1)
    else if (e.key === 'ArrowLeft' || e.key === 'PageUp') go(step - 1)
    else if (e.key.toLowerCase() === 'h') setHideCursor(!hideCursor)
    else if (e.key === 'Escape') exit()
    else if (/^[1-5]$/.test(e.key)) go(Number(e.key) - 1)
  })
  const s = STEPS[step]
  return (
    <div className="tour-frame">
      <div className="tour-bar">
        <div className="row-2"><Mark size={28} /><b className="t-14">Intelligent Well Archive</b></div>
        <ol className="tour-steps" aria-label="Tour steps">{STEPS.map((x, i) => <li key={x.key}><button className={'tstep' + (i === step ? ' on' : i < step ? ' done' : '')} onClick={() => go(i)} aria-current={i === step ? 'step' : undefined}><span className="num">{i + 1}</span>{x.label}</button></li>)}</ol>
        <div className="row-2">
          <button className="btn ghost sm" onClick={() => setHideCursor(!hideCursor)} aria-pressed={hideCursor}><EyeOff {...ICON} size={14} />Hide cursor <span className="kbd">H</span></button>
          <button className="btn ghost iconbtn sm" onClick={toggleTheme} aria-label="Toggle theme">{theme === 'dark' ? <Sun {...ICON} /> : <Moon {...ICON} />}</button>
          <button className="btn sm" onClick={exit}><X {...ICON} size={14} />Exit <span className="kbd">Esc</span></button>
        </div>
      </div>
      <main id="main" className="tour-body" tabIndex={-1} key={s.key}>
        {s.key === 'intro' && (
          <section className="tour-intro rise">
            <div className="eyebrow">NAPE AICE 2026 · Track 2 · Team Trinergy</div>
            <h1 className="t-64 tour-h">Every answer, with its proof.<br />Or an honest “not here”.</h1>
            <p className="lead">Code finds the facts. A small model phrases them. A verifier checks every claim. When the archive does not support an answer, abstaining is a valid result.</p>
            <p className="t-14 faint row-2"><Keyboard {...ICON} size={16} /><span className="kbd">←</span><span className="kbd">→</span> change step <span className="kbd">Space</span> play or pause <span className="kbd">R</span> replay <span className="kbd">S</span> speed <span className="kbd">H</span> hide cursor</p>
          </section>
        )}
        {(s.key === 'a' || s.key === 'b' || s.key === 'c') && <Story key={s.key} id={s.id} title={s.title} note={s.note} allow3d={s.key === 'c'} />}
        {s.key === 'try' && <div className="tour-try"><Suspense fallback={<Loading />}><Ask /></Suspense></div>}
      </main>
      <div className="tour-foot">
        <button className="btn" onClick={() => go(step - 1)} disabled={step === 0}><ChevronLeft {...ICON} />Back</button>
        <span className="t-12 faint">{FOOTER}</span>
        <button className="btn primary" onClick={() => go(step + 1)} disabled={step === STEPS.length - 1}>Next<ChevronRight {...ICON} /></button>
      </div>
    </div>
  )
}
