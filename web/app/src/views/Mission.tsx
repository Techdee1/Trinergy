import { lazy, Suspense, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Box, Rows3 } from 'lucide-react'
import { api } from '../api/client'
import { useAsync, useKey } from '../lib/hooks'
import { buildWorld, timelineFromDetail } from '../lib/adapter'
import { useReplay } from '../lib/useReplay'
import { Replay2D, ReplayControls } from '../components/Replay2D'
import { QuestionPicker } from '../components/QuestionPicker'
import { ErrorState, ICON, Loading } from '../components/ui'

const MissionControl3D = lazy(() => import('../three/MissionControl3D'))

export const STORIES = [
  { id: 'T2-001', label: 'Single report' }, { id: 'T2-017', label: 'Multi-report' }, { id: 'T2-020', label: 'Archive-wide' }, { id: 'T2-032', label: 'Abstention' },
]

/** Keyboard for any replay: Space play/pause, arrows step, R replay, S speed. */
export function useReplayKeys(r: ReturnType<typeof useReplay>, on = true) {
  useKey(e => {
    if (e.key === ' ') { e.preventDefault(); r.playing ? r.pause() : r.play() }
    else if (e.key === 'ArrowRight') r.step(1)
    else if (e.key === 'ArrowLeft') r.step(-1)
    else if (e.key.toLowerCase() === 'r') r.replay()
    else if (e.key.toLowerCase() === 's') r.cycleSpeed()
  }, on)
}

export default function Mission() {
  const { id = 'T2-016' } = useParams()
  const nav = useNavigate()
  const [view, setView] = useState<'2d' | '3d'>('2d')
  const [notice, setNotice] = useState<string | null>(null)
  const q = useAsync(() => api.question(id), [id])
  const arch = useAsync(() => api.archive(), [])
  const traj = useAsync(() => api.trajectories().catch(() => null), [])
  const world = useMemo(() => (arch.data ? buildWorld(arch.data, traj.data) : null), [arch.data, traj.data])
  const tl = useMemo(() => q.data ? timelineFromDetail(q.data) : { question: '', stages: [], complete: false, final: null }, [q.data])
  const r = useReplay(tl, { autoplay: true, resetKey: id + ':' + (q.data ? 'y' : 'n') })
  useReplayKeys(r)
  const err = q.error ?? arch.error
  return (
    <div className="page wide mission">
      <div className="mission-top rise">
        <h1>Mission control</h1>
        <QuestionPicker value={id} onPick={x => nav(`/mission/${x}`)} />
        <div className="chips" role="group" aria-label="Example questions">
          {STORIES.map(s => <button key={s.id} className="chip interactive" aria-pressed={id === s.id} onClick={() => nav(`/mission/${s.id}`)}>{s.label} <span className="mono faint">{s.id}</span></button>)}
        </div>
        <div className="seg" role="group" aria-label="View" style={{ marginLeft: 'auto' }}>
          <button aria-pressed={view === '2d'} onClick={() => setView('2d')}><Rows3 {...ICON} size={14} />2D</button>
          <button aria-pressed={view === '3d'} onClick={() => { setNotice(null); setView('3d') }}><Box {...ICON} size={14} />3D</button>
        </div>
      </div>
      {notice && <div className="callout route" role="status" style={{ marginBottom: 'var(--s-4)' }}><Box {...ICON} /><p className="t-14">{notice}</p></div>}
      {err ? <ErrorState title="Could not load this run" body={err.message} />
        : !q.data || !world ? <Loading lines={6} />
        : <>
          {view === '2d' ? <Replay2D tl={tl} world={world} r={r} />
            : <Suspense fallback={<Loading />}><MissionControl3D timeline={tl} world={world} replay={r} onFallback={m => { setNotice(m); setView('2d') }} /></Suspense>}
          <ReplayControls r={r} />
          <p className="t-12 faint kbd-hint"><span className="kbd">Space</span> play or pause <span className="kbd">←</span><span className="kbd">→</span> step <span className="kbd">R</span> replay <span className="kbd">S</span> speed</p>
        </>}
    </div>
  )
}
