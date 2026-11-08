import { Box } from 'lucide-react'
import type { ReplayTimeline, World } from '../lib/adapter'
import type { ReplayApi } from '../components/Replay2D'
import { ICON } from '../components/ui'

/**
 * Slot for the 3D scene (built in a separate session, see web/app/3D_BRIEF.md).
 * Contract: draw `world` (wells, trajectories, reports) and react to `replay.idx` over `timeline.stages`.
 * It receives no other data and must not fetch. Lazy-loaded by Mission control, so heavy imports are free to live here.
 */
export interface MissionControl3DProps { timeline: ReplayTimeline; world: World; replay: ReplayApi }

export default function MissionControl3D({ world, timeline }: MissionControl3DProps) {
  const surveyed = world.wellbores.filter(w => w.trajectory?.status === 'ok').length
  return (
    <section className="card three-slot" aria-label="3D view">
      <Box size={32} strokeWidth={1.4} />
      <h2 className="t-24">3D view coming</h2>
      <p className="muted" style={{ maxWidth: '52ch' }}>The real field, wells in their surveyed trajectories, and the search as light moving through the archive. The 2D replay shows the same run in the meantime.</p>
      <div className="chips">
        <span className="chip"><b className="num">{world.wellbores.length}</b> wellbores</span>
        <span className="chip"><b className="num">{surveyed}</b> with trajectories</span>
        <span className="chip"><b className="num">{world.reportByStem.size}</b> reports</span>
        <span className="chip"><b className="num">{timeline.stages.length}</b> stages queued</span>
      </div>
      <p className="t-12 faint"><Box {...ICON} size={12} style={{ display: 'inline', verticalAlign: '-1px' }} /> Data adapter ready: <span className="mono">lib/adapter.ts</span></p>
    </section>
  )
}
