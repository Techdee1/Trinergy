import { chromium } from 'playwright'
const BASE = process.env.BASE || 'http://localhost:5173'
const b = await chromium.launch(); const ctx = await b.newContext({ viewport: { width: 1920, height: 1080 } })
await ctx.addInitScript(() => localStorage.setItem('theme', 'dark'))
const p = await ctx.newPage(); const errs = []
p.on('pageerror', e => errs.push(String(e))); p.on('console', m => m.type() === 'error' && !/429|Too Many/.test(m.text()) && errs.push(m.text()))
await p.goto(`${BASE}/#/ask`); await p.waitForSelector('#q')
// 1. clarification (free, no model)
await p.fill('#q', 'What happened?'); await p.keyboard.press('Control+Enter')
await p.waitForSelector('.clarify', { timeout: 20000 }); await p.waitForTimeout(6000)
await p.screenshot({ path: 'screenshots/ask-clarification-dark-1920.png', fullPage: true })
console.log('clarification: ok, examples =', await p.locator('.example').count())
// 2. click an example -> runs it
await p.locator('.example').first().click(); await p.waitForSelector('.answer-card', { timeout: 30000 }); console.log('example click -> answer shown')
// 3. rate limit: hammer free clarification asks until 429
let hit = false
for (let i = 0; i < 9 && !hit; i++) {
  await p.fill('#q', 'What happened? ' + i); await p.keyboard.press('Control+Enter'); await p.waitForTimeout(700)
  hit = await p.locator('[data-state=rate]').count() > 0
}
console.log('rate limited state reached:', hit)
if (hit) await p.screenshot({ path: 'screenshots/ask-ratelimited-dark-1920.png', fullPage: false })
console.log('errors:', errs.length ? errs : 'none'); await b.close()
