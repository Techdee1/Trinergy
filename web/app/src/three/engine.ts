/**
 * Plain three.js engine for Mission control 3D. Draws the Layout and applies a ReplayView per stage.
 * Render on demand: frames are drawn only while something moves (camera tween, stage animation, damping, hover).
 * No per-frame allocations in the loop: scratch vectors/colours/matrices are reused.
 */
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import type { ReplayStage, ReplayTimeline, ReplayView } from '../lib/adapter'
import { alongPath, buildLayout, short, type Layout, type NodeGeom, type WellGeom } from './layout'
import type { World } from '../lib/adapter'

export interface HoverInfo { kind: 'node'; node: NodeGeom }
export type Hover = HoverInfo | { kind: 'well'; well: WellGeom } | null
export interface EngineCallbacks {
  onHover: (h: Hover, x: number, y: number) => void
  onPick: (stem: string | null) => void
  onLowFps: (fps: number) => void
  onUserMove: (moved: boolean) => void
}

const CTX_CAP = 480, CTX_PER_REPORT = 60, AGG_CAP = 24, ABS_CAP = 8, PULSE_CAP = 40
const DIR = new THREE.Vector3(0.85, 0.72, 1.1).normalize()

type Pal = Record<'bg' | 'surface2' | 'text' | 'text2' | 'text3' | 'brand' | 'route' | 'ctx' | 'ok' | 'abstain' | 'flag', THREE.Color>
function palette(): Pal {
  const cs = getComputedStyle(document.documentElement)
  const c = (v: string) => new THREE.Color(cs.getPropertyValue(v).trim() || '#888')
  return { bg: c('--bg'), surface2: c('--surface-2'), text: c('--text'), text2: c('--text-2'), text3: c('--text-3'), brand: c('--brand'), route: c('--route'), ctx: c('--ctx'), ok: c('--ok'), abstain: c('--abstain'), flag: c('--flag') }
}
const easeIO = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2)
const easeOut = (t: number) => 1 - Math.pow(1 - t, 3)
// deterministic pseudo-random in [0,1)
const hash = (i: number, s: number) => { const x = Math.sin(i * 127.1 + s * 311.7) * 43758.5453; return x - Math.floor(x) }

interface Anim { t0: number; dur: number; kind: 'pulse' | 'secondary' | 'sweep' | 'pop' | 'fadeCtx' | 'rise'; targets: NodeGeom[] }

export class Engine {
  readonly layout: Layout
  private renderer: THREE.WebGLRenderer
  private scene = new THREE.Scene()
  private camera: THREE.PerspectiveCamera
  private controls: OrbitControls
  private pal: Pal
  private host: HTMLElement
  private overlay: HTMLElement
  private cb: EngineCallbacks
  private raf = 0
  private dirty = true
  private disposed = false
  private reduced = matchMedia('(prefers-reduced-motion: reduce)').matches
  // scene objects
  private wellMats = new Map<string, THREE.MeshLambertMaterial>()
  private dashMats = new Map<string, THREE.LineDashedMaterial>()
  private tubes: THREE.Mesh[] = []
  private nodeSurvey: THREE.InstancedMesh
  private nodeDate: THREE.InstancedMesh
  private pickMesh: THREE.InstancedMesh // invisible sphere per node: generous hit target (rings have a hole)
  private ctxPts: THREE.InstancedMesh
  private aggPts: THREE.InstancedMesh
  private absPts: THREE.InstancedMesh
  private pulses: THREE.InstancedMesh
  private pulses2: THREE.InstancedMesh
  private rise: THREE.LineSegments
  private risePos: Float32Array
  private sweep: THREE.Group
  private selRing: THREE.Mesh
  private grid: THREE.GridHelper
  private axis: THREE.LineSegments
  private disposables: { dispose(): void }[] = []
  // labels
  private labels: { el: HTMLElement; pos: THREE.Vector3; node?: NodeGeom; well?: WellGeom; always: boolean }[] = []
  // state
  private baseColor: THREE.Color[] = []
  private nodeCol: THREE.Color[] = []
  private nodeScale: number[] = []
  private anims: Anim[] = []
  private cam = { from: new THREE.Vector3(), to: new THREE.Vector3(), tFrom: new THREE.Vector3(), tTo: new THREE.Vector3(), t0: 0, dur: 0, active: false }
  private userMoved = false
  private programmatic = false
  private selected = new Set<string>(); private cited = new Set<string>(); private shownLabels = new Set<string>()
  private picked: string | null = null
  private lastView: ReplayView | null = null
  private sweepRange = { y0: 0, y1: 0 }
  private speed = 1
  // scratch
  private v = new THREE.Vector3(); private v2 = new THREE.Vector3(); private m = new THREE.Matrix4(); private q = new THREE.Quaternion(); private s = new THREE.Vector3(); private col = new THREE.Color()
  private ray = new THREE.Raycaster(); private ndc = new THREE.Vector2(); private pointer: { x: number; y: number } | null = null
  // fps
  private fpsFrames = 0; private fpsT0 = 0; private lowWindows = 0
  fpsSamples: number[] = []

