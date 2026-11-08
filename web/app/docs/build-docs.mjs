// Builds UI_Guide.pdf and Screenshot_Guide.pdf (HTML printed with Playwright).
//   node docs/build-docs.mjs
// Reads docs/facts.json (live API figures), docs/shots/manifest.json (what each screenshot shows, which callouts were drawn)
// and docs/shots.config.mjs (captions, steps, slides). Run docs/capture.mjs first. No em dashes in any text.
import { chromium } from 'playwright'
import { mkdirSync, writeFileSync, readFileSync, existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import * as L from 'lucide-react'
import { SHOTS, SLIDES } from './shots.config.mjs'

const HERE = dirname(fileURLToPath(import.meta.url))
const BUILD = join(HERE, '_build'); mkdirSync(BUILD, { recursive: true })
const F = JSON.parse(readFileSync(join(HERE, 'facts.json'), 'utf8'))
const M = JSON.parse(readFileSync(join(HERE, 'shots', 'manifest.json'), 'utf8')).shots
const TODO_URL = 'TODO-URL'
const date = new Date(F.captured_at).toISOString().slice(0, 10)

const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
const n0 = x => Math.round(x).toLocaleString('en-US'), usd2 = x => '$' + x.toFixed(2), usd4 = x => '$' + x.toFixed(4), pc = x => Math.round(x * 100) + '%'
const icon = (name, size = 14) => renderToStaticMarkup(createElement(L[name], { size, strokeWidth: 1.7 }))
const shot = id => SHOTS.find(s => s.id === id)
const dark = id => M[id]?.variants?.dark
const img = (id, kind = 'annotated', theme = 'dark') => { const v = M[id]?.variants?.[theme]; return v ? `../shots/${v[kind]}` : '' }

const FONT = pathToFileURL(join(HERE, '..', 'node_modules', '@fontsource-variable'))
const CSS = `
@font-face{font-family:'Inter V';src:url('${FONT}/inter/files/inter-latin-wght-normal.woff2') format('woff2');font-weight:100 900}
@font-face{font-family:'JB V';src:url('${FONT}/jetbrains-mono/files/jetbrains-mono-latin-wght-normal.woff2') format('woff2');font-weight:100 800}
@page{size:A4 landscape;margin:0}
:root{--bg:#f6f3f0;--card:#fff;--soft:#efebe7;--text:#1a1613;--t2:#5a524c;--t3:#6f665f;--line:rgba(40,24,10,.14);--brand:#c80000;--ok:#0b7556;--abstain:#8f5200;--route:#1c5bc0;--flag:#6a32b0;--ctx:#5a524c;
 --ok-bg:rgba(11,117,86,.10);--abs-bg:rgba(176,108,0,.12);--route-bg:rgba(28,91,192,.10);--flag-bg:rgba(106,50,176,.10);--ctx-bg:rgba(90,82,76,.09)}
*{box-sizing:border-box}html{-webkit-print-color-adjust:exact;print-color-adjust:exact}
body{margin:0;background:var(--bg);color:var(--text);font:400 9.4pt/1.45 'Inter V',system-ui,sans-serif;font-feature-settings:'cv11','tnum'}
.mono{font-family:'JB V',ui-monospace,monospace;font-size:.92em}
.page{width:297mm;height:210mm;padding:11mm 14mm 14mm;page-break-after:always;position:relative;overflow:hidden;display:flex;flex-direction:column;gap:5mm}
.page:last-child{page-break-after:auto}
.pf{position:absolute;left:14mm;right:14mm;bottom:5.5mm;display:flex;justify-content:space-between;font-size:7pt;color:var(--t3);border-top:1px solid var(--line);padding-top:1.6mm}
h1{font-size:30pt;line-height:1.05;letter-spacing:-.03em;margin:0;font-weight:650}
h2{font-size:17pt;line-height:1.15;letter-spacing:-.02em;margin:0;font-weight:640}
h3{font-size:9pt;margin:0 0 1.2mm;font-weight:640;letter-spacing:.07em;text-transform:uppercase;color:var(--t3)}
p{margin:0 0 2mm}.eyebrow{font-size:7.6pt;font-weight:640;letter-spacing:.09em;text-transform:uppercase;color:var(--t3)}
ul,ol{margin:0;padding-left:4.2mm}li{margin:0 0 1.2mm}
.lead{font-size:11.5pt;color:var(--t2);line-height:1.45;max-width:215mm}
.card{background:var(--card);border:1px solid var(--line);border-radius:3mm;padding:4mm 5mm}
.hd{display:flex;justify-content:space-between;align-items:flex-end;gap:6mm}
.tgrid{display:grid;grid-template-columns:176mm 1fr;gap:7mm;flex:1;min-height:0}
.left{display:flex;flex-direction:column;gap:3.4mm;min-height:0}
figure{margin:0}figure img{display:block;width:100%;border-radius:2.4mm;border:1px solid var(--line);box-shadow:0 1.2mm 4mm rgba(40,24,10,.16)}
.legend{list-style:none;padding:0;margin:0;columns:2;column-gap:6mm;font-size:8.4pt;line-height:1.35}
.legend li{display:grid;grid-template-columns:5.2mm 1fr;gap:2mm;break-inside:avoid;margin:0 0 1.6mm}
.nb{width:4.8mm;height:4.8mm;border-radius:50%;background:var(--brand);color:#fff;font:700 7.4pt/4.8mm 'Inter V';text-align:center}
.right{display:flex;flex-direction:column;gap:3mm;min-height:0}
.thumbs{display:grid;grid-template-columns:repeat(2,1fr);gap:2.4mm;margin-top:auto}
.thumbs figure img{box-shadow:none;border-radius:1.4mm}.thumbs figcaption{font-size:7.2pt;color:var(--t3);line-height:1.25;margin-top:.8mm}
.tip{background:var(--soft);border-radius:2.4mm;padding:2.4mm 3.2mm;font-size:8.4pt;color:var(--t2)}
.tip b{color:var(--text)}
table{border-collapse:collapse;width:100%;font-size:8.3pt}th{text-align:left;font-size:7.2pt;letter-spacing:.07em;text-transform:uppercase;color:var(--t3);padding:1.4mm 2.4mm;border-bottom:1.5px solid var(--line)}
td{padding:1.7mm 2.4mm;border-bottom:1px solid var(--line);vertical-align:top}
.kbd{display:inline-block;min-width:5.2mm;padding:0 1.5mm;border:1px solid var(--line);border-bottom-width:1.6px;border-radius:1.2mm;font:600 7.6pt/4.6mm 'JB V';text-align:center;background:#fff;color:var(--t2);margin-right:1mm}
.pill{display:inline-flex;align-items:center;gap:1.2mm;height:5mm;padding:0 2.2mm;border-radius:99px;font-size:7.6pt;font-weight:620;white-space:nowrap}
.pill svg{flex:none}.ok{color:var(--ok);background:var(--ok-bg)}.ab{color:var(--abstain);background:var(--abs-bg)}.rt{color:var(--route);background:var(--route-bg)}.fl{color:var(--flag);background:var(--flag-bg)}.cx{color:var(--ctx);background:var(--ctx-bg)}.br{color:var(--brand);background:rgba(200,0,0,.08)}
.cols2{display:grid;grid-template-columns:1fr 1fr;gap:6mm}.cols3{display:grid;grid-template-columns:repeat(3,1fr);gap:5mm}
.figs{display:grid;grid-template-columns:repeat(6,1fr);gap:0;border-top:1.5px solid var(--text);border-bottom:1px solid var(--line)}
.fig{padding:3mm 3mm 3mm 0;border-right:1px solid var(--line);margin-right:3mm}.fig:last-child{border-right:0;margin-right:0}
.fig b{display:block;font-size:22pt;letter-spacing:-.03em;line-height:1.05;font-weight:640}.fig span{font-size:7.6pt;color:var(--t3)}
.sw{display:flex;align-items:center;gap:2.4mm;font-size:8pt;margin-bottom:1.4mm}.sw i{width:7mm;height:7mm;border-radius:1.6mm;border:1px solid var(--line);flex:none}
.small{font-size:8pt;color:var(--t2)}.faint{color:var(--t3)}.cmd{background:#1c1917;color:#f5f0eb;border-radius:2.4mm;padding:3mm 4mm;font:500 8.4pt/1.55 'JB V';white-space:pre-wrap}
.cmd .c{color:#9a918a}
.verify{color:#6a32b0;font-weight:700}
.dense td{padding:.9mm 2mm;font-size:7.8pt;line-height:1.35}.dense tr:last-child td{border-bottom:0}
`
const wrap = (title, body) => `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>${esc(title)}</title><style>${CSS}</style></head><body>${body}</body></html>`
let pageNo = 0
const FOOT = (doc) => { pageNo++; return `<div class="pf"><span>Team Trinergy: Intelligent Well Archive. Built for Heirs Energies, NAPE AICE 2026. Data: Equinor Volve dataset.</span><span>${doc} · page ${pageNo}</span></div>` }
const pill = (cls, ico, text) => `<span class="pill ${cls}">${icon(ico, 12)}${esc(text)}</span>`
const kbd = (...k) => k.map(x => `<span class="kbd">${esc(x)}</span>`).join('')

// ───────────────────────── UI Guide
function tourPage({ eyebrow, title, id, purpose, look, tip, thumbs = [], extra = '' }) {
  const v = dark(id); const marks = v?.marks ?? []
  const legend = marks.map(m => `<li><span class="nb">${m.n}</span><span>${esc(m.label)}</span></li>`).join('')
  const th = thumbs.map(([tid, cap]) => `<figure><img src="${img(tid, 'clean')}" alt=""><figcaption>${esc(cap)}</figcaption></figure>`).join('')
  return `<section class="page"><div class="hd"><div><div class="eyebrow">${esc(eyebrow)}</div><h2>${esc(title)}</h2></div></div>
  <div class="tgrid"><div class="left"><figure><img src="${img(id)}" alt="${esc(shot(id).title)}"></figure><ol class="legend">${legend}</ol></div>
  <div class="right"><div><h3>Purpose</h3><p>${purpose}</p></div><div><h3>What to look at</h3><ul>${look.map(x => `<li>${x}</li>`).join('')}</ul></div>${extra}${tip ? `<div class="tip"><b>Tip.</b> ${tip}</div>` : ''}${th ? `<div class="thumbs">${th}</div>` : ''}</div></div>${FOOT('UI Guide')}</section>`
}

function uiGuide() {
  const q = F.questions, a = F.archive, c = F.cost, g = F.generalisation, ab = q.by_status.abstain ?? 0, an = q.by_status.answered ?? 0
  const P = []
  // 1 What it is
  P.push(`<section class="page"><div class="eyebrow">UI Guide · NAPE AICE 2026 · Track 2 · Team Trinergy</div>
  <h1>Intelligent Well Archive</h1><p class="lead">A dashboard over 32 daily drilling reports from the Equinor Volve dataset. Ask a question about a well and get the answer, the report page it came from, and proof that it was checked. When the archive does not hold the answer, it says so and shows what it searched.</p>
  <div class="figs"><div class="fig"><b>${q.total}</b><span>questions: ${q.sets.challenge} challenge, ${q.sets.unseen} unseen</span></div><div class="fig"><b>${a.reports}</b><span>daily reports, ${a.wellbores} wellbores, ${a.pdf_pages} PDF pages</span></div><div class="fig"><b>${n0(a.indexed_records)}</b><span>records indexed, each with page and section</span></div><div class="fig"><b>${an} / ${ab}</b><span>answered / abstained</span></div><div class="fig"><b>${q.verified} of ${q.total}</b><span>carry no verifier-failed flag</span></div><div class="fig"><b>${usd2(c.ledger_usd)}</b><span>total model cost, ${usd4(c.per_challenge_question_usd)} per challenge question</span></div></div>
  <div class="cols3"><div class="card"><h3>What it is</h3><p>A web app with a left rail of eight views and a presenter mode, a replay of how each question was answered, and an Ask box for new questions. It reads everything from a local or hosted API. The model never searches the archive: code does.</p></div>
  <div class="card"><h3>Who it is for</h3><ul><li><b>Drilling and subsurface engineers</b> who need a figure from well history and want to see where it came from.</li><li><b>Data managers and reviewers</b> who must trace a number to a source, for example for data-integrity attestation.</li><li><b>Judges and presenters</b> who want to watch the pipeline work, in 2D or 3D.</li></ul></div>
  <div class="card"><h3>What it will not do</h3><ul><li>Invent a citation. Every cited record is in the archive.</li><li>Guess when the archive has no such field. It abstains, and abstaining is a valid answer.</li><li>Hide cost or doubt. Confidence comes from a written rule, and cost is on its own page.</li></ul></div></div>
  <p class="small">Figures on this page were read from the live API on ${date} (server version ${esc(F.version)}). Hosted address: ${TODO_URL}. Data: Equinor Volve dataset. This is not an official Heirs Energies product.</p>${FOOT('UI Guide')}</section>`)

  P.push(tourPage({ eyebrow: 'View 1 of 9 · Overview', title: 'Overview: the promise and the live numbers', id: 'overview_hero',
    purpose: 'The landing view. It says in one sentence what the system does and proves it with counters read live from the API.',
    look: ['The five counters: questions, reports, records, verified answers and total cost. They count up once, then stay still.', 'The red button <b>Watch it work</b> opens the replay of a multi-report question.', 'Below the fold: the four rules (code finds the facts, AI only phrases, a verifier checks, abstention is valid) and three runs worth watching.'],
    tip: 'Start every demo here. The four rules frame everything that follows.', thumbs: [['overview_principles', 'The four rules and the six-step pipeline strip, further down the same page.']] }))

  P.push(tourPage({ eyebrow: 'View 2 of 9 · Mission control (2D)', title: 'Mission control: watch a question being answered', id: 'mission_2d_t2017',
    purpose: 'Replays what the pipeline did for any of the 72 questions, stage by stage, from the stored trace. Wells are lanes, reports are nodes in date order.',
    look: ['The stage pills at the top. Click one to jump to it. The current stage has a red outline.', 'Blue nodes are reports the router opened. Dimmed lanes were ruled out.', 'The side card says in plain words what is happening. The answer card fills in as claims are verified.'],
    tip: 'Pick a question with the picker above the stage pills. The four quick chips are single report, multi-report, archive-wide and abstention.',
    thumbs: [['replay_t2016_1_route', 'T2-016, stage 1: one report opened out of 32.'], ['replay_t2016_2_context', 'Stage 2: its records go into the context.'], ['replay_t2016_3_verify', 'Stage 3: the verifier checks tick in.'], ['replay_t2016_4_resolve', 'Stage 4: answer and confidence resolve.']] }))

  P.push(tourPage({ eyebrow: 'View 2 of 9 · Mission control (3D)', title: 'Mission control in 3D: the search through the real subsurface', id: 'mission_3d_t2017',
    purpose: 'The same replay, drawn in 3D. Wells follow their surveyed paths, reports are nodes along them, and the search moves through the archive as light.',
    look: ['Solid nodes sit at the depth surveyed that day. Ring nodes have no depth in the data and are spread in date order along the well.', 'The scale on the left is true vertical depth in metres.', 'Drag to orbit, scroll to zoom, hover a node for its file and depth, click it to list its records.'],
    tip: '<b>Focus</b> (key F) gives the scene the whole width. The sidebar collapses with the key [ . 2D stays the default and the automatic fallback.', thumbs: [['mission_3d_focus_t2017', 'Focus mode: a compact card replaces the stage list and side panel.']] }))

  P.push(tourPage({ eyebrow: 'View 3 of 9 · Questions', title: 'Questions: the results board for all 72', id: 'questions_board',
    purpose: `Every question with its status, confidence and flags. ${q.sets.challenge} challenge questions and ${q.sets.unseen} unseen ones. ${an} are answered and ${ab} are abstained.`,
    look: ['Filter by set, mode and status. Counts update as you filter.', 'Status always has an icon and a label as well as a colour: answered is green, abstained is amber.', 'Flags such as escalated, arbitrated or context truncated show where the pipeline had to work harder.'],
    tip: 'Click any row to open its Answer view. On the Answer view, the left and right arrow keys move to the previous and next question.' }))

  P.push(tourPage({ eyebrow: 'View 4 of 9 · Answer view', title: 'Answer view: the answer, and how sure the system is', id: 'answer_t2016',
    purpose: 'One question in full. The answer comes first, then the confidence with the rule that set it, then the evidence and the trace.',
    look: ['The status badges: answered, verified, and the router mode.', 'Confidence is set by code from a written rule: for example 0.95 for one cited record from one report, 0.85 for an abstention backed by an ABSENT record. The model never sets it.', 'Source says whether the model calls were replayed from storage, made live, or not needed.'],
    tip: `For T2-016 the answer is ${esc(F.t2016.answer)} with confidence ${F.t2016.confidence.toFixed(2)}. The report dated D covers D-1 to D, and the router opened the report dated exactly 2014-03-26.` }))

  P.push(tourPage({ eyebrow: 'View 4 of 9 · Answer view: evidence lens', title: 'Evidence lens: the exact line in the original report', id: 'evidence_highlight_t2016',
    purpose: 'Shows the real PDF page that holds each cited record, with a red box on the row, value or heading that supports the answer.',
    look: ['The red box. Its label above the page says what was matched: value, row, label or heading.', 'Use the plus and minus buttons above the page to zoom from 60% to 200%.', 'Records the PDF does not print show a calm "XML only" state, not a made-up page (small image below).'],
    tip: 'The XML is authoritative. Where the PDF prints a value that conflicts with it, for example tightWell, the evidence points to the XML node and says so. The XML-only image is composed from a real record, because no catalogue question cites one.',
    thumbs: [['evidence_xml_only', 'XML-only state (composed from real record 19A-19800101-STATUS-TIGHTWELL).']] }))

  P.push(tourPage({ eyebrow: 'View 4 of 9 · Answer view: trace timeline', title: 'Trace timeline: how the answer was built', id: 'trace_t2017_router',
    purpose: 'Every stage below was observed from the pipeline\'s real calls, in the order it happened: router, context, model calls, verifier, then escalation, second pass or arbitration if they happened.',
    look: ['The router says which reports it opened and why, in its own words.', 'Model calls list role, model, provider-reported tokens, time and cost. "Replayed" means the stored answer from when it was first generated; this server paid nothing now.', 'Token counts in the context step are marked as estimates (text length divided by four). The provider\'s exact counts are in the model calls.'],
    tip: 'A violet flag in the verifier is not a failure shown in red. It is a check that found something, and here it led to an escalation to a larger model.',
    thumbs: [['trace_t2017_verifier', 'Model calls and the first verifier run: a flag on one number.'], ['trace_t2017_escalation', 'The escalation, explained, and the totals.']] }))

  P.push(tourPage({ eyebrow: 'View 5 of 9 · Generalisation', title: 'Generalisation: forty questions it had not seen', id: 'generalisation',
    purpose: `Tests whether the approach holds on different wording, wells and traps. Mean score ${g.mean_score.toFixed(2)} against a baseline of ${g.baseline_mean_score.toFixed(2)}.`,
    look: ['The blue note is the honest caveat: <b>tuned on these questions; independent test in progress</b>. These are not clean held-out scores.', 'One card per category: single report, compare reports, archive-wide, and not in the archive.', 'Each row opens its Answer view.'],
    tip: 'Say the caveat out loud before a judge asks. It is the most credible sentence on the page.' }))

  P.push(tourPage({ eyebrow: 'View 6 of 9 · Impact for Heirs', title: 'Impact: what better well memory could be worth', id: 'impact_calculator',
    purpose: 'The problem (well history buried in legacy reports, and data-integrity attestation for the NUPRC National Data Repository), five use cases, deployment options, a roadmap, and a small calculator.',
    look: ['The calculator is arithmetic on three inputs you can change: engineers, hours saved a week, cost an hour.', 'It is labelled <b>Illustrative, not measured</b>. Nobody has measured these inputs at Heirs.', 'Context fact on the page: OML 17 doubled its output without new wells and reactivated about 100 dormant wells (company-reported).'],
    tip: 'Change the inputs live in front of the audience. It shows the number is theirs to set.' }))

  P.push(tourPage({ eyebrow: 'View 7 of 9 · Archive', title: 'Archive: thirty-two reports across eight wellbores', id: 'archive_timeline',
    purpose: `The whole archive on one timeline. ${a.reports} daily reports, ${a.wellbores} wellbores, ${n0(a.records)} archive records plus ${a.derived_notes} derived notes that flag where the XML and PDF disagree.`,
    look: ['Dot size is the number of records in a report. Click a dot to see its file, the period it covers, pages and records.', 'The 1980 report carries a placeholder date in the source data. Years without reports are skipped and marked with //.', 'The bars show records by type.'],
    tip: 'A report dated D covers D-1 to D. The selected-report card shows the period so nobody has to guess.' }))

  P.push(tourPage({ eyebrow: 'View 8 of 9 · Cost', title: 'Cost: cheap by design', id: 'cost_view',
    purpose: `A small model makes ${pc(c.haiku_share_of_calls)} of the calls and accounts for ${pc(c.haiku_share_of_cost)} of the cost. The larger model is called only when a check fails.`,
    look: [`All model calls for the challenge set cost ${usd2(c.ledger_usd)}, which is ${usd4(c.per_challenge_question_usd)} a question.`, 'Each mark in the per-question chart is one question, cheapest to dearest. Shape tells the set.', `Live budget: the server stops spending at ${usd2(c.server_budget_usd)}. Stored answers still replay after that.`],
    tip: 'Costs of replayed calls are what they cost when first generated. The "paid now" figure on each Answer view is what this server paid in this session.' }))

  P.push(tourPage({ eyebrow: 'View 9 of 9 · Ask', title: 'Ask: your own question, with a live trace', id: 'ask_start',
    purpose: 'Type a question and watch each stage appear as it happens, then see the answer with its evidence. Suggested questions cover answered, multi-report, abstaining and too vague.',
    look: ['Press Command or Control plus Enter to send. Questions are limited to 400 characters.', 'The same stage pills and replay appear as in Mission control, driven live by the server.', 'Every failure has its own designed state. See the table on page 16.'],
    tip: 'A question the archive already answered replays instantly at no cost. A brand new one needs the server to have a model key and budget.',
    thumbs: [['ask_answered', 'Answered, from the Ask box.'], ['ask_abstain', 'An honest abstention.'], ['ask_clarification', 'A vague question gets three examples to click.']] }))

  P.push(tourPage({ eyebrow: 'Presenter mode', title: 'Presenter mode: a guided tour for a projector', id: 'presenter_story_a',
    purpose: 'Five steps: intro, the date-window trap (T2-016), the Western Atlas abstention (T2-032), the multi-report sequence (T2-017, with an optional 3D view), then "try your own question".',
    look: ['Type is enlarged and the rail is hidden. Everything works offline against a local API.', 'Each story has a note to read aloud and its own replay.', 'Hide cursor (H) removes the pointer for filming or projecting.'],
    tip: 'Open it from the rail, or go to #/present. Esc exits. Keys are in the table on page 15.', thumbs: [['presenter_intro', 'Step 1: the intro.']] }))

  // 15 How to operate
  P.push(`<section class="page"><div><div class="eyebrow">How to operate it</div><h2>Navigation, controls and keyboard shortcuts</h2></div>
  <div class="cols2" style="flex:1;min-height:0"><div class="stack"><div><h3>Moving around</h3><ul>
  <li><b>Left rail:</b> one link per view. The button beside the logo, or the key ${kbd('[')}, collapses it to icons.</li>
  <li><b>Question picker</b> (Mission control): click it, type to search the 72 questions, use ${kbd('↑', '↓')} and ${kbd('Enter')}. The four chips jump to a single-report, multi-report, archive-wide or abstaining example.</li>
  <li><b>Theme:</b> the sun or moon button at the bottom of the rail. Dark is the default.</li>
  <li><b>2D or 3D:</b> the switch at the top right of Mission control. ${kbd('F')} toggles Focus in 3D.</li>
  <li><b>Footer:</b> shows the API address in use and where it came from.</li></ul></div>
  <div style="margin-top:3.4mm"><h3>Replay controls</h3><ul>
  <li><b>Play or pause</b> the red button. <b>Previous and next stage</b> the arrow buttons. <b>Replay</b> restarts.</li>
  <li><b>Speed</b> cycles 0.5x, 1x, 2x and 4x. Use 1x for the talk.</li>
  <li>Click a <b>stage pill</b> to jump straight to that stage.</li></ul></div>
  <div style="margin-top:3.4mm"><h3>Zooming the evidence page</h3><p>Use plus, minus and fit above the PDF page. Zoom runs from 60% to 200%. The page images are stored at twice size, so text softens above about 160%.</p></div></div>
  <div><h3>Keyboard shortcuts</h3><table><thead><tr><th>Where</th><th>Keys</th><th>Does</th></tr></thead><tbody>
  <tr><td>Everywhere (not in the tour)</td><td>${kbd('[')}</td><td>Collapse or expand the sidebar</td></tr>
  <tr><td>Mission control</td><td>${kbd('Space')}</td><td>Play or pause</td></tr>
  <tr><td></td><td>${kbd('←', '→')}</td><td>Previous or next stage</td></tr>
  <tr><td></td><td>${kbd('R')} ${kbd('S')}</td><td>Replay. Cycle speed</td></tr>
  <tr><td>Mission control, 3D</td><td>${kbd('F')}</td><td>Focus on or off</td></tr>
  <tr><td>Answer view</td><td>${kbd('←', '→')}</td><td>Previous or next question</td></tr>
  <tr><td>Question picker</td><td>${kbd('↑', '↓', 'Enter', 'Esc')}</td><td>Move, choose, close</td></tr>
  <tr><td>Ask</td><td>${kbd('Ctrl or Cmd', 'Enter')}</td><td>Send the question</td></tr>
  <tr><td>Presenter mode</td><td>${kbd('→', '←')} or PageDown, PageUp</td><td>Next or previous tour step</td></tr>
  <tr><td></td><td>${kbd('1')}...${kbd('5')}</td><td>Jump to a step</td></tr>
  <tr><td></td><td>${kbd('Space')} ${kbd('R')} ${kbd('S')} ${kbd(',')} ${kbd('.')}</td><td>Play or pause, replay, speed, step back, step forward</td></tr>
  <tr><td></td><td>${kbd('H')} ${kbd('Esc')}</td><td>Hide cursor. Exit</td></tr></tbody></table></div></div>${FOOT('UI Guide')}</section>`)

  // 16 Ask states
  const strip = id => `<img src="${img(id, 'clean', 'dark')}" style="width:100%;border-radius:1.4mm;border:1px solid var(--line)" alt="">`
  P.push(`<section class="page"><div><div class="eyebrow">How to operate it</div><h2>Every Ask state, what it means, and what to do</h2></div>
  <table><thead><tr><th style="width:27mm">State</th><th style="width:46mm">What you see</th><th>What it means</th><th style="width:70mm">What to do</th></tr></thead><tbody>
  <tr><td>${pill('cx', 'Loader2', 'Server waking')}</td><td>"Waking the archive server" with a progress bar</td><td>The hosted API sleeps when idle. The first request can take up to a minute.</td><td>Wait. After about 75 seconds a Try again button appears.</td></tr>
  <tr><td>${pill('ab', 'CloudOff', 'Live mode off')}</td><td>Amber banner at the top of Ask</td><td>The server has no model key, or its budget is spent. Only answered questions replay.</td><td>Ask a catalogue question. New ones return NOT EVALUATED.</td></tr>
  <tr><td>${pill('ab', 'HelpCircle', 'Needs clarification')}</td><td>"I need a bit more to go on" and three examples</td><td>The question names no well, date or field. No model was called.</td><td>Click an example, or add a well and a date.</td></tr>
  <tr><td>${pill('ab', 'MinusCircle', 'Abstained')}</td><td>Amber answer card, ABSENT record</td><td>The archive has no such field. It names what was searched. A valid answer.</td><td>Open the evidence lens to see what was considered and rejected.</td></tr>
  <tr><td>${pill('ab', 'Hourglass', 'Rate limited')}</td><td>"Slow down a moment" with a countdown</td><td>More than ${F.rate_limit?.per_minute ?? 6} questions a minute or ${F.rate_limit?.per_day ?? 40} a day from one address (HTTP 429).</td><td>Wait for the timer, then Try again.</td></tr>
  <tr><td>${pill('ab', 'PiggyBank', 'Budget reached')}</td><td>"Live questions have used up their budget"</td><td>The live spending cap (${usd2(c.server_budget_usd)}) is spent and this question has no stored answer.</td><td>Use a catalogue question. Stored answers still replay in full.</td></tr>
  <tr><td>${pill('cx', 'Hourglass', 'NOT EVALUATED')}</td><td>Grey badge, confidence 0, no evidence</td><td>No model could be called and the question is not stored. Nothing is guessed.</td><td>Try a catalogue question, or ask the presenter to enable live mode.</td></tr>
  <tr><td>${pill('cx', 'ServerCrash', 'Timed out')}</td><td>"That took too long"</td><td>The server cut the question off at its time limit.</td><td>Narrow it: one well and one date. Try again.</td></tr>
  <tr><td>${pill('cx', 'WifiOff', 'Connection lost')}</td><td>"Cannot reach the archive server"</td><td>The network dropped or the API restarted.</td><td>Wait a few seconds, then Try again. See Running it.</td></tr></tbody></table>
  <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:3mm;margin-top:auto"><div>${strip('ask_waking')}<div class="small faint">Server waking (composed)</div></div><div>${strip('ask_clarification')}<div class="small faint">Needs clarification (real)</div></div><div>${strip('ask_rate_limited')}<div class="small faint">Rate limited (real 429)</div></div><div>${strip('ask_not_evaluated')}<div class="small faint">NOT EVALUATED (composed)</div></div></div>${FOOT('UI Guide')}</section>`)

  // 17 Glossary
  P.push(`<section class="page"><div><div class="eyebrow">How to read the trace</div><h2>Stages, colours, icons and labels</h2></div>
  <div class="cols2" style="flex:1;min-height:0"><div><h3>Stages, in the order they happen</h3><table><tbody>
  <tr><td><b>Read the question</b></td><td>Code pulls out the well, date and topic. Check the chips against what you asked.</td></tr>
  <tr><td><b>Pick the reports</b></td><td>The router chooses which of the 32 reports to open, and why. Wrong reports here mean a wrong answer later.</td></tr>
  <tr><td><b>Ask for more detail</b></td><td>The gate stops a vague question before any model is called.</td></tr>
  <tr><td><b>Gather the evidence</b></td><td>Records, computed aggregates and ABSENT notes go into the context. This is all the model may cite.</td></tr>
  <tr><td><b>Draft the answer</b></td><td>A small model phrases an answer from that evidence and cites record IDs.</td></tr>
  <tr><td><b>Verify every claim</b></td><td>Code checks citations, numbers, units, dates and abstentions against the records.</td></tr>
  <tr><td><b>Second pass</b></td><td>Only if it happened: the context was enriched and the question asked again.</td></tr>
  <tr><td><b>Escalate</b></td><td>Only if it happened: the verifier objected, so a larger model retried with the same evidence.</td></tr>
  <tr><td><b>Arbitrate</b></td><td>Only if it happened: two drafts disagreed and an arbiter chose the one the records support.</td></tr>
  <tr><td><b>Resolve</b></td><td>The answer and its rule-based confidence settle.</td></tr></tbody></table></div>
  <div><h3>Colours, icons and labels</h3><table><thead><tr><th>Label</th><th>What it tells an engineer</th></tr></thead><tbody>
  <tr><td>${pill('ok', 'ShieldCheck', 'Verified')}</td><td>Every claim passed the checks. Green, with a shield and a tick.</td></tr>
  <tr><td>${pill('ok', 'CheckCircle2', 'Answered')}</td><td>The archive supports an answer.</td></tr>
  <tr><td>${pill('ab', 'MinusCircle', 'Abstained')}</td><td>The archive does not hold the answer. Amber, never red. A correct result.</td></tr>
  <tr><td>${pill('rt', 'Route', 'Router-selected')}</td><td>A report the router opened. Blue.</td></tr>
  <tr><td>${pill('cx', 'FileText', 'Context record')}</td><td>A record the model was allowed to cite. Neutral grey.</td></tr>
  <tr><td>${pill('fl', 'Flag', 'Flag')}</td><td>A check found something, or the answer needs review. Violet, never red.</td></tr>
  <tr><td>${pill('fl', 'FileCode2', 'XML only')}</td><td>The value is in the XML, not printed in the PDF. The XML is authoritative.</td></tr>
  <tr><td>${pill('ab', 'SearchX', 'ABSENT')}</td><td>The field does not exist. Lists what was searched and what was rejected.</td></tr>
  <tr><td>${pill('br', 'Play', 'Red')}</td><td>Heirs red marks only the main action, the current selection and the playhead.</td></tr>
  <tr><td><span class="mono">Replayed</span></td><td>A stored model answer, not a new call. Cost shown is from when it was generated.</td></tr></tbody></table>
  <p class="small" style="margin-top:2.4mm">Confidence is a rule, not a feeling: 0.95 for one cited record from one report, 0.90 across several reports, 0.80 for two or three records, 0.70 for four or more, 0.85 for an abstention with an ABSENT record, 0.90 when no report exists, 0.20 if the verifier failed. The model never sets it.</p></div></div>${FOOT('UI Guide')}</section>`)

  // 18 Running it
  P.push(`<section class="page"><div><div class="eyebrow">Running it</div><h2>Hosted, local and offline, and what to do when it breaks</h2></div>
  <div class="cols2" style="flex:1;min-height:0"><div class="stack"><div><h3>Hosted</h3><p>Open <b>${TODO_URL}</b>. The first visit can take up to a minute while the free-tier API wakes. Open it a few minutes before presenting.</p></div>
  <div style="margin-top:3mm"><h3>Local and offline (two commands)</h3><div class="cmd"><span class="c"># terminal 1, from the repo root</span>
conda activate nape &amp;&amp; uvicorn web.server.app:app --port 8000

<span class="c"># terminal 2, from web/app</span>
npx vite preview --port 5173 --strictPort</div><p style="margin-top:2mm">Then open <span class="mono">http://localhost:5173/?api=http://localhost:8000</span></p>
  <p class="small">The answers, evidence pages and trace for all 72 questions come from the data pack in the repo. No organiser file, no network and no key are needed. A key is needed only for brand new questions.</p></div>
  <div style="margin-top:3mm"><h3>Which API am I using?</h3><p>The footer shows it, for example <span class="mono">API localhost:8000 · set by ?api=</span>. Order of precedence: the <span class="mono">?api=</span> address, then <span class="mono">config.js</span> beside the page, then the build default. <span class="mono">?api=default</span> clears an override.</p></div></div>
  <div><h3>Troubleshooting</h3><table><thead><tr><th>Symptom</th><th>Cause and fix</th></tr></thead><tbody>
  <tr><td>Stays on "Waking the archive server"</td><td>The API is asleep (wait up to a minute), or the browser blocks it. If it never wakes: add this site's exact address to <span class="mono">ALLOWED_ORIGINS</span> on the API and redeploy (CORS).</td></tr>
  <tr><td>Wi-Fi is down</td><td>The hosted site cannot work. Switch to the local two commands above. They need no network.</td></tr>
  <tr><td>Blank page</td><td>Opened <span class="mono">dist/index.html</span> from disk: serve it over http instead. Otherwise hard-refresh and check the browser console.</td></tr>
  <tr><td>3D is slow or blank</td><td>Press 2D. The view also falls back to 2D by itself if the frame rate stays low or WebGL is missing.</td></tr>
  <tr><td>Wrong or empty data</td><td>Check the footer for the API in use. Use <span class="mono">?api=default</span>, then reload.</td></tr>
  <tr><td>Ask says rate limited</td><td>Wait for the timer. Replays of catalogue questions still work.</td></tr></tbody></table></div></div>${FOOT('UI Guide')}</section>`)

  // 19 Design notes
  const sw = (hex, name) => `<div class="sw"><i style="background:${hex}"></i><span><b>${name}</b> <span class="mono faint">${hex}</span></span></div>`
  P.push(`<section class="page"><div><div class="eyebrow">Design notes</div><h2>Principles, palette and type</h2></div>
  <div class="cols3" style="flex:1;min-height:0"><div class="stack"><h3>Principles</h3><ul>
  <li><b>Clarity, deference, depth</b> (Apple): legible type, content and data lead, chrome recedes, motion explains and never decorates.</li>
  <li><b>Swiss typography:</b> a strict 12-column grid, hierarchy from size and weight, generous space.</li>
  <li><b>Tufte for data:</b> label directly, no chart junk, one mark per question in the cost chart.</li>
  <li><b>Calm density</b> (Linear, Stripe): hairline borders, at most two elevation levels, restrained colour.</li>
  <li><b>Status is never colour alone:</b> every status has an icon and a text label. Red never means failure.</li>
  <li><b>Motion:</b> 150 to 400 ms, ease-out, staged in the pipeline's real order, off for people who ask for reduced motion.</li></ul></div>
  <div><h3>Palette</h3>${sw('#fe0000', 'Heirs red')}<p class="small" style="margin:-1mm 0 2mm">Source: heirsenergies.com site CSS (#FE0000, #E61100) and the dominant colour of its logo files. The logo itself is not used.</p>
  ${sw('#0e0c0b', 'Canvas, dark')}${sw('#151311', 'Surface 1, dark')}${sw('#1c1917', 'Surface 2, dark')}${sw('#f6f3f0', 'Canvas, light')}
  ${sw('#4fd8a8', 'Verified (dark) / #0b7556 (light)')}${sw('#f2b544', 'Abstain (dark) / #8f5200 (light)')}${sw('#7db2ff', 'Router-selected (dark) / #1c5bc0 (light)')}${sw('#c9a2ff', 'Flag (dark) / #6a32b0 (light)')}<p class="small">All text meets WCAG AA in both themes. Red fills use white text at 4.7:1 or better.</p></div>
  <div><h3>Type and shape</h3><p><b>Inter Variable</b> for the interface and display, <b>JetBrains Mono</b> for record IDs and data. Both are bundled, so the app works offline.</p>
  <p>Scale: 12, 14, 16, 20, 24, 32, 48, 64 px. Tight tracking when large, slightly open when small. Tabular numerals for every figure.</p>
  <p>Spacing follows an 8 pt scale. One corner radius family: 6, 10, 14 px. One line icon set (Lucide) at one stroke weight.</p>
  <p>The style sheet page (<span class="mono">#/styleguide</span>) shows every token and component.</p><figure><img src="${img('style_sheet', 'clean')}" style="width:100%;border-radius:1.6mm;border:1px solid var(--line)" alt=""></figure></div></div>${FOOT('UI Guide')}</section>`)

  // 20 Truthful visuals
  P.push(`<section class="page"><div><div class="eyebrow">Design notes</div><h2>Truthful visuals: what is real and what is schematic</h2></div>
  <p class="lead" style="font-size:10.5pt">Every element on screen maps to real data or a real pipeline stage. Where the data does not say, the 3D scene says so on screen.</p>
  <div class="cols2" style="flex:1;min-height:0"><div class="card"><h3>Real</h3><ul>
  <li>The shape of each well path: minimum-curvature calculation from the survey stations printed in the daily reports, drawn in true vertical depth.</li>
  <li>The depth scale in metres and every station measured depth.</li>
  <li>The six reports that carry their own survey stations, placed at that day's deepest station (solid nodes).</li>
  <li>Every stage, its order and its payload: router choice, context records, aggregates, ABSENT results, cited record IDs, verifier checks, escalations.</li>
  <li>All numbers in the guides: counts, costs, scores and confidence. They are read from the API.</li></ul></div>
  <div class="card"><h3>Schematic, and labelled as such</h3><ul>
  <li><b>Wellhead positions.</b> Absolute coordinates are not in the data. The F-wells sit on a ring and 15/9-19 is set apart. Path offsets are relative to each well's first station.</li>
  <li><b>The link from wellhead to first survey station</b> and the 1,500 m dashed line for wells with no usable survey: 15/9-F-1 (no azimuth) and 15/9-F-12 (no survey).</li>
  <li><b>The other 26 reports</b> have no depth in the data. They are ring nodes spread in date order along the path.</li>
  <li><b>Replay timing.</b> Stage order and content are real. How long each stage stays on screen is presentation pacing.</li>
  <li><b>XML-only and NOT EVALUATED screenshots</b> in the Screenshot Guide are composed from real records and payloads, and marked as such.</li></ul></div></div>
  <div class="tip"><b>Performance.</b> Measured here with software rendering (no GPU): about 10.5 to 14.3 frames a second at 1920x1080 and 17.1 to 23.8 at 1366x768 across five runs. A real-laptop figure has not been measured. [VERIFY] before relying on 3D in a live demo. The view switches itself back to 2D if it runs slowly.</div>${FOOT('UI Guide')}</section>`)
  return P.join('\n')
}

// ───────────────────────── Screenshot Guide
function screenshotGuide() {
  const P = []
  const heroFiles = ['hero_a_trust_dark_4k', 'hero_b_search_dark_4k'].map(f => existsSync(join(HERE, 'shots', 'hero', f + '.png')))
  const bySlide = Object.fromEntries(SLIDES.map(s => [s, SHOTS.filter(x => x.slides.includes(s))]))
  const SLIDE_NOTE = { problem: 'The problem: well history is buried in legacy reports.', architecture: 'The architecture: code finds facts, AI phrases, a verifier checks.', demo: 'The live demo, or a backup for it.', trust: 'Trust: evidence, verification, honest abstention.', results: 'Results: scores, coverage and counts.', value: 'Value for Heirs.', cost: 'Cost: a small model does most of the work.' }
  P.push(`<section class="page"><div class="eyebrow">Screenshot Guide · Team Trinergy</div><h1>Slide-ready shot list</h1><p class="lead">${SHOTS.length} shots, each in four files: dark at 1920x1080 and light at 1366x768, as a clean image and as an annotated version with numbered callouts. All images are in <span class="mono">web/app/docs/shots/</span>. Two hero images and a replay clip are in <span class="mono">web/app/docs/shots/hero/</span>.</p>
  <div class="cols2" style="flex:1;min-height:0"><div><h3>Which shots suit which slide</h3><table class="dense"><tbody>${SLIDES.map(s => `<tr><td style="width:24mm"><b>${s}</b></td><td class="small">${esc(SLIDE_NOTE[s])}<br><span class="mono faint">${bySlide[s].map(x => x.id).join(', ')}</span></td></tr>`).join('')}</tbody></table></div>
  <div class="stack"><div><h3>File names</h3><p class="small"><span class="mono">&lt;id&gt;_dark_1920.png</span> and <span class="mono">&lt;id&gt;_dark_1920_annotated.png</span><br><span class="mono">&lt;id&gt;_light_1366.png</span> and <span class="mono">&lt;id&gt;_light_1366_annotated.png</span><br>In the shot list this is written <span class="mono">&lt;id&gt;_{dark_1920,light_1366}{,_annotated}.png</span>.</p></div>
  <div style="margin-top:3mm"><h3>Using them on slides</h3><ul class="small"><li>Use the <b>clean</b> image on a slide and say the callouts aloud, or use the <b>annotated</b> one when the audience will read it alone.</li><li>Dark images suit a projector. Light images suit print and documents.</li><li>Show an image at no less than half a laptop screen width so the 14 px interface text stays readable.</li><li>Shots marked <b>composed</b> use a real record or payload in a mocked response. Say "composed" if asked.</li></ul></div>
  <div style="margin-top:3mm"><h3>How to take new screenshots</h3><div class="cmd"><span class="c"># API on :8000, app on :5173 (see UI Guide, Running it)</span>
node docs/capture.mjs
node docs/capture.mjs --only cost_view,ask_start
node docs/capture.mjs --variants dark
node docs/capture-hero.mjs final
node docs/build-docs.mjs</div><p class="small" style="margin-top:2mm">Run from <span class="mono">web/app</span>. The first command rewrites every image and <span class="mono">docs/facts.json</span>, so the guides always show current figures.</p></div></div></div>${FOOT('Screenshot Guide')}</section>`)

  const entry = s => {
    const v = M[s.id]?.variants?.dark
    const composed = M[s.id]?.mocked ? `<span class="pill ab" style="margin-left:2mm">${M[s.id].composed ? 'composed' : 'mocked response'}</span>` : ''
    return `<div class="card" style="display:grid;grid-template-columns:68mm 1fr;gap:4.5mm;padding:2.6mm 3.6mm;break-inside:avoid"><div><img src="../shots/${v.annotated}" style="width:100%;border-radius:1.4mm;border:1px solid var(--line)" alt=""></div>
    <div><div style="display:flex;align-items:baseline;gap:2mm"><b style="font-size:10pt">${esc(s.title)}</b>${composed}</div>
    <div class="small" style="font-size:7.8pt"><span class="mono">${s.id}</span> · ${esc(s.view)} · ${esc(s.state)}</div>
    <table class="dense" style="margin-top:.8mm"><tbody><tr><td style="width:15mm" class="faint">Caption</td><td>${esc(s.caption)}</td></tr>
    <tr><td class="faint">Slides</td><td>${s.slides.map(x => `<span class="pill cx" style="margin-right:1mm;height:4.2mm">${x}</span>`).join('')}</td></tr>
    <tr><td class="faint">Files</td><td class="mono" style="font-size:7pt">${s.id}_{dark_1920,light_1366}{,_annotated}.png</td></tr>
    <tr><td class="faint">Steps</td><td><ol style="padding-left:3.4mm;margin:0">${s.steps.map(x => `<li style="margin:0">${esc(x)}</li>`).join('')}</ol></td></tr></tbody></table></div></div>`
  }
  for (let i = 0; i < SHOTS.length; i += 3) P.push(`<section class="page" style="gap:2.4mm;padding-top:9mm"><div class="eyebrow">Shot list · ${i + 1} to ${Math.min(SHOTS.length, i + 3)} of ${SHOTS.length}</div>${SHOTS.slice(i, i + 3).map(entry).join('')}${FOOT('Screenshot Guide')}</section>`)

  const hero = ['hero_a_trust', 'hero_b_search']
  const HCAP = { hero_a_trust: 'Every answer carries its confidence, the real report page, the cited record and the checks it passed.', hero_b_search: 'Four reports opened out of 32, the rest left closed, and every claim checked before it is shown.' }
  P.push(`<section class="page"><div class="eyebrow">Hero images and clip</div><h2>Two hero frames and a replay clip</h2>
  <div class="cols2" style="flex:1;min-height:0">${hero.map((h, i) => `<div><img src="../shots/hero/${h}_dark_1080p.png" style="width:100%;border-radius:1.6mm;border:1px solid var(--line)" alt=""><p style="margin-top:2mm"><b>${i ? 'Hero B, the search' : 'Hero A, trust in one frame'}</b><br><i>${esc(HCAP[h])}</i><br><span class="mono small">${h}_dark_4k.png, ${h}_dark_1080p.png, ${h}_light_4k.png, ${h}_light_1080p.png</span></p></div>`).join('')}</div>
  <div class="card small"><b>Clip.</b> <span class="mono">hero_replay_t2016.mp4</span> and its poster <span class="mono">hero_replay_t2016_poster.png</span>: the T2-016 replay in Mission control at 1x, 1080p, no cursor. Captions are in <span class="mono">docs/shots/hero/CAPTIONS.md</span>. Regenerate with <span class="mono">node docs/capture-hero.mjs all</span>.</div>${FOOT('Screenshot Guide')}</section>`)
  void heroFiles
  return P.join('\n')
}

// ───────────────────────── print
const browser = await chromium.launch()
async function print(name, body, out) {
  pageNo = 0
  const html = join(BUILD, name + '.html'); writeFileSync(html, wrap(name, body))
  const p = await browser.newPage(); await p.goto(pathToFileURL(html).href); await p.waitForLoadState('networkidle'); await p.evaluate(() => document.fonts.ready)
  await p.pdf({ path: join(HERE, out), format: 'A4', landscape: true, printBackground: true, margin: { top: 0, right: 0, bottom: 0, left: 0 }, preferCSSPageSize: true })
  await p.close(); console.log('wrote', out)
}
const which = process.argv[2]
if (!which || which === 'ui') await print('ui_guide', uiGuide(), 'UI_Guide.pdf')
if (!which || which === 'shots') await print('screenshot_guide', screenshotGuide(), 'Screenshot_Guide.pdf')
await browser.close()
