// Regenerates every documentation screenshot in one command, against the local API.
//
//   node docs/capture.mjs                       all shots, both variants
//   node docs/capture.mjs --only overview_hero,cost_view
//   node docs/capture.mjs --variants dark       dark 1920x1080 only
//
// Needs: the API on :8000 (uvicorn web.server.app:app --port 8000) and the built app served on :5173
// (npx vite preview --port 5173 --strictPort). Override with API=... BASE=...
// Output: docs/shots/<id>_<theme>_<width>.png (clean) and ..._annotated.png, plus docs/shots/manifest.json and docs/facts.json.
// Callouts are drawn by injecting overlay markers into the page (see annotate()). Nothing is edited by hand.
import { chromium } from 'playwright'
import { mkdirSync, writeFileSync, readFileSync, existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { SHOTS, Q } from './shots.config.mjs'

const HERE = dirname(fileURLToPath(import.meta.url))
const OUT = join(HERE, 'shots')
const API = process.env.API || 'http://localhost:8000'
const BASE = (process.env.BASE || 'http://localhost:5173/').replace(/\/?$/, '/')
const arg = n => { const i = process.argv.indexOf('--' + n); return i > -1 ? process.argv[i + 1] : null }
const only = arg('only')?.split(',')
const variantNames = arg('variants')?.split(',') ?? ['dark', 'light']
const VARIANTS = { dark: { theme: 'dark', w: 1920, h: 1080 }, light: { theme: 'light', w: 1366, h: 768 } }
mkdirSync(OUT, { recursive: true })

const j = async p => (await fetch(API + p)).json()
const sleep = ms => new Promise(r => setTimeout(r, ms))

// ───────────── page-side helpers (serialised into the page)
const FIND = `(sel) => sel.startsWith('xpath=') ? document.evaluate(sel.slice(6), document, null, 9, null).singleNodeValue : document.querySelector(sel)`
function annotate({ marks, finder }) {
  const find = eval(finder) // eslint-disable-line no-eval
  const cs = getComputedStyle(document.documentElement)
  const brand = cs.getPropertyValue('--brand').trim() || '#fe0000', fill = cs.getPropertyValue('--brand-fill').trim() || '#e61100', bg = cs.getPropertyValue('--bg').trim() || '#000'
  const layer = document.createElement('div'); layer.id = '__ann'
  layer.style.cssText = 'position:fixed;left:0;top:0;width:100vw;height:100vh;pointer-events:none;z-index:2147483647'
  const used = [], placed = [], vw = innerWidth, vh = innerHeight
  for (const m of marks) {
    const el = find(m.sel); if (!el) continue
    const r = el.getBoundingClientRect(); if (r.width < 4 || r.height < 4) continue
    const x0 = Math.max(r.left, 0), y0 = Math.max(r.top, 0), x1 = Math.min(r.right, vw), y1 = Math.min(r.bottom, vh)
    if (x1 - x0 < 10 || y1 - y0 < 10) continue
    const n = used.length + 1
    const box = document.createElement('div')
    box.style.cssText = `position:absolute;left:${x0 - 3}px;top:${y0 - 3}px;width:${x1 - x0 + 6}px;height:${y1 - y0 + 6}px;border:2px solid ${brand};border-radius:10px;box-shadow:0 0 0 1px rgba(0,0,0,.35)`
    let bx = Math.max(4, x0 - 14), by = Math.max(4, y0 - 14)
    while (placed.some(p => Math.abs(p.x - bx) < 34 && Math.abs(p.y - by) < 34)) bx += 36
    placed.push({ x: bx, y: by })
    const b = document.createElement('div'); b.textContent = String(n)
    b.style.cssText = `position:absolute;left:${bx}px;top:${by}px;width:28px;height:28px;border-radius:50%;background:${fill};color:#fff;font:700 15px/24px Inter Variable,Inter,system-ui,sans-serif;text-align:center;border:2px solid ${bg};box-sizing:border-box;box-shadow:0 2px 6px rgba(0,0,0,.45)`
    layer.append(box, b); used.push({ n, label: m.label })
  }
  document.body.append(layer); return used
}
const clearAnn = () => document.getElementById('__ann')?.remove()
const scrollToEl = ({ sel, off, finder }) => { const el = (eval(finder))(sel); if (!el) return false; window.scrollTo(0, el.getBoundingClientRect().top + scrollY - off); return true } // eslint-disable-line no-eval

// ───────────── context + mocks
async function newPage(browser, v, shot) {
  const ctx = await browser.newContext({ viewport: { width: v.w, height: v.h }, colorScheme: v.theme })
  const focus = shot.threeD ? (shot.focus ? '1' : '0') : '0'
  await ctx.addInitScript(([t, f]) => {
    localStorage.setItem('theme', t); localStorage.setItem('wa-3d-focus', f); localStorage.removeItem('rail')
    const s = document.createElement('style'); s.textContent = '*{cursor:none!important}::-webkit-scrollbar{display:none}html{scrollbar-width:none}'
    document.addEventListener('DOMContentLoaded', () => document.head.appendChild(s))
  }, [v.theme, focus])
  const p = await ctx.newPage(); p.errs = []
  p.on('pageerror', e => p.errs.push(String(e))); p.on('console', m => { if (m.type() === 'error' && !/Failed to load resource|ERR_FAILED|ERR_ABORTED|429|504/.test(m.text())) p.errs.push(m.text()) })
  return p
}
const CORS = { 'access-control-allow-origin': '*', 'access-control-expose-headers': 'Retry-After' }
const sse = evs => evs.map((e, i) => `event: ${e.stage}\nid: ${i + 1}\ndata: ${JSON.stringify(e.data)}\n\n`).join('')
async function applyMock(p, kind, v) {
  if (kind === 'xml_only') {
    const base = await j('/questions/T2-001'); const rec = JSON.parse(readFileSync(join(HERE, 'fixtures', 'xml_only_record.json'), 'utf8'))
    base.cited_records = [rec]; base.answer = 'tightWell is 0 in the XML. The PDF prints Y, but the XML is authoritative.'; base.rationale = 'Composed for documentation: a real XML-only record shown in the evidence lens.'
    await p.route('**/questions/T2-001', r => r.fulfill({ json: base, headers: CORS }))
  } else if (kind === 'waking') {
    let n = 0; await p.route('**/health', r => (++n < 4 ? r.abort() : r.continue()))
  } else if (kind === 'live_off') {
    await p.route('**/health', async r => { const x = await (await r.fetch()).json(); x.live_mode = false; r.fulfill({ json: x, headers: CORS }) })
  } else if (kind === 'budget') {
    const ev = (await j('/questions/' + Q.single)).trace.events[0]
    await p.route('**/ask/stream', r => r.fulfill({ status: 200, contentType: 'text/event-stream', headers: CORS, body: sse([ev, { stage: 'error', data: { code: 'budget_exhausted', message: 'budget used up' } }]) }))
  } else if (kind === 'timeout') {
    await p.route('**/ask/stream', r => r.fulfill({ status: 504, contentType: 'application/json', headers: CORS, body: JSON.stringify({ detail: { code: 'timeout', message: 'timed out' } }) }))
  } else if (kind === 'not_evaluated') {
    const d = await j('/questions/' + Q.single); const ne = JSON.parse(JSON.stringify(d))
    Object.assign(ne, { id: 'ASK-mock0000', set: 'adhoc', status: 'not_evaluated', confidence: 0, verified: false, flags: ['not_evaluated'], source: 'none', cited_records: [], rationale: null, evidence: '' })
    ne.answer = 'NOT EVALUATED: no API key is configured and this question is not in the answer cache, so no model was called.'
    ne.trace.model_calls = []; ne.trace.verifier = []; ne.trace.contexts = []; ne.trace.events = [d.trace.events[0]]
    await p.route('**/ask/stream', r => r.fulfill({ status: 200, contentType: 'text/event-stream', headers: CORS, body: sse([d.trace.events[0], { stage: 'result', data: ne }]) }))
  } else if (kind === 'rate429') {
    await p.route('**/ask/stream', r => r.fulfill({ status: 429, contentType: 'application/json', headers: { ...CORS, 'retry-after': '42' }, body: JSON.stringify({ detail: { code: 'rate_limited', message: 'Too many questions. Slow down.' } }) }))
  }
}

// ───────────── stepping and asking
async function toStage(p, idx, keys) {
  await p.waitForSelector('.stepper .step, .mc3-hud, .stepper', { timeout: 60000 })
  await p.waitForTimeout(400)
  for (let i = 0; i < 14; i++) await p.keyboard.press(keys[0])
  for (let i = 0; i <= idx; i++) await p.keyboard.press(keys[1])
}
async function resolveText(t) { return /^[TG]-?\d|^T2-\d|^G-\d/.test(t) ? (await j('/questions/' + t)).question : t }
async function doAsk(p, shot) {
  const a = shot.ask
  await p.waitForSelector('#q', { timeout: 90000 })
  if (a.rate) {
    if (shot.rateReal) {
      let hit = false
      for (let i = 0; i < 12 && !hit; i++) { await p.fill('#q', `What happened? ${i}`); await p.keyboard.press('Control+Enter'); await p.waitForTimeout(650); hit = (await p.locator('[data-state=rate]').count()) > 0 }
      if (!hit) throw new Error('429 state not reached')
    } else { await p.fill('#q', 'A question that is sent too soon after the others'); await p.keyboard.press('Control+Enter') }
  } else { await p.fill('#q', await resolveText(a.text)); await p.keyboard.press('Control+Enter') }
  await p.waitForSelector(shot.focusOn, { timeout: 90000 })
  await p.waitForTimeout(a.rate ? 900 : 3200)
}

// ───────────── one shot, one variant
async function capture(browser, shot, vname, manifestEntry) {
  const v = VARIANTS[vname]; const p = await newPage(browser, v, shot)
  try {
    const kind = shot.ask?.rate ? (vname === 'dark' ? null : 'rate429') : shot.mock
    if (kind) await applyMock(p, kind, v)
    const url = `${BASE}?api=${encodeURIComponent(API)}#${shot.route}`
    await p.goto(url); await p.waitForLoadState('networkidle').catch(() => {})
    const present = shot.route.startsWith('/present')
    if (shot.ask) { if (shot.ask.rate && vname === 'dark') shot.rateReal = true; await doAsk(p, shot); shot.rateReal = false }
    else if (shot.mock === 'waking') await p.waitForSelector('.gate', { timeout: 20000 })
    else if (shot.threeD) {
      await p.waitForSelector(present ? '.tour-body .mc, .tour-body .stepper' : '.mc', { timeout: 90000 })
      await p.getByRole('button', { name: '3D', exact: true }).click(); await p.waitForSelector('.mc3-canvas', { timeout: 40000 })
      await toStage(p, shot.stage ?? 0, present ? [',', '.'] : ['ArrowLeft', 'ArrowRight'])
    } else if (shot.stage != null) {
      await p.waitForSelector(present ? '.tour-body .mc' : '.mc', { timeout: 90000 }); await toStage(p, shot.stage, present ? [',', '.'] : ['ArrowLeft', 'ArrowRight'])
    } else if (shot.prep === 'archive') { await p.waitForSelector('.dotg', { timeout: 30000 }); await p.locator('.dotg').nth(9).click() }
    else await p.waitForSelector('main .page, .tour-frame', { timeout: 60000 })
    if (shot.id === 'overview_hero') await p.waitForTimeout(1400)
    if (shot.id.startsWith('evidence_highlight')) { await p.waitForSelector('.page-wrap .hl', { timeout: 30000 }) }
    if (shot.id === 'cost_view' || shot.id === 'generalisation') await p.waitForTimeout(900)
    const fo = shot.focusOn ?? (shot.id.startsWith('evidence_') ? '.lens' : null)
    if (fo && !shot.ask) await p.evaluate(scrollToEl, { sel: fo, off: shot.focusOff ?? (shot.id === 'impact_calculator' ? 260 : 24), finder: FIND })
    else if (fo && shot.ask) await p.evaluate(scrollToEl, { sel: fo, off: 24, finder: FIND })
    if (shot.id === 'overview_principles') await p.evaluate(scrollToEl, { sel: '.principles', off: 150, finder: FIND })
    if (shot.id.startsWith('trace_')) await p.evaluate(scrollToEl, { sel: shot.focusOn, off: 16, finder: FIND })
    await p.waitForTimeout(shot.settle ?? (shot.threeD ? 1200 : 900))
    const base = `${shot.id}_${v.theme}_${v.w}`
    await p.screenshot({ path: join(OUT, base + '.png') })
    const used = await p.evaluate(annotate, { marks: shot.marks.map(([sel, label]) => ({ sel, label })), finder: FIND })
    await p.screenshot({ path: join(OUT, base + '_annotated.png') })
    await p.evaluate(clearAnn)
    manifestEntry.variants[vname] = { clean: base + '.png', annotated: base + '_annotated.png', width: v.w, height: v.h, theme: v.theme, marks: used, errors: p.errs }
    return p.errs.length ? `ERR ${p.errs[0].slice(0, 80)}` : `ok (${used.length}/${shot.marks.length} callouts)`
  } finally { await p.context().close() }
}

// ───────────── facts from the live API (every figure in the guides comes from here)
async function facts() {
  const [h, qs, a, c, g] = await Promise.all([j('/health'), j('/questions'), j('/archive'), j('/costs'), j('/generalisation')])
  const by = {}; qs.questions.forEach(q => { by[q.status] = (by[q.status] ?? 0) + 1 })
  const modes = {}; qs.questions.forEach(q => { modes[q.router_mode] = (modes[q.router_mode] ?? 0) + 1 })
  const f = {
    captured_at: new Date().toISOString(), api: API, version: h.version, live_mode: h.live_mode, models: h.models,
    questions: { total: qs.count, sets: qs.sets, by_status: by, by_mode: modes, verified: qs.questions.filter(q => q.status !== 'not_evaluated' && !q.flags.includes('verifier_failed')).length },
    archive: { reports: a.reports.length, wellbores: a.wellbores.length, wells: a.wells.length, records: a.record_counts.total, derived_notes: a.record_counts.derived_notes, indexed_records: h.details.records, pdf_pages: a.reports.reduce((s, r) => s + r.pages, 0) },
    cost: { ledger_usd: c.ledger.cost_usd, per_challenge_question_usd: c.derived_from_cache.cost_per_challenge_question_usd, calls: c.ledger.calls, haiku_share_of_calls: c.model_mix.find(m => /haiku/i.test(m.model))?.share_of_calls, haiku_share_of_cost: c.model_mix.find(m => /haiku/i.test(m.model))?.share_of_cost, server_budget_usd: c.budget.server_budget_usd },
    generalisation: g.summary ? { questions: g.summary.questions, mean_score: g.summary.mean_score, baseline_mean_score: g.summary.baseline_mean_score, by_category: g.summary.by_category } : null,
    rate_limit: h.details.rate_limit,
    t2016: await j('/questions/' + Q.single).then(d => ({ answer: d.answer, confidence: d.confidence, verified: d.verified, evidence: d.evidence })),
  }
  writeFileSync(join(HERE, 'facts.json'), JSON.stringify(f, null, 2)); return f
}

const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] })
const manifestPath = join(OUT, 'manifest.json')
const old = existsSync(manifestPath) ? JSON.parse(readFileSync(manifestPath, 'utf8')) : { shots: {} }
const todo = SHOTS.filter(s => !only || only.includes(s.id)); const failures = []
await facts(); console.log('facts.json written')
for (const vname of variantNames) for (const shot of todo) {
  const entry = old.shots[shot.id] ?? { variants: {} }
  Object.assign(entry, { id: shot.id, composed: !!shot.mock && ['xml_only', 'not_evaluated'].includes(shot.mock), mocked: shot.mock ?? null })
  let res
  for (let t = 0; t < 2; t++) { try { res = await capture(browser, shot, vname, entry); break } catch (e) { res = 'FAIL ' + String(e).split('\n')[0].slice(0, 110); await sleep(1500) } }
  if (res.startsWith('FAIL') || res.startsWith('ERR')) failures.push([vname, shot.id, res])
  old.shots[shot.id] = entry; console.log(vname.padEnd(5), shot.id.padEnd(28), res)
  writeFileSync(manifestPath, JSON.stringify({ generated: new Date().toISOString(), shots: old.shots }, null, 2))
}
await browser.close()
if (failures.length) { console.log('\nPROBLEMS'); failures.forEach(f => console.log(f.join(' | '))); process.exit(1) }
console.log('\nAll shots captured.')