  constructor(host: HTMLElement, overlay: HTMLElement, world: World, cb: EngineCallbacks) {
    this.host = host; this.overlay = overlay; this.cb = cb
    this.layout = buildLayout(world)
    this.pal = palette()
    this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance', failIfMajorPerformanceCaveat: false })
    if (!this.renderer.getContext()) throw new Error('no webgl')
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
    this.renderer.domElement.className = 'mc3-canvas'
    host.appendChild(this.renderer.domElement)
    const { clientWidth: w, clientHeight: h } = host
    this.renderer.setSize(w, h, false)
    this.camera = new THREE.PerspectiveCamera(38, w / Math.max(1, h), 5, 40000)
    this.applyOffset()
    this.controls = new OrbitControls(this.camera, this.renderer.domElement)
    this.controls.enableDamping = true; this.controls.dampingFactor = 0.08; this.controls.screenSpacePanning = true
    this.controls.minDistance = 120; this.controls.maxDistance = 16000; this.controls.rotateSpeed = 0.6; this.controls.zoomSpeed = 0.8
    this.controls.addEventListener('start', () => { if (!this.programmatic) { this.userMoved = true; this.cam.active = false; this.cb.onUserMove(true) } })
    this.controls.addEventListener('change', () => { this.dirty = true })

    this.scene.background = this.pal.bg.clone()
    const span = Math.max(this.layout.bounds.getSize(this.v).length(), 1500)
    this.scene.fog = new THREE.Fog(this.pal.bg.clone(), span * 1.6, span * 4.5)
    const hemi = new THREE.HemisphereLight(0xffffff, 0x404040, 1.6); this.scene.add(hemi)
    const dir = new THREE.DirectionalLight(0xffffff, 0.9); dir.position.set(1, 2, 1.5); this.scene.add(dir)

    // surface reference plane with a fine grid (100 m cells)
    const b = this.layout.bounds
    const size = Math.ceil((Math.max(b.max.x - b.min.x, b.max.z - b.min.z) + 900) / 100) * 100
    this.grid = new THREE.GridHelper(size, size / 100, this.pal.text3, this.pal.text3)
    const gm = this.grid.material as THREE.Material; gm.transparent = true; gm.opacity = 0.16; gm.depthWrite = false
    this.grid.position.set((b.max.x + b.min.x) / 2, 0, (b.max.z + b.min.z) / 2)
    this.scene.add(this.grid); this.disposables.push(this.grid.geometry, gm)

    // TVD scale: vertical line with 500 m ticks, on the west side
    const ax = b.min.x - 260, az = (b.max.z + b.min.z) / 2
    const maxT = Math.ceil(this.layout.maxTvd / 500) * 500
    const ap: number[] = [ax, 0, az, ax, -maxT, az]
    for (let d = 0; d <= maxT; d += 500) ap.push(ax - 40, -d, az, ax + 40, -d, az)
    const ag = new THREE.BufferGeometry(); ag.setAttribute('position', new THREE.Float32BufferAttribute(ap, 3))
    const am = new THREE.LineBasicMaterial({ color: this.pal.text3, transparent: true, opacity: 0.7 })
    this.axis = new THREE.LineSegments(ag, am); this.scene.add(this.axis); this.disposables.push(ag, am)
    for (let d = 0; d <= maxT; d += 500) this.label(`${d.toLocaleString('en-US')} m`, new THREE.Vector3(ax - 56, -d, az), 'tick', true)
    this.label('TVD (m)', new THREE.Vector3(ax, -maxT - 180, az), 'tick strong', true)

    // wells
    for (const w of this.layout.wells) {
      const dm = new THREE.LineDashedMaterial({ color: this.pal.ctx, dashSize: 40, gapSize: 28, transparent: true, opacity: 0.9 })
      const lg = new THREE.BufferGeometry().setFromPoints([w.head, w.firstStation])
      const line = new THREE.Line(lg, dm); line.computeLineDistances(); this.scene.add(line)
      this.dashMats.set(w.name, dm); this.disposables.push(lg, dm)
      if (w.curve) {
        const segs = Math.min(128, Math.max(24, w.curve.points.length * 6))
        const tg = new THREE.TubeGeometry(w.curve, segs, 9, 6, false)
        const tm = new THREE.MeshLambertMaterial({ color: this.pal.ctx })
        const mesh = new THREE.Mesh(tg, tm); mesh.userData.well = w; this.scene.add(mesh); this.tubes.push(mesh)
        this.wellMats.set(w.name, tm); this.disposables.push(tg, tm)
        if (w.firstStation.y < -400) this.label(short(w.name), w.firstStation.clone().add(new THREE.Vector3(22, 0, 0)), 'well-sub', true, undefined, w)
      } else {
        this.label(`${short(w.name)} · ${w.note}`, w.firstStation.clone().add(new THREE.Vector3(18, 0, 0)), 'well-sub note', true, undefined, w)
      }
    }
    this.layout.slots.forEach((s, i) => {
      const out = s.head.clone().setY(0); const len = out.length() || 1
      const p = out.multiplyScalar((len + 160) / len).add(new THREE.Vector3(0, 60 + (i % 2) * 70, 0))
      const el = this.label(s.wellbores.map(short).join(' · '), p, 'head', true); el.dataset.slot = s.name
    })

    // report nodes (instanced): solid sphere = at surveyed depth, flat ring = placed in date order
    const nS = this.layout.nodes.filter(n => n.placement === 'survey'), nD = this.layout.nodes.filter(n => n.placement === 'date')
    const sg = new THREE.SphereGeometry(24, 18, 12), dg = new THREE.TorusGeometry(26, 6, 8, 28); dg.rotateX(Math.PI / 2)
    const nm = new THREE.MeshLambertMaterial({ color: 0xffffff })
    this.nodeSurvey = new THREE.InstancedMesh(sg, nm, Math.max(1, nS.length)); this.nodeSurvey.count = nS.length
    this.nodeDate = new THREE.InstancedMesh(dg, nm, Math.max(1, nD.length)); this.nodeDate.count = nD.length
    this.scene.add(this.nodeSurvey, this.nodeDate); this.disposables.push(sg, dg, nm)
    this.layout.nodes.forEach(n => {
      this.nodeScale[n.index] = 1; this.nodeCol[n.index] = new THREE.Color(); this.baseColor[n.index] = new THREE.Color()
      this.label(`${short(n.wellbore)} · ${n.date}`, n.pos.clone().add(new THREE.Vector3(34, 10, 0)), 'node', false, n)
    })
    this.computeBaseColors()
    const pkg = new THREE.SphereGeometry(40, 10, 8), pkm = new THREE.MeshBasicMaterial({ colorWrite: false, depthWrite: false })
    this.pickMesh = new THREE.InstancedMesh(pkg, pkm, this.layout.nodes.length)
    this.layout.nodes.forEach(n => { this.m.compose(n.pos, this.q.identity(), this.s.set(1, 1, 1)); this.pickMesh.setMatrixAt(n.index, this.m) })
    this.pickMesh.renderOrder = -1; this.scene.add(this.pickMesh); this.disposables.push(pkg, pkm)

    // context records, aggregates, ABSENT
    const cg = new THREE.SphereGeometry(5.5, 8, 6), cm = new THREE.MeshBasicMaterial({ color: this.pal.ctx, transparent: true, opacity: 0 })
    this.ctxPts = new THREE.InstancedMesh(cg, cm, CTX_CAP); this.ctxPts.count = 0
    const bg = new THREE.BoxGeometry(13, 13, 13), bm = new THREE.MeshBasicMaterial({ color: this.pal.route, transparent: true, opacity: 0 })
    this.aggPts = new THREE.InstancedMesh(bg, bm, AGG_CAP); this.aggPts.count = 0
    const og = new THREE.OctahedronGeometry(30), om = new THREE.MeshBasicMaterial({ color: this.pal.abstain, wireframe: true, transparent: true, opacity: 0 })
    this.absPts = new THREE.InstancedMesh(og, om, ABS_CAP); this.absPts.count = 0
    this.scene.add(this.ctxPts, this.aggPts, this.absPts); this.disposables.push(cg, cm, bg, bm, og, om)

    // pulses and rising lines
    const pg = new THREE.SphereGeometry(18, 14, 10)
    const pm = new THREE.MeshBasicMaterial({ color: this.pal.brand }), pm2 = new THREE.MeshBasicMaterial({ color: this.pal.flag })
    this.pulses = new THREE.InstancedMesh(pg, pm, PULSE_CAP); this.pulses.count = 0
    this.pulses2 = new THREE.InstancedMesh(pg, pm2, PULSE_CAP); this.pulses2.count = 0
    this.risePos = new Float32Array(PULSE_CAP * 6)
    const rg = new THREE.BufferGeometry(); rg.setAttribute('position', new THREE.BufferAttribute(this.risePos, 3)); rg.setDrawRange(0, 0)
    const rm = new THREE.LineBasicMaterial({ color: this.pal.brand, transparent: true, opacity: 0.85 })
    this.rise = new THREE.LineSegments(rg, rm); this.rise.frustumCulled = false
    this.scene.add(this.pulses, this.pulses2, this.rise); this.disposables.push(pg, pm, pm2, rg, rm)

    // abstain sweep plane
    this.sweep = new THREE.Group()
    const sp = new THREE.PlaneGeometry(1, 1); sp.rotateX(-Math.PI / 2)
    const spm = new THREE.MeshBasicMaterial({ color: this.pal.abstain, transparent: true, opacity: 0.14, side: THREE.DoubleSide, depthWrite: false })
    const eg = new THREE.EdgesGeometry(sp), em = new THREE.LineBasicMaterial({ color: this.pal.abstain, transparent: true, opacity: 0.9 })
    this.sweep.add(new THREE.Mesh(sp, spm), new THREE.LineSegments(eg, em)); this.sweep.visible = false
    this.scene.add(this.sweep); this.disposables.push(sp, spm, eg, em)

    // selection ring (Heirs red: selection only)
    const rgeo = new THREE.TorusGeometry(42, 3.2, 8, 40); rgeo.rotateX(Math.PI / 2)
    const rmat = new THREE.MeshBasicMaterial({ color: this.pal.brand })
    this.selRing = new THREE.Mesh(rgeo, rmat); this.selRing.visible = false; this.scene.add(this.selRing); this.disposables.push(rgeo, rmat)

    this.writeNodes()
    this.fitAll(true)
    const el = this.renderer.domElement
    el.addEventListener('pointermove', this.onMove); el.addEventListener('pointerleave', this.onLeave); el.addEventListener('click', this.onClick)
    this.ro = new ResizeObserver(() => this.resize()); this.ro.observe(host)
    document.addEventListener('visibilitychange', this.onVis)
    this.raf = requestAnimationFrame(this.loop)
  }
  private ro: ResizeObserver

