"""Slides 14 to 25 of Flow_and_Architecture.pdf."""
from pages_a import S

PAGES = []

# 14 T2-016
PAGES.append(S("Worked example 1 · T2-016 · the date window", "A sample stamped the day before the report", '''
<p class="q">What was the density of the NaCl brine sampled from the active pit on well 15/9-F-1-C on 2014-03-26?</p>
<div class="cols2"><div>
<table><tr><th>Stage</th><th>What happened</th></tr>
<tr><td>Router</td><td>single_report, confidence high: exact date, one report <code>15_9_F_1_C_2014_03_26</code></td></tr>
<tr><td>Context</td><td>4 lines, about 181 tokens: summary, forecast, one fluid record</td></tr>
<tr><td>The trap</td><td>the sample is stamped <code>2014-03-25T21:00:00</code>, one day before the question's date, but inside the report that covers D-1 to D</td></tr>
<tr><td>Model</td><td>two Haiku runs, both answered 1.03 g/cm3 citing <code>F1C-20140326-FLUID-01</code></td></tr>
<tr><td>Verifier</td><td>all checks pass; no escalation</td></tr></table></div>
<div><div class="card ok"><h2>Result</h2>
<p><b>1.03 g/cm3</b>, confidence 0.95, verified</p>
<p class="mono" style="font-size:12px;line-height:1.5">15_9_F_1_C_2014_03_26.pdf p.1 (Drilling Fluid);<br>15_9_F_1_C_2014_03_26.xml F1C-20140326-FLUID-01</p>
<p class="muted" style="font-size:13.5px">Cost when generated: $0.0003 (2 calls, 1,946 prompt tokens). Replayed from the cache for free.</p></div>
<div class="card abs" style="margin-top:10px"><h2>Why it matters</h2><p class="muted" style="font-size:14px">In the benchmark, date-window cases scored 12 percent across eight models. Larger models abstained more here. Haiku answered. When a question also names a clock time (T2-004: 18:00 on 2013-06-28), a WINDOW NOTE is added to the context.</p></div></div></div>
''', "Sources: GET /questions/T2-016 (trace); submission/predictions.csv; submission/DATA_NOTES.md (Dates); tools/llm_bench/RECOMMENDATION.md (local benchmark notes, not committed)."))

# 15 T2-031
PAGES.append(S("Worked example 2 · T2-031 · abstention", "The failure is logged. The cost is not in the archive.", '''
<p class="q">What was the cost of the replacement parts for the equipment failure logged on well 15/9-F-15-D on 2015-08-10?</p>
<div class="cols2"><div>
<table><tr><th>Stage</th><th>What happened</th></tr>
<tr><td>Router</td><td>single_report, confidence high: <code>15_9_F_15_D_2015_08_10</code></td></tr>
<tr><td>Context</td><td>25 lines, about 1,760 tokens. The activity records do say "equipment failure" and "lost communication with tractor". An <code>ABSENT-cost</code> record says: searched 1 report, 56 records, no cost field exists.</td></tr>
<tr><td>Model</td><td>two Haiku runs both abstained</td></tr>
<tr><td>Citations</td><td>set in code: an abstention may cite only ABSENT records</td></tr>
<tr><td>Verifier</td><td>passes; no escalation (abstaining on a missing field is correct)</td></tr></table></div>
<div><div class="card abs"><h2>Result</h2>
<p><b>Not answerable from the archive.</b> No cost field exists (searched 1 report, 56 records).</p>
<p class="mono" style="font-size:12px">15_9_F_15_D_2015_08_10.pdf: all sections checked, no cost field</p>
<p class="muted" style="font-size:13.5px">Confidence 0.85. Cost when generated: $0.0009.</p></div>
<div class="card ok" style="margin-top:10px"><h2>Why it matters</h2><p class="muted" style="font-size:14px">The archive has no cost, AFE, personnel, supervisor or weather fields in any XML or PDF. A correct abstention scores a full point and an invented number scores zero. The ABSENT record is what a reviewer reads as proof that we looked.</p></div></div></div>
''', "Sources: GET /questions/T2-031 (trace); submission/predictions.csv; submission/DATA_NOTES.md (Fields the archive does not have); submission/archive_qa/context.py (_absent_record)."))

