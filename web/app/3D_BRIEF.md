# 3D brief: Mission control scene

The 2D replay is finished and is the fallback. This session only has to **draw**. All data shaping is done in
[src/lib/adapter.ts](src/lib/adapter.ts) and playback in [src/lib/useReplay.ts](src/lib/useReplay.ts). The 3D scene must not call
the API itself.

## 1. Where it plugs in

| Piece | File |
|---|---|
| Slot component (placeholder to replace) | [src/three/MissionControl3D.tsx](src/three/MissionControl3D.tsx) |
| Loaded lazily by | [src/views/Mission.tsx](src/views/Mission.tsx) (`lazy(() => import('../three/MissionControl3D'))`), shown when the 2D/3D toggle is on 3D |
| Props | `{ timeline: ReplayTimeline, world: World, replay: ReplayApi }` |

- `replay.idx` is the current stage index (-1 = not started). Draw as a pure function of `idx`; stepping backwards then works for free.
  `replay.playing`, `replay.speed` (0.5, 1, 2, 4) and `replay.goto(i)` are available. Controls and keyboard (Space, arrows, R, S) are already
  rendered by Mission control, so **do not add playback UI**, only the scene.
- Keep the default export and the props. Heavy imports (three.js, loaders) belong inside `src/three/` so they stay out of the main chunk.
  Add the dependency to `package.json` yourself and tell the owner (rule: no new libraries without asking).
- **Presenter tour:** [src/views/Present.tsx](src/views/Present.tsx) renders `<Replay2D>` in its three story steps. To offer 3D there, add a `2D | 3D`
  segmented control in `Story` (same pattern as Mission.tsx) and render `<MissionControl3D timeline={tl} world={world} replay={r} />`
  instead of `<Replay2D/>`. Tour keys (Space, R, S, comma, period) already drive `r`.
- Fallback: if WebGL is unavailable, render nothing special; Mission control can flip the toggle back to 2D. Add a `try/catch` around
  context creation and call back with a message, never a blank panel.

## 2. Data available

### 2.1 `world: World` (from `buildWorld(archive, trajectories)`)

```ts
interface World {
  wellbores: WorldWellbore[]            // 8 wellbores, natural-sorted by name
  reportByStem: Map<string, WorldReport> // key = report stem, e.g. "15_9_F_1_C_2014_03_26"
  maxOrdinal: number                    // most reports in one wellbore (4)
  approximate: boolean                  // trajectories are approximate: ALWAYS say so on screen
  caveats: string[]                     // from /trajectories, show them
}
interface WorldWellbore {
  name: string        // "15/9-F-1-C" (canonical)
  well: string        // parent slot, "15/9-F-1"
  reports: WorldReport[]                // oldest to newest
  first: string; last: string           // ISO dates
  trajectory: { status: 'ok' | 'skipped'; reason: string | null; approximate: boolean; stations: Station[] } | null
}
interface WorldReport {
  stem: string; file: string; pdfFile: string; wellbore: string; date: string
  t: number; ordinal: number            // epoch ms; index within its wellbore
  records: number; pages: number
  along: number                         // 0..1 position by report date between the wellbore's first and last report
  anchor: { x: number; y: number; tvd: number; md: number | null; approximate: true } | null
                                        // last surveyed station on or before the report date; null if none
}
interface Station { record_id: string; report_date: string; md: number; incl?: number; azi?: number; tvd_reported?: number; x: number; y: number; tvd: number }
```

Real example (trimmed, from `GET /trajectories`):

```json
{ "wellbore": "15/9-F-1-C", "status": "ok", "approximate": true, "stations_used": 46,
  "stations": [ { "record_id": "F1C-20140222-SURVEY-01", "report_date": "2014-02-22", "md": 145.9,
                  "incl": 0.0, "azi": 302.24, "tvd_reported": 145.9, "x": 0.0, "y": 0.0, "tvd": 145.9 } ] }
```

**Hard facts about the trajectories (read before modelling):**
- `x` is east and `y` is north, in metres, **relative to the first station of each wellbore**. Absolute field coordinates are not in the data.
  Every wellbore starts at (0, 0). Do not invent surface locations. Place wellbores either at a shared origin or on a plain, clearly labelled
  schematic layout (for example evenly spaced on a circle) and state "layout schematic, trajectories relative".
- `tvd` is true vertical depth in metres, positive down. The first station starts at its reported TVD (not 0), so shift each trajectory
  up to the surface or draw it from its first station and label the offset.
