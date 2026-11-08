// 3D verification: stage-by-stage screenshots for T2-016, T2-017, T2-020, T2-031; both themes x 1920/1366; hover + click;
// presenter story (c) in 3D; frame rate during a 1x replay. Fails on any console error. Output: screenshots/3d/.
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'
const BASE = process.env.BASE || 'http://localhost:3000'
mkdirSync('screenshots/3d', { recursive: true })
const Q = [['single', 'T2-016'], ['multi', 'T2-017'], ['archive', 'T2-020'], ['abstain', 'T2-031']]
const b = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] })
const out = []; const fail = []
async function open(theme, w, h, route) {
  const ctx = await b.newContext({ viewport: { width: w, height: h }, colorScheme: theme })
  await ctx.addInitScript(([t, f]) => { localStorage.setItem('theme', t); localStorage.setItem('wa-3d-focus', f) }, [theme, process.env.FOCUS ?? '0'])
  const p = await ctx.newPage(); p.errs = []
  p.on('console', m => { if (m.type() === 'error') p.errs.push(m.text()) }); p.on('pageerror', e => p.errs.push(String(e)))
  await p.goto(`${BASE}/#${route}`); await p.waitForSelector('.mc', { timeout: 90000 })
  if (!route.startsWith('/present')) { await p.getByRole('button', { name: '3D', exact: true }).click(); await p.waitForSelector('.mc3-canvas', { timeout: 30000 }) }
  return p
}
const close = async (label, p) => { if (p.errs.length) fail.push([label, p.errs]); out.push(label + (p.errs.length ? '  ERRORS' : '  ok')); await p.context().close() }