# 16 T2-017
PAGES.append(S("Worked example 3 · T2-017 · multi-report", "A verifier failure, an escalation and a citation repair", '''
<p class="q" style="font-size:14.5px">During the October 2016 plug and abandonment campaign, in what order did the rig move between wells while cutting and pulling production risers, from the 15/9-F-15-D report on 2016-10-19 to the 15/9-F-1-C report on 2016-10-22?</p>
<div class="cols2"><div>
<table style="font-size:13px"><tr><th>Stage</th><th>What happened</th></tr>
<tr><td>Router</td><td>multi_report: range 2016-10-19..2016-10-22 spans wells, so 4 reports (F-15-D, F-12, F-11-B, F-1-C)</td></tr>
<tr><td>Context</td><td>93 lines, about 6,003 tokens; recall forced in 16 matching records</td></tr>
<tr><td>Haiku run 1</td><td>answered, citing 8 records. It also wrote "24" and "134.9" (runs differed on these)</td></tr>
<tr><td>Verifier</td><td><b>failed</b>: "numbers in the answer not found in the cited records: ['24']"</td></tr>
<tr><td>Escalation</td><td>Sonnet 5.5 called with that message. Its answer <b>passed</b> all checks</td></tr>
<tr><td>Repair</td><td>citation repair added <code>F1C-20161022-ACT-01</code> and <code>ACT-02</code></td></tr></table></div>
<div><div class="card ok"><h2>Result</h2>
<p style="font-size:14px">Order: F-15-D, F-14, F-12, F-11 B, F-1 C, then planned moves to F-7 and F-9 A. Confidence 0.70 (ten records).</p>
<p class="muted" style="font-size:13.5px">3 calls, 38,301 prompt tokens, $0.034 when generated. Sonnet cost 91 percent of that.</p></div>
<div class="card flag" style="margin-top:10px"><h2>Why it matters</h2><p class="muted" style="font-size:14px">The cheap model got the story right but added a number that no cited record contains. The verifier caught it. The escalation fixed it for a few cents. Nobody had to read the answer to know it was wrong.</p></div></div></div>
''', "Sources: GET /questions/T2-017 (trace: router, contexts, model_calls, verifier, decisions); submission/predictions.csv; web/server/samples/T2-017.json."))

# 17 T2-020
PAGES.append(S("Worked example 4 · T2-020 · archive-wide", "No well named, so the whole archive is searched", '''
<p class="q" style="font-size:14.5px">On which completion days did the crew land the BOP onto the surface riser and make up the NT2 connector, and what BOP pressure tests were done on those days?</p>
<div class="cols2"><div>
<table style="font-size:13px"><tr><th>Stage</th><th>What happened</th></tr>
<tr><td>Router</td><td>archive_wide, confidence <b>low</b>: no well or date named, all 32 reports</td></tr>
<tr><td>Context</td><td>442 candidate records, cap about 12,000 tokens: kept 117, dropped 325 (forced matches first). Confidence loses 0.05 for truncation</td></tr>
<tr><td>Haiku runs</td><td>both answered but disagreed on numbers and times</td></tr>
<tr><td>Arbitration</td><td>Sonnet 5.5 arbitrated; its answer verified and was committed</td></tr>
<tr><td>Repair</td><td>added <code>F15D-20131214-ACT-14</code></td></tr></table></div>
<div><div class="card ok"><h2>Result</h2>
<p style="font-size:14px">Two days: 2013-06-27 (F-11-B report of 2013-06-28) and 2013-12-13 (F-15-D report of 2013-12-14), with the BOP pressure tests of each day. Confidence 0.65, seven cited records.</p>
<p class="muted" style="font-size:13.5px">3 calls, 67,502 prompt tokens, $0.057 when generated.</p></div>
<div class="card abs" style="margin-top:10px"><h2>Why it matters</h2><p class="muted" style="font-size:14px">This is the hardest class. The context does not hold everything, so confidence is lower by rule and the trace shows what was dropped. For new counts and extremes, code now computes the answer first (aggregates). The 32 published contexts, including this one, are unchanged by that.</p></div></div></div>
''', "Sources: GET /questions/T2-020 (trace); submission/predictions.csv; submission/archive_qa/context.py (TRUNCATED note); verify.py (confidence)."))