- Stations are sparse (4 to 46 per wellbore, in the printed survey tables), so the path is minimum-curvature between few points. Smooth with
  a spline for display but never extrapolate beyond the first and last station.
- `15/9-F-1` is `skipped` (no usable stations: azimuth missing in all 7, and -999.99 is missing, never a value). Draw it as a short, dashed,
  labelled stub or omit it with a visible note. `15/9-19-A` is a 1980 placeholder date and its trajectory is real.
- Several reports of one wellbore carry the same survey table; `report.anchor` therefore often equals the wellbore's last station.
  If you want reports spread along the well, use `along` (by date) for position along the path length, and fall back to `anchor`.

### 2.2 `timeline: ReplayTimeline` (from `timelineFromDetail(detail)`, built from the real `trace.events`)

```ts
interface ReplayTimeline { question: string; stages: ReplayStage[]; complete: boolean; final: QuestionDetail | null }
interface ReplayStage { index: number; kind: StageKind; title: string; plain: string
  realMs: number | null     // server t_ms of the first source event (cached replays are ~0-200 ms, so do not time the scene from it)
  durationMs: number        // presentation dwell at 1x, already tuned for the 2D replay; reuse it
  seq: number[]; payload: any }
type StageKind = 'parse'|'route'|'gate'|'context'|'draft'|'verify'|'second_pass'|'escalate'|'arbitrate'|'answer'
```

Use `viewAt(timeline, idx)` ([adapter.ts](src/lib/adapter.ts)) to get the derived state at any stage instead of re-deriving it:
`selected` (report stems the router opened), `candidates` (wellbore names), `contextCount` (stem to number of records in context),
`absent` (ABSENT records with `reports_searched`, `records_searched`, `considered_and_rejected`), `citedIds`, `citedReports`, `verifies`, `answered`.
`recordToReport(timeline)` maps every record id to its report stem.

### 2.3 Stage events and what each means visually

| kind | payload | meaning | scene intent |
|---|---|---|---|
| `parse` | `RouterTrace` | code read well/date/topic from the question | labels appear over the named wellbores / dates |
| `route` | `RouterTrace` (`reports_selected[]`, `wells_considered[]`, `mode`, `gate`) | router opened these reports; the rest stay closed. If `gate` is set nothing was opened | selected report nodes light (blue); other wellbores recede. Archive-wide opens all 32 |
| `gate` | `{gate,message,examples}` | question too vague, no search, no model | scene idles; a calm "needs detail" state |
| `context` | `ContextTrace` (`records[]`, `aggregates[]`, `absent[]`) | evidence gathered (neutral), computed aggregates, ABSENT records (field does not exist) | records stream into opened reports (neutral); aggregates drawn as a distinct marker; for `absent`, light **sweeps along the opened reports and finds nothing** (amber), then names what was searched |
| `draft` | `ModelCall[]` | a small model drafted from that evidence (`reply_cited[]` = records it cited) | cited records pulse (green) and travel to the answer anchor |
| `verify` | `VerifyTrace[]` (`checks[]` with `pass`/`flag`/`fail`/`not_applicable`) | code re-checked every claim | checks tick one by one; a flagged check is **violet**, never red |
| `escalate` | `{trigger, model, reason}` | verifier objected; a larger model retries | a second, larger pass of light along the same reports. Only if it happened |
| `second_pass` | `{reason}` | context enriched, question asked again | only if it happened |
| `arbitrate` | `{retry, model, reason}` | two drafts disagreed, an arbiter chose | only if it happened |
| `answer` | `{status, confidence, source, flags, detail}` | answer and rule-based confidence resolve | cited records settle (green), abstentions settle amber |

Example stage list for T2-017 (real): `parse, route, context, draft, verify, escalate, draft, verify, answer`.
For T2-032 (abstention): `parse, route, context, draft, verify, answer` with `context.absent[0] = { id: "ABSENT-mud_logging", reports_searched: 1, records_searched: 50, considered_and_rejected: [...] }`.

## 3. Visual intent

- **The real field.** Wells are drawn in their true surveyed trajectories (minimum curvature, from `world`), TVD downwards, as thin luminous
  lines on a dark, quiet ground. A faint grid and depth ticks (every 500 m TVD) give scale. Mark trajectories "approximate" (on screen, not just here).
- **Reports as nodes along each well**, positioned by `along`. One node per report, small. Sized by `records` (sqrt scale). Same dates as the 2D lanes.
- **The search as light moving through the archive.** Selected reports light blue; a travelling pulse runs along each opened wellbore through its
  report nodes; ABSENT shows the pulse passing through and finding nothing (amber). Cited records leave their report node as green sparks and converge on
  a fixed answer anchor (a HUD element in screen space, not a world object).
