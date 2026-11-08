// Full verification: every view x theme x size, replays for 4 question types, every Ask state. Fails on console errors.
// Needs the API on :8000 and the app on BASE (default http://localhost:4173, i.e. `npm run preview` after build).
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'
const BASE = process.env.BASE || 'http://localhost:4173'
const API = process.env.API || 'http://localhost:8000'
mkdirSync('screenshots', { recursive: true })
const SIZES = [[1920, 1080], [1366, 768]]
const VIEWS = [['overview', '/'], ['mission', '/mission/T2-016'], ['questions', '/questions'], ['answer', '/question/T2-016'], ['generalisation', '/generalisation'],
  ['impact', '/impact'], ['archive', '/archive'], ['cost', '/cost'], ['ask', '/ask'], ['present', '/present?step=0'], ['styleguide', '/styleguide']]
const results = []; const failures = []
const b = await chromium.launch()

async function page(theme, [w, h], mocks) {
  const ctx = await b.newContext({ viewport: { width: w, height: h }, colorScheme: theme })
  await ctx.addInitScript(t => localStorage.setItem('theme', t), theme)
  const p = await ctx.newPage(); p.errs = []
  p.on('pageerror', e => p.errs.push('pageerror: ' + e))
  p.on('console', m => { if (m.type() === 'error' && !/Failed to load resource|ERR_FAILED|ERR_ABORTED/.test(m.text())) p.errs.push(m.text()) })
  if (mocks) await mocks(p)
  return p
}
const done = async (label, p) => { if (p.errs.length) failures.push([label, p.errs]); results.push(label + (p.errs.length ? '  ERRORS' : '  ok')); await p.context().close() }
const snap = (p, name, theme, w, full = true) => p.screenshot({ path: `screenshots/${name}-${theme}-${w}.png`, fullPage: full })
const settle = p => p.waitForLoadState('networkidle').then(() => p.waitForTimeout(1200))

// 1. every view, both themes, both sizes
for (const theme of ['dark', 'light']) for (const sz of SIZES) {
  const p = await page(theme, sz)
  for (const [name, route] of VIEWS) {
    await p.goto(`${BASE}/#${route}`); await settle(p)
    if (name === 'mission' || name === 'present') await p.waitForTimeout(2500)
    await snap(p, name, theme, sz[0], !['mission', 'present'].includes(name))
  }
  await done(`views ${theme} ${sz.join('x')}`, p)
}

// 2. replays: answered, multi-report, archive-wide, abstain (run to the end at 4x)
for (const [name, id] of [['answered', 'T2-001'], ['multi', 'T2-017'], ['archive', 'T2-020'], ['abstain', 'T2-032']]) {
  for (const theme of ['dark', 'light']) {
    const p = await page(theme, [1920, 1080])
    await p.goto(`${BASE}/#/mission/${id}`); await p.waitForSelector('.mc'); await p.waitForTimeout(500)
    await p.keyboard.press('s'); await p.keyboard.press('s')
    if (theme === 'dark') { await p.waitForSelector('.step.now'); await p.waitForTimeout(2200); await snap(p, `replay-${name}-mid`, theme, 1920, false) }
    await p.waitForSelector('.resolve', { timeout: 60000 }); await p.waitForTimeout(1200)
    await snap(p, `replay-${name}-end`, theme, 1920, false)
    await done(`replay ${name} ${theme}`, p)
  }
}

// 3. Ask states
const sse = (events) => events.map((e, i) => `event: ${e.stage}\nid: ${i + 1}\ndata: ${JSON.stringify(e.data)}\n\n`).join('')
const real = id => fetch(`${API}/questions/${id}`).then(r => r.json())
const askState = async (label, setup, act, sel, shot) => {
  const p = await page('dark', [1920, 1080], setup)
  await p.goto(`${BASE}/#/ask`); await p.waitForSelector('#q', { timeout: 90000 })
  await act(p); await p.waitForSelector(sel, { timeout: 60000 }); await p.waitForTimeout(2500)
  await snap(p, shot, 'dark', 1920, true); await done(`ask: ${label}`, p)
}
const type = q => async p => { await p.fill('#q', q); await p.keyboard.press('Control+Enter') }
const q16 = await real('T2-016'), q32 = await real('T2-032')
const reqText = async route => (await real('T2-016')).question