# 18 traps
PAGES.append(S("Data traps", "Seven things that would have produced confident wrong answers", '''
<div class="cols2"><div>
<table style="font-size:13px"><tr><th>Trap</th><th>How it is handled</th></tr>
<tr><td><b>D-1 window.</b> Report D covers D-1 to D.</td><td>Every record carries its window; a WINDOW NOTE and the verifier accept the D-1 stamp.</td></tr>
<tr><td><b>1980 placeholder.</b> The 15/9-19-A report dated 1980-01-01 has a 1997 spud date and no text.</td><td>Still cited: its kick-off 2178 m is printed on PDF page 1 (T2-001).</td></tr>
<tr><td><b>Same-date reports.</b> F-1-B and F-1-C both have 2014-02-22.</td><td>Filter by well, then by date.</td></tr>
<tr><td><b>Well-name variants.</b> "15/9-F-11 B", F-11B, F-11-T2; XML says "NO 15/9-F-1 C"; bare F-1 is the main bore.</td><td>One canonical name; tested spellings; each date paired with its own well.</td></tr></table></div>
<div><table style="font-size:13px"><tr><th>Trap</th><th>How it is handled</th></tr>
<tr><td><b>XML vs PDF.</b> PDF prints Y for tightWell and HPHT in all 32 reports; XML says 0. Days ahead or behind blank in 11 PDFs. Bit end depth 2574 vs 2577.</td><td>XML is authoritative; derived NOTE records; the locator never gives these fields a page.</td></tr>
<tr><td><b>XML-only fields.</b> NPD numbers, rig code, wellhead elevation, fixedRig, mudClass, BOP rating, bit grading.</td><td>Cited as "XML only: field; not printed in the PDF".</td></tr>
<tr><td><b>Western Atlas.</b> A company name in 19-A 1997-08-29.</td><td>It is a wireline logging company, not mud logging. T2-032 abstains and says so.</td></tr></table>
<p class="faint" style="font-size:12.5px;margin-top:8px">Also: -999.99 and the text "None" are missing, never values. There is no report for F-14, and F-15-D has no report on 2013-12-15 (T2-027, T2-029 abstain with no model call).</p></div></div>
''', "Sources: submission/DATA_NOTES.md (all items); submission/archive_qa/discrepancy.py, xmlonly.py; submission/predictions.csv (T2-001, T2-027, T2-029, T2-032)."))