- **Restraint.** Heirs red is for the selection ring and the playhead only (under about 5% of pixels). Status colours stay as in tokens. No bloom
  stack, no lens flare, no looping ambient motion, no parallax decoration. Camera moves are purposeful: a slow dolly to frame the opened wellbores on
  `route`, held still afterwards. Respect `prefers-reduced-motion` by cutting camera moves and replacing pulses with a fade.
- **Legibility from the back of a room.** Labels in screen space, 16 px minimum (the presenter mode scales root font size to 125%),
  wellbore names in the mono face, never hidden behind geometry (use an HTML overlay or sprite labels with depth test off).
- **Honesty.** Everything drawn comes from `world` and `timeline`. Do not fabricate formation layers, rig models, seabed, or coordinates.

## 4. Performance budget

- 60 fps on a mid-range laptop (integrated GPU, 1366x768 to 1920x1080, devicePixelRatio capped at 2).
- Scene size is small, so keep it small: 8 wellbore tubes (max about 46 stations each, spline-sampled to at most 128 points) and 32 report nodes.
  Cap total triangles around 150k and draw calls under 100.
- **Instancing:** one `InstancedMesh` for the 32 report nodes (per-instance colour and scale, updated from `viewAt`, not per-frame allocation). One
  `Line2`/tube batch for trajectories. A small pooled `InstancedMesh` (at most 64) for cited-record sparks.
- No per-frame allocations in the render loop; reuse vectors and colours. Update uniforms/instance attributes only when `replay.idx` changes or while
  a tween runs. Render on demand (`frameloop: 'demand'` or equivalent) when nothing animates.
- **Lazy loading:** keep three.js and any loader out of the main bundle (the slot is already behind `lazy()`). The 3D chunk loads only when the user picks 3D.
  Target under 600 kB gzip for the 3D chunk. No textures or models fetched at run time (offline requirement): procedural geometry only.
- Dispose geometries, materials and the renderer on unmount. Pause rendering when the tab is hidden (`document.hidden`) and when the 3D view is not selected.
- Test on a throttled CPU (4x slowdown in DevTools) and confirm it stays smooth.

## 5. Theme tokens to reuse

Defined in [src/styles/tokens.css](src/styles/tokens.css). Read them at run time so dark and light both work
(`getComputedStyle(document.documentElement).getPropertyValue('--route')`, and re-read when `document.documentElement.dataset.theme` changes).

| purpose | token | dark | light |
|---|---|---|---|
| ground / canvas | `--bg`, `--surface-1`, `--surface-2` | #0e0c0b, #151311, #1c1917 | #f6f3f0, #ffffff, #fbf9f7 |
| hairlines, grid | `--line`, `--line-strong`, `--grid-line` | warm white at 9%, 18%, 5% | warm black at 10%, 20%, 5% |
| text / labels | `--text`, `--text-2`, `--text-3` | #f5f0eb, #bdb4ac, #9a918a | #1a1613, #5a524c, #6f665f |
| selection, playhead (sparingly) | `--brand` | #fe0000 | #e00000 |
| router-selected | `--route` | #7db2ff | #1c5bc0 |
| context records | `--ctx` | #b9b0a8 | #5a524c |
| cited / verified | `--ok` | #4fd8a8 | #0b7556 |
| abstain / searched, not found | `--abstain` | #f2b544 | #8f5200 |
| flag (verifier flag) | `--flag` | #c9a2ff | #6a32b0 |

Never use red to mean failure. Every status needs a shape or label as well as colour (the 2D legend is the reference). Motion tokens: 150 to 400 ms,
`--ease-out: cubic-bezier(0.16, 1, 0.3, 1)`. Fonts: Inter Variable (UI), JetBrains Mono Variable (IDs), already bundled.

## 6. Acceptance checklist for the 3D session

1. `MissionControl3D` draws `world` and follows `replay.idx`; scrubbing, stepping back and replay all work.
2. Abstention (T2-032) shows the empty sweep and an amber result. Archive-wide (T2-020) opens all 32 report nodes. Multi-report (T2-017) opens four.
3. Trajectories labelled approximate and relative; `15/9-F-1` handled honestly.
4. 60 fps check recorded; first load of the 3D chunk measured.
5. Works offline, no console errors, reduced motion honoured, both themes.
6. 2D remains the default and the fallback. Presenter tour can toggle 3D per step.