// 1. stage-by-stage, dark 1920
for (const [name, id] of Q) {
  const p = await open('dark', 1920, 1080, `/mission/${id}`)
  const n = await p.locator('.stepper .step').count()
  for (let i = 0; i < n; i++) {
    await p.locator('.stepper .step').nth(i).click(); await p.waitForTimeout(i === 0 ? 2600 : 2300)
    const kind = (await p.locator('.stepper .step').nth(i).innerText()).trim().toLowerCase().replace(/[^a-z0-9]+/g, '-')
    await p.screenshot({ path: `screenshots/3d/${name}-${String(i + 1).padStart(2, '0')}-${kind}-dark-1920.png` })
  }
  await close(`stages ${name} (${id}) ${n} stages`, p)
}
// 2. end state, both themes x sizes (light 1920, dark+light 1366)
for (const [theme, w, h] of [['light', 1920, 1080], ['dark', 1366, 768], ['light', 1366, 768]]) for (const [name, id] of Q) {
  const p = await open(theme, w, h, `/mission/${id}`)
  const n = await p.locator('.stepper .step').count(); await p.locator('.stepper .step').nth(n - 1).click(); await p.waitForTimeout(2600)
  await p.screenshot({ path: `screenshots/3d/${name}-end-${theme}-${w}.png` }); await close(`end ${name} ${theme} ${w}`, p)
}
// 3. hover + click a report node
{
  const p = await open('dark', 1920, 1080, '/mission/T2-017')
  const n = await p.locator('.stepper .step').count(); await p.locator('.stepper .step').nth(n - 1).click(); await p.waitForTimeout(2600)
  const pt = await p.evaluate(() => { const e = window.__wa3d, c = document.querySelector('.mc3-canvas').getBoundingClientRect(); const s = e.screenOf('15_9_F_12_2016_10_21'); return s && { x: c.left + s.x, y: c.top + s.y } })
  if (!pt) fail.push(['hover', ['node not on screen']])
  else {
    await p.mouse.move(pt.x, pt.y); await p.waitForTimeout(400)
    if (!(await p.locator('.mc3-tip').count())) fail.push(['hover', ['no tooltip']])
    await p.screenshot({ path: 'screenshots/3d/interaction-hover-dark-1920.png' })
    await p.mouse.click(pt.x, pt.y); await p.waitForTimeout(500)
    if (!(await p.getByText("In this question's context").count())) fail.push(['click', ['records panel not shown']])
    await p.screenshot({ path: 'screenshots/3d/interaction-click-dark-1920.png' })
    // free orbit then reset
    await p.mouse.move(900, 600); await p.mouse.down(); await p.mouse.move(700, 520, { steps: 8 }); await p.mouse.up(); await p.waitForTimeout(400)
    await p.screenshot({ path: 'screenshots/3d/interaction-orbit-dark-1920.png' })
    await p.getByRole('button', { name: 'Reset view' }).click(); await p.waitForTimeout(1800)
  }
  await close('hover, click, orbit, reset', p)
}
// 4. presenter story (c) in 3D
{
  const p = await open('dark', 1920, 1080, '/present?step=3')
  await p.getByRole('button', { name: '3D', exact: true }).click(); await p.waitForSelector('.mc3-canvas', { timeout: 30000 }); await p.waitForTimeout(7000)
  await p.screenshot({ path: 'screenshots/3d/presenter-c-3d-dark-1920.png' }); await close('presenter story c in 3D', p)
}
// 4b. focus mode + collapsed rail at a small laptop viewport (1280x600 ≈ 1920x1080 at 150% scaling)
for (const [name, id] of Q) {
  const ctx = await b.newContext({ viewport: { width: 1280, height: 600 }, colorScheme: 'dark' })
  await ctx.addInitScript(() => { localStorage.setItem('theme', 'dark'); localStorage.setItem('wa-3d-focus', '1'); localStorage.setItem('rail', 'collapsed') })
  const p = await ctx.newPage(); p.errs = []; p.on('pageerror', e => p.errs.push(String(e))); p.on('console', m => m.type() === 'error' && p.errs.push(m.text()))
  await p.goto(`${BASE}/#/mission/${id}`); await p.waitForSelector('.mc', { timeout: 90000 })
  await p.getByRole('button', { name: '3D', exact: true }).click(); await p.waitForSelector('.mc3-hud', { timeout: 30000 })
  await p.keyboard.press('s'); await p.keyboard.press('s'); await p.waitForTimeout(4500)
  await p.screenshot({ path: `screenshots/3d/${name}-focus-mid-dark-1280x600.png` })
  await p.waitForSelector('.mc3-hud .mc3-hud-ans', { timeout: 60000 }); await p.waitForTimeout(1500)
  await p.screenshot({ path: `screenshots/3d/${name}-focus-end-dark-1280x600.png` })
  await p.keyboard.press('f'); await p.waitForSelector('.mc-side'); await p.keyboard.press('f'); await p.waitForSelector('.mc3-hud')
  await close(`focus + collapsed rail ${name} 1280x600`, p)
}
// 5. frame rate during a 1x replay (render loop counts only frames drawn while something animates)
const fps = {}
for (const [w, h] of [[1920, 1080], [1366, 768]]) {
  const p = await open('dark', w, h, '/mission/T2-017')
  await p.waitForTimeout(24000)
  const s = await p.evaluate(() => window.__wa3dFps || []); s.sort((a, c) => a - c)
  fps[`${w}x${h}`] = { windows: s.length, median: +(s[Math.floor(s.length / 2)] ?? 0).toFixed(1), p10: +(s[Math.floor(s.length * 0.1)] ?? 0).toFixed(1), max: +(s[s.length - 1] ?? 0).toFixed(1) }
  await close(`fps ${w}x${h}`, p)
}
const renderer = await (async () => { const p = await (await b.newContext()).newPage(); const r = await p.evaluate(() => { const g = document.createElement('canvas').getContext('webgl2'); const e = g && g.getExtension('WEBGL_debug_renderer_info'); return e ? g.getParameter(e.UNMASKED_RENDERER_WEBGL) : 'unknown' }); await p.context().close(); return r })()
await b.close()
console.log(out.join('\n')); console.log('\nWebGL renderer:', renderer); console.log('FPS during 1x replay:', JSON.stringify(fps))
if (fail.length) { console.log('\nFAILURES'); fail.forEach(f => console.log(f[0], f[1])); process.exit(1) }
console.log('\nALL 3D CHECKS PASSED, no console errors')