  // ───────────── labels (HTML overlay, projected each rendered frame)
  private label(text: string, pos: THREE.Vector3, cls: string, always: boolean, node?: NodeGeom, well?: WellGeom) {
    const el = document.createElement('div'); el.className = 'l3 ' + cls.split(' ').map(c => 'l3-' + c).join(' '); el.textContent = text
    if (!always) el.style.display = 'none'
    this.overlay.appendChild(el); this.labels.push({ el, pos, node, well, always }); return el
  }
  private placeLabels() {
    const w = this.host.clientWidth, h = this.host.clientHeight
    for (const l of this.labels) {
      if (!l.always && !(l.node && this.shownLabels.has(l.node.stem))) { if (l.el.style.display !== 'none') l.el.style.display = 'none'; continue }
      this.v.copy(l.pos).project(this.camera)
      if (this.v.z > 1 || this.v.x < -1.1 || this.v.x > 1.1 || this.v.y < -1.1 || this.v.y > 1.1) { l.el.style.display = 'none'; continue }
      l.el.style.display = ''
      l.el.style.transform = `translate3d(${((this.v.x + 1) / 2 * w).toFixed(1)}px, ${((1 - this.v.y) / 2 * h).toFixed(1)}px, 0)`
    }
  }
  /** screen position (px, relative to host) of a report node */
  screenOf(stem: string): { x: number; y: number } | null {
    const n = this.layout.byStem.get(stem); if (!n) return null
    this.v.copy(n.pos).project(this.camera); if (this.v.z > 1) return null
    return { x: (this.v.x + 1) / 2 * this.host.clientWidth, y: (1 - this.v.y) / 2 * this.host.clientHeight }
  }