# 19 model strategy
PAGES.append(S("Model strategy", "A small model does the work. A bigger one is called only when the code objects.", '''
<div class="cols2"><div>
<table style="font-size:12.5px"><tr><th>Model (16 cases)</th><th class="n">Answer acc.</th><th class="n">$ per call</th><th class="n">p50 s</th></tr>
<tr><td><b>claude-haiku-5.5</b></td><td class="n"><b>100%</b></td><td class="n">0.00026</td><td class="n">1.21</td></tr>
<tr><td>claude-sonnet-5.5</td><td class="n">94%</td><td class="n">0.00528</td><td class="n">2.12</td></tr>
<tr><td>claude-opus-5.5</td><td class="n">94%</td><td class="n">0.00980</td><td class="n">2.16</td></tr>
<tr><td>gemini-3-flash-preview</td><td class="n">94%</td><td class="n">0.00108</td><td class="n">1.34</td></tr>
<tr><td>deepseek-v4-flash</td><td class="n">87.5%</td><td class="n">0.00012</td><td class="n">1.28</td></tr>
<tr><td>gpt-oss-120b</td><td class="n">87.5%</td><td class="n">0.00013</td><td class="n">0.82</td></tr>
<tr><td>qwen3.7-plus</td><td class="n">75%</td><td class="n">0.00062</td><td class="n">2.70</td></tr>
<tr><td>llama-4-scout</td><td class="n">56%</td><td class="n">0.00021</td><td class="n">2.82</td></tr></table>
<p class="faint" style="font-size:12px;margin-top:6px">Caveat: 16 cases, one call each. One case is 6 points. Good for failure patterns and cost, not for ranking close models. Zero invented citations in 405 calls.</p></div>
<div><div class="card ok" style="margin-bottom:8px"><h2>Why Haiku is primary</h2><p class="muted" style="font-size:14px">Best accuracy on our cases, decision-stable on 4 of 4 repeats, 1.2 s median, about a twentieth of Sonnet's price. The task is reading a few lines, not reasoning, and the verifier does the checking.</p></div>
<div class="card flag" style="margin-bottom:8px"><h2>Where the money goes (32 questions)</h2><p class="muted" style="font-size:14px">Haiku: 104 calls, 80 percent of calls, 12.7 percent of cost ($0.083). Sonnet: 26 calls, 20 percent of calls, 87.3 percent of cost ($0.568). Total $0.651.</p></div>
<div class="card abs"><h2>Provider pinning</h2><p class="muted" style="font-size:13.5px">Anthropic requests must be pinned to the Anthropic provider with require_parameters off. With it on, every request returned HTTP 404. If the pin is unavailable on a key, the run falls back to default routing for the same model and logs a warning.</p></div></div></div>
''', "Sources: tools/llm_bench/RECOMMENDATION.md (local benchmark notes, not committed [VERIFY]); GET /costs (web/server/API.md); submission/archive_qa/llm.py (ProviderUnavailable fallback)."))

# 20 reproducibility
PAGES.append(S("Reproducibility", "Reviewers rerun the notebook in under a minute, with no key", '''
<div class="cols2"><div>
<table style="font-size:13.5px"><tr><th>Run</th><th>What happens</th><th>Time</th></tr>
<tr><td>No key, 32 published questions</td><td>all answers from the committed cache; predictions.csv identical (md5 90717d3e7767eee3f53b739bb32923fc)</td><td>about 14 s from a fresh kernel (about 10 s of compute)</td></tr>
<tr><td>Key, 40 new questions, cold cache</td><td>81 live calls, valid output file, 0 questions needing review</td><td>about 21 s, $0.12</td></tr>
<tr><td>Key, 3 demo questions, cold cache</td><td>6 live calls, 2 answered, 1 abstained</td><td>about 7 s incl. kernel start, $0.003</td></tr>
<tr><td>No key, uncached question</td><td>"NOT EVALUATED: no API key and no cached answer", never a guess</td><td>instant</td></tr></table>
<p class="muted" style="margin-top:10px;font-size:14px"><b>Key names:</b> OPENROUTER_KEY first, then OPENROUTER_API_KEY, OpenRouter_Key, openrouter_api_key; environment or <code>.env</code>. The first notebook cell prints which one it found, never its value.</p></div>
<div><div class="card ok"><h2>Why it is deterministic</h2>
<ul style="font-size:14px"><li>Models are not bit-identical even at temperature 0. The cache is what fixes the answers.</li>
<li>Cache keys include the question text, so a changed question misses instead of returning a stale answer.</li>
<li>New answers go to a git-ignored runtime cache. The committed cache is never modified by a run.</li>
<li>A different question file writes <code>predictions_&lt;file&gt;.csv</code>, never the committed predictions.csv.</li></ul></div>
<div class="card" style="margin-top:10px"><h2>Tests (fresh run, 2026-11-08)</h2><p class="muted" style="font-size:14px">345 passed, 1 skipped (pipeline, about 31 s). 99 passed (API, about 97 s). Tests assert the 32 contexts and routes are unchanged, that no socket opens with no key, and that predictions.csv is byte-identical.</p></div></div></div>
''', "Sources: submission/README.md; tests/test_generalise.py; submission/archive_qa/llm.py; session runs of the notebook with NAPE_QUESTIONS_CSV (timings are one run each [VERIFY on your machine]); pytest output 2026-11-08."))

