/**
 * Scene layout derived ONLY from the adapter's World. Units: metres. Three.js axes: x = east, y = up (y = -TVD), z = -north.
 *
 * Real:      each wellbore's path shape (minimum-curvature x/y/TVD from /trajectories), TVD values, station MDs,
 *            the 6 reports that carry their own survey stations (placed at their deepest station that day).
 * Schematic: wellhead positions (platform template ring, 15/9-19 offset), the dashed connector from the wellhead
 *            down to the first surveyed station, the length of the dashed line for wellbores with no usable survey,
 *            and the position of reports with no depth (spread in date order along the path).
 */
import * as THREE from 'three'
import type { World, WorldWellbore, WorldReport } from '../lib/adapter'

export const NO_SURVEY_DEPTH = 1500 // schematic length (m) of the dashed line for wellbores without a usable trajectory

export interface NodeGeom {
  index: number; stem: string; wellbore: string; date: string; year: number; records: number; pages: number; pdfFile: string
  pos: THREE.Vector3; t: number               // parameter on the well's real curve (0..1), or fraction of the dashed line
  placement: 'survey' | 'date'; md: number | null; tvd: number | null
  well: WellGeom; slotIndex: number           // index within the placement-specific instanced mesh
}
export interface WellGeom {
  name: string; slot: string; head: THREE.Vector3; firstStation: THREE.Vector3
  curve: THREE.CatmullRomCurve3 | null        // real survey path; null when no usable trajectory
  dashedOnly: boolean; note: string | null; connectorLen: number; realLen: number
  nodes: NodeGeom[]; minY: number; maxY: number
}
export interface Layout { wells: WellGeom[]; nodes: NodeGeom[]; byStem: Map<string, NodeGeom>; slots: { name: string; head: THREE.Vector3; wellbores: string[] }[]
  bounds: THREE.Box3; maxTvd: number; years: number[] }

const RING = 300       // schematic template radius (m)
const SUB = 70         // schematic offset between sidetracks sharing a slot (m)
const FAR = new THREE.Vector3(1500, 0, 450) // schematic offset of the exploration well 15/9-19

const short = (n: string) => n.replace(/^15\/9-/, '')