  // ───────────── colours
  private computeBaseColors() {
    const ys = this.layout.years
    this.layout.nodes.forEach(n => { const t = ys.length > 1 ? ys.indexOf(n.year) / (ys.length - 1) : 1; this.baseColor[n.index].copy(this.pal.text3).lerp(this.pal.text, 0.15 + 0.85 * t) })
  }
  private writeNodes() {
    for (const n of this.layout.nodes) {
      const k = this.nodeScale[n.index]
      this.s.set(k, k, k); this.q.identity(); this.m.compose(n.pos, this.q, this.s)
      const mesh = n.placement === 'survey' ? this.nodeSurvey : this.nodeDate
      mesh.setMatrixAt(n.slotIndex, this.m); mesh.setColorAt(n.slotIndex, this.nodeCol[n.index])
    }
    for (const mesh of [this.nodeSurvey, this.nodeDate]) { mesh.instanceMatrix.needsUpdate = true; if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true }
    this.dirty = true
  }

  applyTheme() {
    this.pal = palette()
    ;(this.scene.background as THREE.Color).copy(this.pal.bg); (this.scene.fog as THREE.Fog).color.copy(this.pal.bg)
    const gm = this.grid.material as THREE.LineBasicMaterial
    ;(Array.isArray(gm) ? gm : [gm]).forEach((x: any) => x.color?.copy(this.pal.text3))
    ;(this.axis.material as THREE.LineBasicMaterial).color.copy(this.pal.text3)
    ;(this.ctxPts.material as THREE.MeshBasicMaterial).color.copy(this.pal.ctx)
    ;(this.aggPts.material as THREE.MeshBasicMaterial).color.copy(this.pal.route)
    ;(this.absPts.material as THREE.MeshBasicMaterial).color.copy(this.pal.abstain)
    ;(this.pulses.material as THREE.MeshBasicMaterial).color.copy(this.pal.brand)
    ;(this.pulses2.material as THREE.MeshBasicMaterial).color.copy(this.pal.flag)
    ;(this.rise.material as THREE.LineBasicMaterial).color.copy(this.pal.brand)
    ;(this.selRing.material as THREE.MeshBasicMaterial).color.copy(this.pal.brand)
    this.sweep.children.forEach((c: any) => c.material.color.copy(this.pal.abstain))
    this.computeBaseColors()
    if (this.lastView) this.applyColors(this.lastView)
    this.dirty = true
  }

