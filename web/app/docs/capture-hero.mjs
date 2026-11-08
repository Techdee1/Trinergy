// Hero images and the replay clip for slides. No application code is changed: injected CSS hides chrome, and hero A moves the
// real Answer view components into one frame. Everything shown is real data from the local API.
//
//   node docs/capture-hero.mjs candidates   6 candidate frames for hero B (2D and 3D) into docs/shots/hero/_candidates/
//   node docs/capture-hero.mjs final        hero A and B, dark and light, 4K and 1080p
//   node docs/capture-hero.mjs clip         the T2-016 replay clip (MP4 and poster)
//   node docs/capture-hero.mjs all          final + clip
//
// Needs the API on :8000 and the built app on :5173 (see docs/capture.mjs). The clip needs ffmpeg: set FFMPEG=/path/to/ffmpeg
// (for example the binary inside the imageio-ffmpeg Python package). Without it the WebM from Playwright is kept.
import { chromium } from 'playwright'
import { mkdirSync, writeFileSync, renameSync, existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { execFileSync } from 'node:child_process'

const HERE = dirname(fileURLToPath(import.meta.url))
const OUT = join(HERE, 'shots', 'hero'); const CAND = join(OUT, '_candidates')
const API = process.env.API || 'http://localhost:8000'
const BASE = (process.env.BASE || 'http://localhost:5173/').replace(/\/?$/, '/')
const FFMPEG = process.env.FFMPEG
mkdirSync(OUT, { recursive: true }); mkdirSync(CAND, { recursive: true })

// The frame chosen for hero B after looking at the candidates (see the design review in the report).
// mode: '2d' or '3d'. T: milliseconds into the stage's animations at which everything is frozen.
// stage: 'draft' (cited dots travelling) or 'verify' (checks ticking, cited records collected). Chosen: verify.
export const CHOICE_B = { mode: '2d', stage: process.env.HERO_B_STAGE || 'verify', T: Number(process.env.HERO_B_T || 950) }
// Hero B is rendered in a 1536x864 CSS viewport at 1.25x (1080p) or 2.5x (4K): the interface reads at 125% without CSS zoom.
const VP_B = { width: 1536, height: 864 }, K_B = 1920 / 1536

const HIDE_CHROME = '*{cursor:none!important}::-webkit-scrollbar{display:none}html{scrollbar-width:none}'
const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] })

async function page(theme, dsf, extra = {}, vp = { width: 1920, height: 1080 }) {
  const ctx = await browser.newContext({ viewport: vp, deviceScaleFactor: dsf, colorScheme: theme, ...extra })
  await ctx.addInitScript(([t, css]) => {
    localStorage.setItem('theme', t); localStorage.setItem('wa-3d-focus', '0'); localStorage.removeItem('rail')
    const s = document.createElement('style'); s.textContent = css; document.addEventListener('DOMContentLoaded', () => document.head.appendChild(s))
  }, [theme, HIDE_CHROME])
  const p = await ctx.newPage(); p.errs = []
  p.on('pageerror', e => p.errs.push(String(e))); p.on('console', m => m.type() === 'error' && !/Failed to load resource/.test(m.text()) && p.errs.push(m.text()))
  return p
}
const url = route => `${BASE}?api=${encodeURIComponent(API)}#${route}`
const toStage = async (p, idx) => { for (let i = 0; i < 14; i++) await p.keyboard.press('ArrowLeft'); for (let i = 0; i <= idx; i++) await p.keyboard.press('ArrowRight') }