// answered (real, cached) and abstain (real, cached)
await askState('answered', null, type(q16.question), '.answer-card', 'ask-answered')
await askState('abstain', null, type(q32.question), '.answer-card.abstain', 'ask-abstain')
// needs_clarification (real, free)
await askState('needs_clarification', null, type('What happened?'), '.clarify', 'ask-clarification')
// early abstain: a well that is not in the archive (real, free, no model)
await askState('early abstain (unknown well)', null, type('What was the kick-off depth on well 15/9-F-99 on 2014-01-01?'), '.answer-card', 'ask-early-abstain')
// rate limited (real: hammer the free path until the server says 429)
{
  const p = await page('dark', [1920, 1080]); await p.goto(`${BASE}/#/ask`); await p.waitForSelector('#q')
  let hit = false
  for (let i = 0; i < 10 && !hit; i++) { await p.fill('#q', `What happened? ${i}`); await p.keyboard.press('Control+Enter'); await p.waitForTimeout(600); hit = (await p.locator('[data-state=rate]').count()) > 0 }
  if (!hit) failures.push(['ask: rate limited', ['429 state not reached']])
  await p.waitForTimeout(800); await snap(p, 'ask-ratelimited', 'dark', 1920, false); await done('ask: rate limited (real 429)', p)
}
// states below need server config we do not change, so they are mocked from real payloads
const streamMock = (events, status = 200) => async p => { await p.route('**/ask/stream', r => r.fulfill({ status, contentType: 'text/event-stream', body: sse(events) })) }
const routeEv = { stage: 'route', data: q16.trace.events[0].data }
await askState('MOCK budget reached', streamMock([routeEv, { stage: 'error', data: { code: 'budget_exhausted', message: 'budget used up' } }]), type('A brand new question about well 15/9-F-1-C on 2014-03-26'), '[data-state=budget]', 'ask-budget')
await askState('MOCK timeout', streamMock([], 504), async p => { await p.route('**/ask/stream', r => r.fulfill({ status: 504, contentType: 'application/json', body: JSON.stringify({ detail: { code: 'timeout', message: 'timed out' } }) })); await type('slow one')(p) }, '[data-state=timeout]', 'ask-timeout')
const ne = JSON.parse(JSON.stringify(q16)); ne.id = 'ASK-mock0000'; ne.set = 'adhoc'; ne.status = 'not_evaluated'; ne.confidence = 0; ne.verified = false; ne.flags = ['not_evaluated']; ne.source = 'none'; ne.cited_records = []
ne.answer = 'NOT EVALUATED: no API key is configured and this question is not in the answer cache, so no model was called.'; ne.rationale = null; ne.evidence = ''
ne.trace.model_calls = []; ne.trace.verifier = []; ne.trace.contexts = []; ne.trace.events = [q16.trace.events[0]]
await askState('MOCK NOT EVALUATED', streamMock([routeEv, { stage: 'result', data: ne }]), type('A brand new question about well 15/9-F-1-C on 2014-03-26'), '.state', 'ask-not-evaluated')
{ // live mode off banner + server waking gate
  const off = async p => { await p.route('**/health', async r => { const j = await (await r.fetch()).json(); j.live_mode = false; r.fulfill({ json: j }) }) }
  await askState('MOCK live mode off', off, async () => {}, '.callout.abstain', 'ask-live-off')
  const p = await page('dark', [1920, 1080], async p => { let n = 0; await p.route('**/health', r => (++n < 4 ? r.abort() : r.continue())) })
  await p.goto(`${BASE}/#/ask`); await p.waitForSelector('.gate', { timeout: 20000 }); await p.waitForTimeout(5200); await snap(p, 'ask-server-waking', 'dark', 1920, false)
  await p.waitForSelector('#q', { timeout: 30000 }); await done('ask: MOCK server waking', p)
}

await b.close()
console.log(results.join('\n'))
if (failures.length) { console.log('\nFAILURES'); for (const [l, e] of failures) console.log(l, e); process.exit(1) }
console.log('\nALL CHECKS PASSED, no console errors')