  // ───────────── stage application
  apply(tl: ReplayTimeline, idx: number, view: ReplayView, speed: number) {
    this.speed = speed; this.lastView = view
    const stage: ReplayStage | undefined = tl.stages[idx]
    this.selected = new Set(view.selected); this.cited = new Set(view.citedReports)
    this.anims.length = 0; this.pulses.count = 0; this.pulses2.count = 0
    this.applyColors(view)
    // labels: dates on opened reports
    this.shownLabels = new Set([...this.selected].slice(0, 12))
    this.cited.forEach(s => this.shownLabels.add(s))
    if (this.picked) this.shownLabels.add(this.picked)
    this.layoutContext(view, tl)
    this.layoutRise(view, stage)
    const sel = this.layout.nodes.filter(n => this.selected.has(n.stem))
    const absent = view.absent.length > 0
    // sweep range: selected wells' depth range
    if (sel.length) { const ys = sel.flatMap(n => [n.pos.y, n.well.minY, Math.min(0, n.well.firstStation.y)]); this.sweepRange = { y0: Math.max(...ys) + 40, y1: Math.min(...ys) - 40 } }
    this.sweep.visible = false
    const dwell = (stage?.durationMs ?? 2000) / speed
    const now = performance.now()
    const add = (kind: Anim['kind'], dur: number, targets: NodeGeom[], delay = 0) => this.anims.push({ t0: now + delay, dur, kind, targets })
    if (stage && !this.reduced) {
      switch (stage.kind) {
        case 'route': add('pop', 700 / speed, sel); break
        case 'context': if (absent && sel.length) add('sweep', dwell * 0.75, sel); else add('fadeCtx', 500 / speed, []); break
        case 'draft': { const tg = this.citedOrSelected(view, sel); add('pulse', dwell * 0.5, tg); add('rise', dwell * 0.35, tg, dwell * 0.5); break }
        case 'verify': add('pop', 600 / speed, this.layout.nodes.filter(n => this.cited.has(n.stem))); break
        case 'escalate': case 'second_pass': case 'arbitrate': add('secondary', dwell * 0.6, sel.slice(0, PULSE_CAP)); break
      }
    }
    if (absent && stage && (stage.kind !== 'context' || this.reduced) && tl.stages.slice(0, idx + 1).some(s => s.kind === 'context')) this.showSweepAt(1, 0.11)
    // fade-in of context points: set final opacity unless the fade anim runs
    const ctxOpacity = this.anims.some(a => a.kind === 'fadeCtx') ? 0 : 0.85
    ;(this.ctxPts.material as THREE.MeshBasicMaterial).opacity = ctxOpacity
    ;(this.aggPts.material as THREE.MeshBasicMaterial).opacity = ctxOpacity
    ;(this.absPts.material as THREE.MeshBasicMaterial).opacity = ctxOpacity
    // camera choreography
    if (!this.userMoved) {
      if (!stage || stage.kind === 'parse' || stage.kind === 'gate' || !sel.length) this.fitAll(this.reduced, dwell)
      else this.fitNodes(sel, stage.kind === 'answer' ? 1.04 : 1, this.reduced, Math.min(2200, dwell * 0.8))
    }
    this.writeNodes()
  }

  private citedOrSelected(view: ReplayView, sel: NodeGeom[]) {
    const c = this.layout.nodes.filter(n => view.citedReports.has(n.stem))
    return (c.length ? c : sel).slice(0, PULSE_CAP)
  }

  private applyColors(view: ReplayView) {
    const P = this.pal, routed = view.routed && !view.gate
    const sweptStage = view.absent.length > 0
    for (const n of this.layout.nodes) {
      const c = this.nodeCol[n.index].copy(this.baseColor[n.index])
      const sel = this.selected.has(n.stem)
      if (this.cited.has(n.stem) && (view.answered || view.verifies.length)) c.copy(P.ok)
      else if (sel && sweptStage) c.copy(P.abstain)
      else if (sel) c.copy(P.route)
      else if (routed) c.lerp(P.bg, 0.78)
      this.nodeScale[n.index] = sel ? 1.25 : 1
    }
    for (const w of this.layout.wells) {
      const cand = routed && view.candidates.has(w.name)
      const tm = this.wellMats.get(w.name), dm = this.dashMats.get(w.name)!
      const c = this.col.copy(P.ctx)
      if (cand) c.lerp(P.text, 0.45); else if (routed) c.lerp(P.bg, 0.72)
      tm?.color.copy(c); dm.color.copy(c); dm.opacity = (routed && !cand ? 0.3 : 0.7) * (w.dashedOnly ? 0.75 : 1)
    }
    for (const l of this.labels) if (l.well) l.el.classList.toggle('l3-dim', routed && !view.candidates.has(l.well.name))
    for (const l of this.labels) if (l.el.dataset.slot) l.el.classList.toggle('l3-dim', routed && !this.layout.slots.some(s => s.name === l.el.dataset.slot && s.wellbores.some(wb => view.candidates.has(wb))))
    // selection ring on a picked node
    const p = this.picked ? this.layout.byStem.get(this.picked) : null
    this.selRing.visible = !!p; if (p) this.selRing.position.copy(p.pos)
    this.dirty = true
  }