// ───────────────────────── Hero A: trust in one frame
function buildHeroA() {
  const $ = s => document.querySelector(s)
  const step = h => document.evaluate(`//li[contains(@class,'tl-step')][.//h3[normalize-space(text())='${h}']]`, document, null, 9, null).singleNodeValue
  const head = $('.page-head'), ans = $('.answer-card'), conf = $('aside.c-4 .card:nth-child(1)'), lens = $('.lens')
  const ver = step('Verifier'), checks = ver.querySelector('.checks'), pass = ver.querySelector('.verify .badge')
  const recId = $('.lens-item .lens-id')?.textContent ?? ''
  const hero = document.createElement('div'); hero.id = 'hero'
  const hd = document.createElement('div'); hd.className = 'hd'
  const eb = head.querySelector('.row-2'), h1 = head.querySelector('h1'); hd.append(eb, h1)
  const col = document.createElement('div'); col.className = 'col'
  conf.classList.add('conf-card')
  const vcard = document.createElement('div'); vcard.className = 'card vcard'
  const vt = document.createElement('div'); vt.className = 'row between'; vt.style.marginBottom = '10px'
  const ve = document.createElement('div'); ve.className = 'eyebrow'; ve.textContent = `Verifier: ${checks.querySelectorAll('li.check.pass').length} checks`
  vt.append(ve, pass); vcard.append(vt, checks)
  col.append(ans, conf, vcard)
  const bar = lens.querySelector('.viewer-bar'); const cite = document.createElement('div'); cite.className = 'cite'
  cite.innerHTML = `<span class="eyebrow">Cited record</span><b class="mono"></b>`; cite.querySelector('b').textContent = recId; bar.append(cite)
  hero.append(hd, col, lens)
  document.getElementById('root').replaceChildren(hero)
}
const HERO_A_CSS = `
html,body{overflow:hidden!important;height:100%}
#hero{position:fixed;inset:0;background:var(--bg);color:var(--text);display:grid;grid-template-columns:790px minmax(0,1fr);grid-template-rows:auto minmax(0,1fr);column-gap:32px;row-gap:20px;padding:34px 48px 38px}
#hero .hd{grid-column:1/-1;display:grid;gap:6px}
#hero .hd .row-2{gap:8px}
#hero .hd h1{font-size:38px;line-height:1.12;letter-spacing:-.025em;font-weight:620;max-width:none}
#hero .col{display:grid;grid-template-columns:minmax(0,1fr);grid-template-rows:auto auto minmax(0,1fr);gap:16px;min-height:0}
#hero .col>*{grid-column:1/-1!important}
#hero .answer-card{padding:22px 26px}
#hero .answer-card .stack-2{display:none}
#hero .answer-card .row-2{margin-bottom:10px!important}
#hero .answer-card .answer-text{font-size:84px;line-height:1;letter-spacing:-.04em;font-weight:650;margin-top:8px}
#hero .conf-card{display:grid;grid-template-columns:auto 1fr;gap:2px 30px;align-items:center;padding:16px 26px}
#hero .conf-card>.eyebrow,#hero .conf-card>h3{grid-column:1/-1}
#hero .conf-card>.row{margin:0!important}
#hero .conf-card .t-64{font-size:60px}
#hero .conf-card>h3{margin-top:4px!important;font-size:15px}
#hero .conf-card p.t-14{display:none}
#hero .vcard{padding:18px 26px;display:flex;flex-direction:column}
#hero .vcard .checks{flex:1;align-content:space-evenly}
#hero .vcard .checks{grid-template-columns:1fr 1fr;gap:0 26px}
#hero .vcard .check{padding:6px 0;animation:none}
#hero .vcard .check .t-14{font-size:14px;line-height:1.3}
#hero .vcard .check-detail{display:none}
#hero .lens{grid-template-columns:1fr;min-height:0;height:100%;border-radius:var(--r-3)}
#hero .lens-list,#hero .viewer-foot,#hero .viewer-bar .row-2{display:none}
#hero .lens-main,#hero .viewer{height:100%;min-height:0}
#hero .viewer-bar{padding:14px 22px}
#hero .viewer-bar .t-14{font-size:20px;font-weight:600}
#hero .viewer-bar .t-12{font-size:14px}
#hero .viewer-scroll{flex:1;height:auto;min-height:0;padding:0}
#hero .cite{display:grid;gap:2px;justify-items:end}
#hero .cite b{font-size:20px;font-weight:600;padding:4px 10px;border:1px solid var(--line-strong);border-radius:var(--r-1);background:var(--surface-2)}
#hero .hl{border-width:4px;box-shadow:0 0 0 7px color-mix(in srgb,var(--brand) 25%,transparent),0 0 36px color-mix(in srgb,var(--brand) 55%,transparent)}
`
async function heroA(theme, dsf, file) {
  const p = await page(theme, dsf)
  await p.goto(url('/question/T2-016')); await p.waitForSelector('.page-wrap .hl', { timeout: 60000 }); await p.waitForTimeout(1200)
  await p.getByRole('button', { name: 'Zoom in' }).click(); await p.waitForTimeout(600)
  await p.evaluate(buildHeroA); await p.addStyleTag({ content: HERO_A_CSS }); await p.waitForTimeout(700)
  await p.evaluate(() => {
    const v = document.querySelector('.viewer-scroll'), h = document.querySelector('.page-wrap .hl'), vr = v.getBoundingClientRect(), hr = h.getBoundingClientRect()
    v.scrollTop += hr.top - vr.top - v.clientHeight * 0.42; v.scrollLeft += hr.left - vr.left - v.clientWidth * 0.3
  })
  await p.waitForTimeout(400); await p.screenshot({ path: file })
  const errs = p.errs; await p.context().close(); return errs
}