export function buildLayout(world: World): Layout {
  const slotNames = [...new Set(world.wellbores.map(w => w.well))].sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))
  const fSlots = slotNames.filter(s => /-F-/.test(s)), other = slotNames.filter(s => !/-F-/.test(s))
  const slotPos = new Map<string, THREE.Vector3>()
  fSlots.forEach((s, i) => { const a = (i / fSlots.length) * Math.PI * 2 - Math.PI / 2; slotPos.set(s, new THREE.Vector3(Math.cos(a) * RING, 0, Math.sin(a) * RING)) })
  other.forEach((s, i) => slotPos.set(s, FAR.clone().add(new THREE.Vector3(i * 220, 0, 0))))

  const wells: WellGeom[] = []; const nodes: NodeGeom[] = []
  const years = [...new Set(world.wellbores.flatMap(w => w.reports.map(r => +r.date.slice(0, 4))))].sort((a, b) => a - b)
  let sCount = 0, dCount = 0
  for (const slot of slotNames) {
    const members = world.wellbores.filter(w => w.well === slot)
    members.forEach((wb, k) => {
      const base = slotPos.get(slot)!.clone()
      const tangent = new THREE.Vector3(-base.z, 0, base.x).normalize()
      if (!isFinite(tangent.x)) tangent.set(1, 0, 0)
      const head = base.add(tangent.multiplyScalar((k - (members.length - 1) / 2) * SUB))
      const g = wellGeom(wb, slot, head)
      wells.push(g)
      // reports: surveyed ones at their deepest own station; the rest in date order along the path
      const own = (r: WorldReport) => (wb.trajectory?.stations ?? []).map((s, i) => ({ s, i })).filter(x => x.s.report_date === r.date)
      const dated = wb.reports.filter(r => !own(r).length)
      for (const r of wb.reports) {
        const o = own(r)
        let n: NodeGeom
        if (o.length && g.curve) {
          const last = o.reduce((m, x) => (x.s.md > m.s.md ? x : m), o[0])
          const nst = wb.trajectory!.stations.length
          const t = nst > 1 ? last.i / (nst - 1) : 0
          n = mk(r, wb, g, g.curve.getPoint(t), t, 'survey', last.s.md, last.s.tvd, sCount++)
        } else {
          const k2 = dated.indexOf(r), m = dated.length
          const f = (k2 + 1) / (m + 1)
          const pos = g.curve ? g.curve.getPoint(f) : g.head.clone().add(new THREE.Vector3(0, -NO_SURVEY_DEPTH * (0.12 + 0.8 * f), 0))
          n = mk(r, wb, g, pos, f, 'date', null, null, dCount++)
        }
        n.index = nodes.length; nodes.push(n); g.nodes.push(n)
      }
    })
  }
  const bounds = new THREE.Box3()
  wells.forEach(w => { bounds.expandByPoint(w.head); bounds.expandByPoint(new THREE.Vector3(w.head.x, w.minY, w.head.z)); if (w.curve) w.curve.points.forEach(p => bounds.expandByPoint(p)) })
  const slots = slotNames.map(s => ({ name: s, head: slotPos.get(s)!.clone(), wellbores: world.wellbores.filter(w => w.well === s).map(w => w.name) }))
  return { wells, nodes, byStem: new Map(nodes.map(n => [n.stem, n])), slots, bounds, maxTvd: -bounds.min.y, years }

  function mk(r: WorldReport, wb: WorldWellbore, g: WellGeom, pos: THREE.Vector3, t: number, placement: 'survey' | 'date', md: number | null, tvd: number | null, slotIndex: number): NodeGeom {
    return { index: 0, stem: r.stem, wellbore: wb.name, date: r.date, year: +r.date.slice(0, 4), records: r.records, pages: r.pages, pdfFile: r.pdfFile, pos, t, placement, md, tvd, well: g, slotIndex }
  }
}

function wellGeom(wb: WorldWellbore, slot: string, head: THREE.Vector3): WellGeom {
  const st = wb.trajectory?.status === 'ok' ? wb.trajectory.stations : []
  const pts: THREE.Vector3[] = []
  for (const s of st) {
    const p = new THREE.Vector3(head.x + s.x, -s.tvd, head.z - s.y)
    if (!pts.length || pts[pts.length - 1].distanceTo(p) > 0.5) pts.push(p)
  }
  if (pts.length >= 2) {
    const curve = new THREE.CatmullRomCurve3(pts, false, 'centripetal')
    const first = pts[0].clone()
    const ys = pts.map(p => p.y)
    return { name: wb.name, slot, head, firstStation: first, curve, dashedOnly: false, note: null, connectorLen: head.distanceTo(first), realLen: curve.getLength(), nodes: [], minY: Math.min(...ys), maxY: 0 }
  }
  const reason = wb.trajectory?.reason ?? ''
  const note = /azi/i.test(reason) ? 'no azimuth in archive' : 'no survey in archive'
  const bottom = head.clone().add(new THREE.Vector3(0, -NO_SURVEY_DEPTH, 0))
  return { name: wb.name, slot, head, firstStation: bottom, curve: null, dashedOnly: true, note, connectorLen: NO_SURVEY_DEPTH, realLen: 0, nodes: [], minY: -NO_SURVEY_DEPTH, maxY: 0 }
}

/** Point along the path from the wellhead to a node, f in 0..1. Writes into `out` (no allocation). */
export function alongPath(n: NodeGeom, f: number, out: THREE.Vector3): THREE.Vector3 {
  const w = n.well
  if (!w.curve) return out.copy(w.head).lerp(n.pos, f)
  const realToNode = Math.max(1, w.realLen * n.t)
  const cf = w.connectorLen / (w.connectorLen + realToNode)
  if (f <= cf) return out.copy(w.head).lerp(w.firstStation, cf > 0 ? f / cf : 1)
  return w.curve.getPoint(n.t * ((f - cf) / (1 - cf)), out)
}

export { short }