  private layoutContext(view: ReplayView, tl: ReplayTimeline) {
    const ctx = view.contexts[view.contexts.length - 1]
    let i = 0, a = 0, b = 0
    if (ctx) {
      const per = new Map<string, number>()
      for (const r of ctx.records) {
        const n = this.layout.byStem.get(r.report); if (!n) continue
        const k = per.get(r.report) ?? 0; if (k >= CTX_PER_REPORT || i >= CTX_CAP) continue
        per.set(r.report, k + 1)
        // golden-angle shell around the node, radius grows slightly with count
        const phi = Math.acos(1 - 2 * hash(k, 1)), th = k * 2.39996
        const rad = 34 + 22 * hash(k, 2)
        this.v.set(Math.sin(phi) * Math.cos(th), Math.cos(phi), Math.sin(phi) * Math.sin(th)).multiplyScalar(rad).add(n.pos)
        this.s.set(1, 1, 1); this.q.identity(); this.m.compose(this.v, this.q, this.s); this.ctxPts.setMatrixAt(i++, this.m)
      }
      const sel = this.layout.nodes.filter(n => this.selected.has(n.stem))
      const anchor = this.v2.set(0, 0, 0); sel.forEach(n => anchor.add(n.pos)); if (sel.length) anchor.multiplyScalar(1 / sel.length)
      ctx.aggregates.slice(0, AGG_CAP).forEach((_, k) => {
        this.v.set(70 + (k % 6) * 22, 30 + Math.floor(k / 6) * 22, 0).add(anchor)
        this.q.setFromEuler(new THREE.Euler(0.6, 0.6, 0)); this.m.compose(this.v, this.q, this.s.set(1, 1, 1)); this.aggPts.setMatrixAt(a++, this.m)
      })
      ctx.absent.slice(0, ABS_CAP).forEach((_, k) => {
        this.v.set(k * 70, 110, 0).add(anchor); this.q.identity(); this.m.compose(this.v, this.q, this.s.set(1, 1, 1)); this.absPts.setMatrixAt(b++, this.m)
      })
    }
    this.ctxPts.count = i; this.aggPts.count = a; this.absPts.count = b
    this.ctxPts.instanceMatrix.needsUpdate = true; this.aggPts.instanceMatrix.needsUpdate = true; this.absPts.instanceMatrix.needsUpdate = true
    void tl
  }

  /** after the draft stage, a thin line of light stands above each cited report (top = surface + 220 m) */
  private layoutRise(view: ReplayView, stage: ReplayStage | undefined) {
    const reached = view.drafts.length > 0
    const tg = reached ? this.citedOrSelected(view, this.layout.nodes.filter(n => this.selected.has(n.stem))) : []
    tg.forEach((n, k) => { const o = k * 6; this.risePos[o] = n.pos.x; this.risePos[o + 1] = n.pos.y; this.risePos[o + 2] = n.pos.z; this.risePos[o + 3] = n.pos.x; this.risePos[o + 4] = 220; this.risePos[o + 5] = n.pos.z })
    this.rise.userData.targets = tg
    this.rise.geometry.setDrawRange(0, tg.length * 2)
    ;(this.rise.geometry.attributes.position as THREE.BufferAttribute).needsUpdate = true
    ;(this.rise.material as THREE.LineBasicMaterial).opacity = stage?.kind === 'draft' ? 0.9 : 0.35
    this.rise.visible = stage?.kind === 'draft' || stage?.kind === 'verify'
  }

  private showSweepAt(f: number, opacity: number) {
    const sel = this.layout.nodes.filter(n => this.selected.has(n.stem)); if (!sel.length) return
    const box = new THREE.Box3(); sel.forEach(n => { box.expandByPoint(n.pos); box.expandByPoint(n.well.head) })
    const sx = Math.max(260, box.max.x - box.min.x + 260), sz = Math.max(260, box.max.z - box.min.z + 260)
    this.sweep.visible = true
    this.sweep.position.set((box.max.x + box.min.x) / 2, this.sweepRange.y0 + (this.sweepRange.y1 - this.sweepRange.y0) * f, (box.max.z + box.min.z) / 2)
    this.sweep.scale.set(sx, 1, sz)
    ;((this.sweep.children[0] as THREE.Mesh).material as THREE.MeshBasicMaterial).opacity = opacity
    ;((this.sweep.children[1] as THREE.LineSegments).material as THREE.LineBasicMaterial).opacity = opacity * 5
  }

