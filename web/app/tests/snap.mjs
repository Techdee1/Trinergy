// usage: node tests/snap.mjs <route> <out-name> [theme=dark] [WxH=1920x1080] [full=1] [BASE=http://localhost:5173]
import { chromium } from 'playwright'
const [route, name, theme = 'dark', size = '1920x1080', full = '1'] = process.argv.slice(2)
const BASE = process.env.BASE || 'http://localhost:5173'
const [w, h] = size.split('x').map(Number)
const b = await chromium.launch()
const ctx = await b.newContext({ viewport: { width: w, height: h }, colorScheme: theme })
await ctx.addInitScript(t => localStorage.setItem('theme', t), theme)
const p = await ctx.newPage()
const errs = []
p.on('console', m => { if (m.type() === 'error') errs.push(m.text()) })
p.on('pageerror', e => errs.push(String(e)))
await p.goto(`${BASE}/#${route}`)
await p.waitForTimeout(Number(process.env.WAIT || 1500))
await p.screenshot({ path: `screenshots/${name}-${theme}-${w}.png`, fullPage: full === '1' })
console.log('errors:', errs.length ? errs : 'none')
await b.close()