# 21 generalisation
PAGES.append(S("Generalisation", "Forty questions the pipeline had not seen", '''
<div class="cols2"><div>
<table><tr><th>Category</th><th class="n">Before</th><th class="n">After</th></tr>
<tr><td>Single-report lookups (24)</td><td class="n">23</td><td class="n">24</td></tr>
<tr><td>Cross-report comparisons (4)</td><td class="n">0</td><td class="n">4</td></tr>
<tr><td>Archive-wide counts and maxima (5)</td><td class="n">1</td><td class="n">5</td></tr>
<tr><td>Fields the archive does not hold (7)</td><td class="n">7</td><td class="n">7</td></tr>
<tr><td><b>Total (40)</b></td><td class="n"><b>31</b></td><td class="n"><b>40</b></td></tr></table>
<p class="muted" style="font-size:13.5px;margin-top:8px">Expected answers were computed by separate code reading the XML directly. Cost for the run: $0.276 before, $0.061 after.</p>
<div class="card abs"><h2>Honest caveat</h2><p class="muted" style="font-size:13.5px">We fixed the failures after seeing them, so 40 of 40 is not a clean estimate. A second 40 from a different random seed also scored 40 of 40, but it uses the same question templates, and that result is not saved in the repository [VERIFY]. The scorer is lenient on numbers.</p></div></div>
<div><h2>What we fixed</h2>
<ul style="font-size:14px"><li><b>Router:</b> a date followed by "report for F-1" now pairs with F-1, not the earlier well. One question had routed to the wrong report.</li>
<li><b>Computed aggregates:</b> counts, extremes and comparisons are computed in code and shown as evidence lines.</li>
<li><b>Field-name section match:</b> a question about "date drilling was completed" now loads the section holding <code>dateDrillComplete</code>.</li>
<li><b>Generic absence:</b> an ABSENT-search record when no content word matches anything.</li>
<li><b>Second pass:</b> one retry with an enriched context. It did not fire on the final run. In a test with aggregates switched off it fired on 5 of 8 and rescued all 5; the other 3 were confident wrong answers, which it does not touch [VERIFY: session test, not committed].</li></ul>
<p class="faint" style="font-size:12.5px">Pending: the engineer's hand check of the 32 answers and an independent test set.</p></div></div>
''', "Sources: submission/eval/generalisation (gen.py, run.py, score.py, questions.csv, expected.json); GET /generalisation (baseline_mean_score 0.775, mean_score 1.0, cost_usd 0.060687); commit eecf7cd; submission/eval/key_template.csv (no verdicts)."))

# 22 system architecture: API
PAGES.append(S("System architecture · backend API", "The API wraps the frozen pipeline and records every stage", '''
<div class="cols2"><div>
<table style="font-size:12.5px"><tr><th>Endpoint</th><th>Returns</th></tr>
<tr><td><code>GET /health</code></td><td>status, live mode, models, budget left</td></tr>
<tr><td><code>GET /questions</code></td><td>72 questions (32 + 40) with status and flags</td></tr>
<tr><td><code>GET /questions/{id}</code></td><td>answer, evidence, cited records, full trace</td></tr>
<tr><td><code>POST /ask</code>, <code>/ask/stream</code></td><td>any question; the stream sends one event per real stage</td></tr>
<tr><td><code>GET /pages/{record}.png</code></td><td>the PDF page with the evidence highlighted</td></tr>
<tr><td><code>GET /archive</code>, <code>/trajectories</code></td><td>reports, wellbores, survey paths (approximate)</td></tr>
<tr><td><code>GET /costs</code>, <code>/generalisation</code></td><td>cost split, unseen-set results</td></tr></table>
<p class="faint" style="font-size:12.5px;margin-top:6px">The server starts with a data pack (7.5 MB: records, 54 page images, boxes). No organiser raw file is needed at run time.</p></div>
<div><h2>Trace schema</h2>
<p class="muted" style="font-size:13.5px"><b>router</b> (mode, confidence, reports and why) · <b>contexts</b> (tokens, records, aggregates, ABSENT) · <b>model_calls</b> (role, model, cache hit, provider-reported tokens, latency, cost) · <b>verifier</b> (13 named checks) · <b>escalations</b>, <b>second_pass</b>, <b>arbitration</b> · <b>cited</b> · <b>decisions</b> · <b>totals</b> · <b>events</b>.</p>
<h2>Guardrails</h2>
<ul style="font-size:13.5px"><li><b>Frozen pipeline:</b> the trace builder watches from outside; tests prove predictions and caches are byte-identical after live asks.</li>
<li><b>Clarification gate:</b> a vague question with no well, date or field term and no cached answer gets examples and costs nothing.</li>
<li><b>Limits:</b> 400-character cap, 6 per minute and 40 per day per client, 4 concurrent, 120 s timeout, spend cap $2.00 (persisted).</li>
<li><b>Key hygiene:</b> never returned or logged; errors pass through a redactor.</li></ul></div></div>
''', "Sources: web/server/API.md (endpoints, Trace, Guarantees, Configuration); web/server/app.py, guards.py, safety.py; web/server/data/MANIFEST.json."))