// ───────────────────────── Hero B: the search
const HERO_B_CSS = `${HIDE_CHROME}
.rail,.footer,.mission-top,.controls,.kbd-hint,.skip{display:none!important}
.app{grid-template-columns:minmax(0,1fr)!important}
.page.wide{padding:20px 28px 16px;max-width:none}
.mc3{height:clamp(420px,calc(100vh - 110px),900px)}
.node{height:64px!important}
.checks.one .check{padding:1px 0!important}
.now-card,.answer-mini{padding:16px 20px!important}
.answer-mini .chips{gap:5px!important}
.answer-mini .chip{height:24px!important}
.answer-mini .stack-2{margin-bottom:8px!important}
.checks.one .check .t-12{font-size:12.5px;line-height:1.3}
.now-card p.t-14.muted{display:none}
.now-card .stack{gap:8px!important}
.answer-mini .card-title{margin-bottom:8px}
.stepper{display:none!important}
.legend .faint{display:none}
.now-card{min-height:0!important}
.lanes{gap:8px!important;padding-top:10px!important;padding-bottom:10px!important}
.mc-q{padding-top:12px!important;padding-bottom:10px!important}
.legend{padding-top:8px!important;padding-bottom:8px!important}
.stepper{margin-bottom:2px}
`
async function stageB(p, mode, stage = 'draft') {
  await p.goto(url('/mission/T2-017')); await p.waitForSelector('.mc', { timeout: 60000 })
  if (mode === '3d') { await p.getByRole('button', { name: '3D', exact: true }).click(); await p.waitForSelector('.mc3-canvas', { timeout: 40000 }) }
  await p.addStyleTag({ content: HERO_B_CSS }); await p.waitForTimeout(1200)
  // 3D: enter the verify stage (idx 4) from the draft stage (idx 3). 2D: enter the draft stage (idx 3) from the context stage (idx 2).
  const enter = stage === 'verify' ? 3 : mode === '3d' ? 3 : 2
  await toStage(p, enter); await p.waitForTimeout(mode === '3d' ? 3200 : stage === 'verify' ? 2600 : 1800)
  await p.keyboard.press('ArrowRight')
}
// Only the flying cited-record dots and the arriving cited-record chips are frozen at the same instant (Web Animations API);
// everything else keeps its natural, settled state. At ~700 to 1000 ms both are genuinely in motion in the real replay.
const FREEZE = { draft: ['fly', 'cite-in'], verify: ['check'] }
const freeze = (p, T, stage = 'draft') => p.evaluate(([t, cls]) => { document.getAnimations().forEach(a => { try { const c = a.effect?.target?.classList; if (c && cls.some(k => c.contains(k))) { a.pause(); a.currentTime = t } } catch { /* ignore */ } }) }, [T, FREEZE[stage]])

