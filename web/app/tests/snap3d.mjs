// usage: node tests/snap3d.mjs <questionId> <name> [theme] [WxH] [waitMs]  (clicks the 3D toggle, autoplay runs)
import { chromium } from 'playwright'
const [id, name, theme = 'dark', size = '1920x1080', wait = '6000'] = process.argv.slice(2)
const BASE = process.env.BASE || 'http://localhost:3000'
const [w, h] = size.split('x').map(Number)
const b = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] })
const ctx = await b.newContext({ viewport: { width: w, height: h }, colorScheme: theme })
await ctx.addInitScript(t => localStorage.setItem('theme', t), theme)
const p = await ctx.newPage(); const errs = []
p.on('console', m => { if (m.type() === 'error') errs.push(m.text()) }); p.on('pageerror', e => errs.push(String(e)))
await p.goto(`${BASE}/#/mission/${id}`); await p.waitForSelector('.mc')
await p.getByRole('button', { name: '3D' }).click(); await p.waitForSelector('.mc3-canvas', { timeout: 20000 })
await p.waitForTimeout(Number(wait))
await p.screenshot({ path: `screenshots/3d/${name}-${theme}-${w}.png` })
console.log('fps', await p.evaluate(() => (window.__wa3dFps || []).map(x => Math.round(x)).join(',')))
console.log('errors:', errs.length ? errs : 'none'); await b.close()