# 23 frontend, deployment, security
PAGES.append(S("System architecture · dashboard and deployment", "Eleven views, one real API, an offline fallback", '''
<img class="dia" src="DIA/deployment.png" style="max-height:325px;width:auto;margin:0 auto 8px">
<div class="cols2"><table style="font-size:12.5px"><tr><th>View</th><th>What it shows</th></tr>
<tr><td>Overview, Questions</td><td>live counters; all 72 questions by set, mode, status</td></tr>
<tr><td>Answer</td><td>answer, confidence rule, PDF page with highlights, trace</td></tr>
<tr><td>Mission control</td><td>2D replay of the real trace; 3D view (three.js), Focus mode</td></tr>
<tr><td>Ask</td><td>your own question, live trace, designed error states</td></tr></table>
<table style="font-size:12.5px"><tr><th>View</th><th>What it shows</th></tr>
<tr><td>Generalisation, Cost, Archive</td><td>unseen set before and after; cost and cache; 32-report timeline</td></tr>
<tr><td>Impact, Present, Styleguide</td><td>use cases and roadmap for Heirs; guided tour; tokens</td></tr>
<tr><td colspan="2" class="faint">Everything on screen comes from the API. Fonts, icons and libraries are bundled.</td></tr></table></div>
''', "Sources: web/app/README.md (Views, Run, Run: hosted); web/DEPLOY.md; web/render.yaml; web/server/API.md (security headers); diagram docs/presentation/diagrams/deployment.svg."))

# 24 cost, limits, roadmap
PAGES.append(S("Cost, limits, roadmap", "What it costs, what it cannot do, what comes next", '''
<div class="cols3">
<div><h2>Cost</h2>
<table style="font-size:12.5px"><tr><th>Item</th><th class="n">USD</th></tr>
<tr><td>32 questions, cached (130 calls)</td><td class="n">0.651</td></tr>
<tr><td>per question</td><td class="n">0.0217</td></tr>
<tr><td>Escalation (26 calls)</td><td class="n">0.568</td></tr>
<tr><td>Haiku calls (104)</td><td class="n">0.083</td></tr>
<tr><td>40 unseen, after fixes</td><td class="n">0.061</td></tr>
<tr><td>3 demo questions, live</td><td class="n">0.003</td></tr>
<tr><td>Model benchmark [VERIFY]</td><td class="n">0.62</td></tr></table>
<p class="faint" style="font-size:12px">A typical new question costs well under a cent. A hard archive-wide one up to about five cents.</p></div>
<div><h2>Limits</h2>
<ul style="font-size:13px"><li>One field, 32 reports. No scanned pages here: every PDF page has a text layer. OCR is not built.</li>
<li>No cost, personnel, supervisor or weather fields exist, so those questions abstain.</li>
<li>Hand check by a petroleum engineer is pending. Independent test pending. Hidden-test score unknown.</li>
<li>Confident wrong answers on multi-report questions are caught only if a number or ID breaks a check.</li>
<li>Free Render plan sleeps; its spend counter resets on restart. The key's own limit always holds.</li>
<li>Locator reaches 78.8% of records; the rest are cited from the XML.</li></ul></div>
<div><h2>Roadmap</h2>
<table style="font-size:12.5px"><tr><td><span class="tag ok">Today</span></td><td>Volve prototype: cited answers, verifier, abstention</td></tr>
<tr><td><span class="tag route">Next</span></td><td>Pilot on a small set of real Heirs daily reports, scored on Heirs engineers' own questions</td></tr>
<tr><td><span class="tag flag">Then</span></td><td>Completion reports, well tests and surveys, with page evidence</td></tr>
<tr><td><span class="tag abs">Later</span></td><td>One searchable, auditable memory across the asset base</td></tr></table>
<p class="faint" style="font-size:12px;margin-top:6px">Not yet done: OCR for scans, a larger blind test, deployment inside Heirs, role-based access.</p></div></div>
''', "Sources: GET /costs (web/server/API.md); submission/indexes/cost_summary.csv; web/DEPLOY.md; web/app/src/views/Impact.tsx (roadmap); submission/DATA_NOTES.md; tools/llm_bench/RECOMMENDATION.md (local, not committed [VERIFY])."))