  // ───────────── camera
  private fitCam = new THREE.PerspectiveCamera()
  private corners = Array.from({ length: 8 }, () => new THREE.Vector3())
  /** Distance found by projecting the box corners with the real (offset) projection until they fill ~80% of the frame. */
  private fitBox(box: THREE.Box3, k: number, instant: boolean, dur = 1600) {
    const c = box.getCenter(new THREE.Vector3())
    const fc = this.fitCam; fc.copy(this.camera)
    const cs = this.corners; let i = 0
    for (const x of [box.min.x, box.max.x]) for (const y of [box.min.y, box.max.y]) for (const z of [box.min.z, box.max.z]) cs[i++].set(x, y, z)
    let dist = box.getSize(new THREE.Vector3()).length() * 1.2 + 400
    const lim = { x: 0.92, yTop: 0.66, yBot: -0.86 } // NDC: keep clear of the question header (top) and legend (bottom)
    for (let it = 0; it < 14; it++) {
      fc.position.copy(c).addScaledVector(DIR, dist); fc.lookAt(c); fc.updateMatrixWorld(); fc.updateProjectionMatrix()
      let worst = 0
      for (const p of cs) {
        this.v.copy(p).project(fc)
        worst = Math.max(worst, Math.abs(this.v.x) / lim.x, this.v.y > 0 ? this.v.y / lim.yTop : this.v.y / lim.yBot)
      }
      dist *= Math.max(0.6, Math.min(1.8, 0.35 + 0.65 * worst))
      if (Math.abs(worst - 1) < 0.03) break
    }
    dist *= k
    const pos = c.clone().addScaledVector(DIR, dist)
    if (instant) { this.camera.position.copy(pos); this.controls.target.copy(c); this.cam.active = false; this.programmatic = true; this.controls.update(); this.programmatic = false; this.dirty = true; return }
    this.cam.from.copy(this.camera.position); this.cam.to.copy(pos); this.cam.tFrom.copy(this.controls.target); this.cam.tTo.copy(c)
    this.cam.t0 = performance.now(); this.cam.dur = Math.max(900, Math.min(2400, dur)); this.cam.active = true
  }
  fitAll(instant = false, dur = 1600) { this.fitBox(this.layout.bounds.clone(), 1, instant, dur) }
  private fitNodes(ns: NodeGeom[], k: number, instant: boolean, dur: number) {
    const box = new THREE.Box3(); ns.forEach(n => { box.expandByPoint(n.pos); box.expandByPoint(n.well.head); box.expandByPoint(n.well.firstStation); this.v.copy(n.well.head).setY(n.well.minY); box.expandByPoint(this.v); n.well.curve?.points.forEach(p => box.expandByPoint(p)) })
    box.expandByScalar(160); this.fitBox(box, k, instant, dur)
  }
  resetView(view: ReplayView | null) {
    this.userMoved = false; this.cb.onUserMove(false)
    const sel = this.layout.nodes.filter(n => this.selected.has(n.stem))
    if (sel.length && view?.routed) this.fitNodes(sel, view.answered ? 1.04 : 1, this.reduced, 1400); else this.fitAll(this.reduced, 1400)
  }
  pick(stem: string | null) { this.picked = stem; if (stem) this.shownLabels.add(stem); if (this.lastView) this.applyColors(this.lastView) }