async function candidates() {
  for (const mode of ['2d']) {
    // six moments, each from a fresh run so every frame starts the stage from zero
    const stage = process.env.HERO_B_STAGE || 'verify'
    const times = stage === 'verify' ? [400, 550, 700, 850, 1000, 1150] : [500, 650, 800, 950, 1100, 1250]
    for (let i = 0; i < times.length; i++) {
      const q = await page('dark', K_B, {}, VP_B); await stageB(q, mode, stage); await q.waitForTimeout(60); await freeze(q, times[i], stage); await q.waitForTimeout(250)
      await q.screenshot({ path: join(CAND, `B_${stage}_${i + 1}_T${times[i]}.png`) }); await q.context().close()
    }
  }
  console.log('candidates written to', CAND)
}

async function heroB(theme, dsf, file) {
  const p = await page(theme, dsf * K_B, {}, VP_B); await stageB(p, CHOICE_B.mode, CHOICE_B.stage); await p.waitForTimeout(60); await freeze(p, CHOICE_B.T, CHOICE_B.stage); await p.waitForTimeout(350)
  await p.screenshot({ path: file }); const errs = p.errs; await p.context().close(); return errs
}

async function final() {
  const problems = []
  for (const theme of ['dark', 'light']) for (const [dsf, tag] of [[2, '4k'], [1, '1080p']]) {
    const sfx = tag === '4k' ? '4k' : '1080p'
    for (const [name, fn] of [['hero_a_trust', heroA], ['hero_b_search', heroB]]) {
      const file = join(OUT, `${name}_${theme}_${sfx}.png`); const errs = await fn(theme, dsf, file)
      console.log(name, theme, sfx, errs.length ? 'ERRORS ' + errs[0] : 'ok'); if (errs.length) problems.push([name, theme, errs[0]])
    }
  }
  if (problems.length) { console.log('PROBLEMS', problems); process.exitCode = 1 }
}

// ───────────────────────── Clip: T2-016 replay at 1x, no cursor
async function clip() {
  const dir = join(OUT, '_video'); mkdirSync(dir, { recursive: true })
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, colorScheme: 'dark', recordVideo: { dir, size: { width: 1920, height: 1080 } } })
  await ctx.addInitScript(css => { localStorage.setItem('theme', 'dark'); localStorage.removeItem('rail'); const s = document.createElement('style'); s.textContent = css; document.addEventListener('DOMContentLoaded', () => document.head.appendChild(s)) }, HIDE_CHROME)
  const t0 = Date.now(); const p = await ctx.newPage()
  await p.goto(url('/mission/T2-016')); await p.waitForSelector('.mc .stepper .step', { timeout: 60000 })
  const tAppear = (Date.now() - t0) / 1000
  await p.waitForSelector('.resolve', { timeout: 60000 }); const tResolved = (Date.now() - t0) / 1000
  await p.waitForTimeout(900); await p.screenshot({ path: join(OUT, 'hero_replay_t2016_poster.png') })
  const total = 22.5; const remain = total - (Date.now() - t0) / 1000 + tAppear - 0.2
  if (remain > 0) await p.waitForTimeout(remain * 1000)
  const video = p.video(); await ctx.close(); const webm = await video.path()
  const info = { webm, tAppear, tResolved, replaySeconds: +(tResolved - tAppear).toFixed(1) }
  if (FFMPEG) {
    const mp4 = join(OUT, 'hero_replay_t2016.mp4')
    execFileSync(FFMPEG, ['-y', '-loglevel', 'error', '-ss', String(Math.max(0, tAppear - 0.2)), '-i', webm, '-t', String(total), '-an', '-c:v', 'libx264', '-preset', 'slow', '-crf', '20', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', mp4])
    info.mp4 = mp4
  } else { renameSync(webm, join(OUT, 'hero_replay_t2016.webm')); info.webm = join(OUT, 'hero_replay_t2016.webm') }
  console.log('clip', JSON.stringify(info)); return info
}

const cmd = process.argv[2] ?? 'final'
if (cmd === 'candidates') await candidates()
else if (cmd === 'final') await final()
else if (cmd === 'clip') await clip()
else if (cmd === 'all') { await final(); await clip() }
else console.log('usage: node docs/capture-hero.mjs candidates|final|clip|all')
await browser.close()