# 25 cheat sheet
PAGES.append(S("One-page cheat sheet", "Numbers you may be asked, with their sources", '''
<table style="font-size:12.5px"><tr><th>Fact</th><th>Value</th><th>Source</th></tr>
<tr><td>Reports, wellbores, PDF pages</td><td>32, 8, 54</td><td>submission/DATA_NOTES.md</td></tr>
<tr><td>Records in the store</td><td>1,783 (1,707 archive, 76 derived notes)</td><td>web/server/data/MANIFEST.json</td></tr>
<tr><td>Located in the PDF</td><td>99.2% table and narrative, 94.5% of printed, 78.8% of all</td><td>submission/DATA_NOTES.md</td></tr>
<tr><td>32 answers</td><td>24 answered, 8 abstained (2 early)</td><td>GET /questions; submission/predictions.csv</td></tr>
<tr><td>Confidence values used</td><td>0.65, 0.70, 0.80, 0.85, 0.90, 0.95</td><td>submission/indexes/answers.json (local artefact)</td></tr>
<tr><td>Cached calls and cost</td><td>130 calls, $0.651, $0.0217 per question, 949,726 prompt tokens</td><td>submission/indexes/cost_summary.csv</td></tr>
<tr><td>Model split</td><td>Haiku 104 calls, 12.7% of cost; Sonnet 26 calls, 87.3%</td><td>GET /costs</td></tr>
<tr><td>Models, settings</td><td>Haiku 5.5 and Sonnet 5.5, temperature 0, 400/3,000/1,500 token caps, Anthropic pin</td><td>submission/archive_qa/config.py</td></tr>
<tr><td>Unseen 40</td><td>31 to 40 correct; $0.276 to $0.061; tuned on them</td><td>GET /generalisation; commit eecf7cd</td></tr>
<tr><td>Offline rerun</td><td>about 14 s from a fresh kernel, md5 90717d3e7767eee3f53b739bb32923fc</td><td>submission/README.md; clean-clone run 2026-11-08</td></tr>
<tr><td>Tests</td><td>345 pipeline (1 skipped) and 99 API</td><td>pytest, 2026-11-08</td></tr>
<tr><td>Verifier checks</td><td>13</td><td>GET /questions/{id} trace</td></tr>
<tr><td>API limits</td><td>400 characters, 6 per minute, 40 per day, $2.00 server budget</td><td>web/server/API.md</td></tr>
<tr><td>Benchmark</td><td>8 models, 16 cases, 405 calls, 0 invented citations</td><td>tools/llm_bench (local) [VERIFY]</td></tr></table>
''', "All values were read from the files named in this table on 2026-11-08. Items marked [VERIFY] are not in the committed repository."))