  // ───────────── loop
  private loop = (now: number) => {
    if (this.disposed) return
    this.raf = requestAnimationFrame(this.loop)
    if (document.hidden) return
    let animating = false
    if (this.cam.active) {
      const t = Math.min(1, (now - this.cam.t0) / this.cam.dur), e = easeIO(t)
      this.camera.position.lerpVectors(this.cam.from, this.cam.to, e); this.controls.target.lerpVectors(this.cam.tFrom, this.cam.tTo, e)
      if (t >= 1) this.cam.active = false
      animating = true
    }
    if (this.anims.length) animating = this.stepAnims(now) || animating
    this.programmatic = true; const changed = this.controls.update(); this.programmatic = false
    if (this.pointer) { this.doHover(); }
    if (animating || changed || this.dirty) {
      this.renderer.render(this.scene, this.camera); this.placeLabels(); this.dirty = false
      if (animating) this.countFps(now); else this.fpsT0 = 0
    }
  }
  private countFps(now: number) {
    if (!this.fpsT0) { this.fpsT0 = now; this.fpsFrames = 0; return }
    this.fpsFrames++
    const el = now - this.fpsT0
    if (el >= 1000) {
      const fps = (this.fpsFrames * 1000) / el; this.fpsSamples.push(fps); if (this.fpsSamples.length > 600) this.fpsSamples.shift()
      ;(window as any).__wa3dFps = this.fpsSamples
      this.lowWindows = fps < 20 ? this.lowWindows + 1 : 0
      if (this.lowWindows >= 3 && !navigator.webdriver) this.cb.onLowFps(fps)
      this.fpsT0 = now; this.fpsFrames = 0
    }
  }
  private stepAnims(now: number): boolean {
    let live = false, pc = 0, pc2 = 0, nodesTouched = false
    for (const a of this.anims) {
      const raw = (now - a.t0) / a.dur
      if (raw < 0) { live = true; if (a.kind === 'rise') this.setRise(a.targets, 0); continue }
      const t = Math.min(1, raw); if (raw < 1) live = true
      switch (a.kind) {
        case 'pulse': case 'secondary': {
          const mesh = a.kind === 'pulse' ? this.pulses : this.pulses2
          if (t >= 1) break
          for (const n of a.targets) {
            alongPath(n, easeOut(t), this.v); const k = 1 - 0.3 * t
            this.m.compose(this.v, this.q.identity(), this.s.set(k, k, k))
            if (a.kind === 'pulse') mesh.setMatrixAt(pc++, this.m); else mesh.setMatrixAt(pc2++, this.m)
          }
          break
        }
        case 'rise': this.setRise(a.targets, easeOut(t)); break
        case 'sweep': this.showSweepAt(easeIO(t), 0.16 * (t < 0.9 ? 1 : (1 - t) * 10 * 0.6 + 0.4)); break
        case 'pop': for (const n of a.targets) { this.nodeScale[n.index] = 1.25 + 0.6 * Math.sin(Math.PI * t) }; nodesTouched = true; break
        case 'fadeCtx': { const o = 0.85 * easeOut(t); (this.ctxPts.material as THREE.MeshBasicMaterial).opacity = o; (this.aggPts.material as THREE.MeshBasicMaterial).opacity = o; (this.absPts.material as THREE.MeshBasicMaterial).opacity = o; break }
      }
    }
    this.pulses.count = pc; this.pulses2.count = pc2
    if (pc) this.pulses.instanceMatrix.needsUpdate = true
    if (pc2) this.pulses2.instanceMatrix.needsUpdate = true
    if (nodesTouched) this.writeNodes()
    if (!live) this.anims.length = 0
    return live
  }
  private setRise(targets: NodeGeom[], f: number) {
    targets.forEach((n, k) => { this.risePos[k * 6 + 4] = n.pos.y + (220 - n.pos.y) * f })
    ;(this.rise.geometry.attributes.position as THREE.BufferAttribute).needsUpdate = true
  }

  // ───────────── interaction
  private onMove = (e: PointerEvent) => { const r = this.renderer.domElement.getBoundingClientRect(); this.pointer = { x: e.clientX - r.left, y: e.clientY - r.top } }
  private onLeave = () => { this.pointer = null; this.cb.onHover(null, 0, 0) }
  private hoverKey = ''
  private doHover() {
    const p = this.pointer!; const w = this.host.clientWidth, h = this.host.clientHeight
    this.ndc.set((p.x / w) * 2 - 1, -(p.y / h) * 2 + 1); this.ray.setFromCamera(this.ndc, this.camera)
    const hit = this.ray.intersectObjects([this.pickMesh, ...this.tubes], false)[0]
    let hov: Hover = null
    if (hit) {
      if (hit.object === this.pickMesh) {
        const n = hit.instanceId != null ? this.layout.nodes[hit.instanceId] : undefined; if (n) hov = { kind: 'node', node: n }
      } else if (hit.object.userData.well) hov = { kind: 'well', well: hit.object.userData.well }
    }
    const key = hov ? (hov.kind === 'node' ? hov.node.stem : hov.well.name) + p.x + ',' + p.y : ''
    if (key !== this.hoverKey) { this.hoverKey = key; this.cb.onHover(hov, p.x, p.y); this.renderer.domElement.style.cursor = hov?.kind === 'node' ? 'pointer' : '' }
    this.pointer = null
  }
  private onClick = () => {
    const hov = this.hoverKey ? this.lastHover() : null
    this.cb.onPick(hov)
  }
  private lastHover(): string | null { const n = this.layout.nodes.find(x => this.hoverKey.startsWith(x.stem)); return n ? n.stem : null }
  private onVis = () => { if (!document.hidden) this.dirty = true }
  private resize() {
    const w = this.host.clientWidth, h = this.host.clientHeight; if (!w || !h) return
    this.renderer.setSize(w, h, false); this.camera.aspect = w / h; this.applyOffset(); this.dirty = true
  }
  private applyOffset() {
    const w = this.host.clientWidth, h = this.host.clientHeight; if (!w || !h) return
    this.camera.setViewOffset(w, h + 160, 0, 0, w, h); this.camera.updateProjectionMatrix()
  }

  dispose() {
    this.disposed = true; cancelAnimationFrame(this.raf); this.ro.disconnect(); document.removeEventListener('visibilitychange', this.onVis)
    const el = this.renderer.domElement
    el.removeEventListener('pointermove', this.onMove); el.removeEventListener('pointerleave', this.onLeave); el.removeEventListener('click', this.onClick)
    this.controls.dispose(); this.disposables.forEach(d => d.dispose()); this.nodeSurvey.dispose(); this.nodeDate.dispose()
    this.pickMesh.dispose(); this.ctxPts.dispose(); this.aggPts.dispose(); this.absPts.dispose(); this.pulses.dispose(); this.pulses2.dispose()
    this.renderer.dispose(); el.remove(); this.labels.forEach(l => l.el.remove())
  }
}
