"""Slides 1 to 13 of Flow_and_Architecture.pdf. Every number comes from a repo file named in the slide's source line."""

def S(kick, title, body, src, n=None):
    return f'<section class="slide"><div class="bar"></div><div class="pg">__PG__</div><div class="kick">{kick}</div><h1>{title}</h1><div class="in">{body}</div><div class="src">{src}</div></section>'

PAGES = []

# 1 cover
PAGES.append('''<section class="slide"><div class="bar"></div>
<div style="position:absolute;left:52px;top:150px;width:1000px">
<div class="kick">NAPE AICE 2026 · Track 2 · Team Trinergy · built for Heirs Energies</div>
<h1 style="font-size:64px;letter-spacing:-.035em;line-height:1.02;margin-bottom:22px">Intelligent Well Archive</h1>
<p style="font-size:24px;line-height:1.35;color:var(--t2);max-width:900px">Ask a question about decades of drilling reports. Get the answer, the page it came from, and an honest "not in the archive" when it is not.</p>
<p style="margin-top:34px"><span class="tag ok">Code finds the facts</span><span class="tag flag">AI phrases them</span><span class="tag ok">A verifier checks</span><span class="tag abs">Abstaining is valid</span></p>
</div>
<div class="src">Flow and architecture pack for the three presenters (AI engineer, product designer, petroleum engineer). Data: Equinor Volve dataset. Palette: web/app/src/styles/tokens.css. No Heirs logo is used.</div></section>''')

# 2 overview
PAGES.append(S("Overview", "The problem, the idea, the four principles", '''
<div class="cols2" style="margin-bottom:12px">
<div class="card"><h2>The problem</h2>
<p class="muted">Well history sits in daily drilling reports. Engineers search by hand, and nobody can easily show where a number came from. The task: answer 32 questions about Volve daily reports with traceable evidence (file, page, section), and say so when the archive cannot answer.</p>
<p class="muted">In this contest a correct abstention scores a full point. An invented citation scores zero.</p></div>
<div class="card"><h2>The idea</h2>
<p class="muted">Turn every report into small records with stable IDs. Let code pick the right records. Let a small model write one short answer from only those records. Let code check the answer before it is accepted.</p>
<p class="muted">If the archive has no such field, the system says what it searched and stops.</p></div></div>
<div class="cols4">
<div class="card ok"><span class="tag ok">1</span><h2>Code finds facts</h2><p class="muted" style="font-size:14px">Parser, router and context builder pick the evidence. The model never searches the archive.</p></div>
<div class="card flag"><span class="tag flag">2</span><h2>AI phrases</h2><p class="muted" style="font-size:14px">A small model (Haiku 5.5) turns the chosen lines into a short answer in a fixed JSON shape.</p></div>
<div class="card ok"><span class="tag ok">3</span><h2>Verifier checks</h2><p class="muted" style="font-size:14px">13 code checks. A number, date or ID that is not in the cited records is rejected.</p></div>
<div class="card abs"><span class="tag abs">4</span><h2>Abstention is valid</h2><p class="muted" style="font-size:14px">No field, no report, no answer. The evidence column says what was searched.</p></div></div>
''', "Source: CLAUDE.md (goal and scoring rules); submission/archive_qa/prompts.py; submission/archive_qa/verify.py; web/app/src/views/Impact.tsx (problem statement)."))

# 3 headline numbers
PAGES.append(S("Overview", "Headline numbers", '''
<div class="cols4" style="margin-bottom:14px">
<div class="card"><div class="big">24 + 8</div><div class="lab">of 32 questions: 24 answered, 8 abstained (2 of them because the report does not exist)</div></div>
<div class="card"><div class="big">$0.022</div><div class="lab">per question: 130 cached model calls cost $0.651 for all 32</div></div>
<div class="card"><div class="big">~14 s</div><div class="lab">from a fresh kernel to a regenerated predictions.csv, offline, no API key, same file every time</div></div>
<div class="card"><div class="big">0</div><div class="lab">invented citations: every cited ID must exist in the store and in the model's context</div></div></div>
<div class="cols4" style="margin-bottom:14px">
<div class="card"><div class="big">1,783</div><div class="lab">records from 32 reports, 8 wellbores, 54 PDF pages (1,707 archive records and 76 derived notes)</div></div>
<div class="card"><div class="big">31 → 40</div><div class="lab">of 40 unseen questions, before and after the generalisation fixes. Tuned on those 40 (see page 21)</div></div>
<div class="card"><div class="big">345 + 99</div><div class="lab">tests pass: 345 pipeline tests (1 skipped) and 99 API tests, from a fresh run</div></div>
<div class="card"><div class="big">13</div><div class="lab">verifier checks, all in code. Confidence is set by rules, never by the model</div></div></div>
<p class="muted" style="font-size:14px">Honest status: the engineer's hand check of the 32 answers and an independent test are <b>pending</b>. The key file <code>submission/eval/key_template.csv</code> has no verdicts yet. The hidden-test score is unknown.</p>
''', "Sources: GET /questions and GET /costs (web/server/API.md); submission/indexes/cost_summary.csv; submission/predictions.csv; web/server/data/MANIFEST.json; submission/DATA_NOTES.md; pytest runs on 2026-11-08 (root: 345 passed, 1 skipped; web/server/tests: 99 passed)."))

# 4 flow diagram
PAGES.append(S("The flow", "End to end, in one picture", '<img class="dia" src="DIA/pipeline.png" style="margin-top:2px;max-height:560px;width:auto;margin-left:auto;margin-right:auto">', "Diagram: docs/presentation/diagrams/pipeline.svg. Code: submission/archive_qa (answer.py, route.py, context.py, verify.py, write.py); web/server (API and trace)."))

# 5 data
PAGES.append(S("Stage 1 · Data and formats", "What goes in: 32 reports, three formats", '''
<div class="cols2"><div>
<table><tr><th>Format</th><th>What it is</th><th>Role</th></tr>
<tr><td>XML</td><td>WITSML 1.4 drillReport, 32 files</td><td>Source of truth for values</td></tr>
<tr><td>PDF</td><td>The same report, 54 pages, all with a text layer (no OCR)</td><td>Page and section for citations</td></tr>
<tr><td>HTML</td><td>No text that is not also in the PDF</td><td>Not used</td></tr></table>
<p style="margin-top:12px" class="muted"><b>Wellbores (8):</b> 15/9-19-A, F-1, F-1-B, F-1-C, F-11-B, F-11-T2, F-12, F-15-D. There is no report for F-14.</p>
<p class="muted">A report dated D covers D-1 00:00 to D 00:00.</p></div>
<div class="card"><h2>What it prevents</h2>
<ul><li>Reading a value from the wrong source: the XML wins when the PDF disagrees.</li>
<li>Counting wells from a bad hint column: the manifest's <code>well_hint</code> leaks the year, so it gives 11 "wells". We count from file names (8).</li>
<li>Encoding errors: 28 files declare ISO-8859-1, four declare nothing. Parsing raw bytes reads both.</li></ul>
<h2 style="margin-top:8px">What comes out</h2><p class="muted">A clean list of reports per wellbore and date, ready for the parser.</p></div></div>
<p class="faint" style="margin-top:8px;font-size:13px">Missing values: <code>-999.99</code> is a sentinel (174 occurrences) and is never output as a value. The text "None" in 5 summary or forecast fields is also missing.</p>
''', "Source: submission/DATA_NOTES.md (Archive shape, Dates, Missing values); submission/archive_qa/wells.py (report discovery)."))

# 6 parser + store
PAGES.append(S("Stage 2 · Parser and evidence store", "From XML to records with stable IDs", '''
<div class="cols2"><div>
<div class="card ok" style="margin-bottom:10px"><h2>Record IDs</h2>
<p class="mono" style="line-height:1.7">F1C-20140326-FLUID-01<br>19A-19800101-STATUS-MDKICKOFF<br>F15D-20150810-ACT-01<br>F1C-20161022-FCST-FORECAST24HR</p>
<p class="muted" style="font-size:14px">Well code, report date, record type, then a field name or a number. The same ID appears in the context, in the model's citation and in the evidence column.</p></div>
<h2>Record types (1,783)</h2>
<table><tr><td>status 619</td><td>activity 370</td><td>wellbore 275</td></tr><tr><td>header 224</td><td>survey 80</td><td>note 76</td></tr><tr><td>fluid 40</td><td>summary 32</td><td>forecast 32</td></tr><tr><td>casing 9</td><td>equip. failure 8</td><td>pore pressure 7</td></tr><tr><td>gas 3</td><td colspan="2">log, bit, strat, lithology 2 each</td></tr></table></div>
<div class="card"><h2>What it does</h2>
<ul><li>Reads each XML section into small records: one value, its unit, its time stamp, its report window.</li>
<li>Keeps missing values as missing, with the original text.</li>
<li>Builds <b>derived NOTE records</b> when XML and PDF disagree (64 flag fields, 11 days-behind, 1 bit end depth).</li>
<li>Keeps a bit with two nozzle blocks complete. A parser bug once let the second block overwrite the first; it is fixed and tested.</li></ul>
<h2 style="margin-top:8px">What it prevents</h2><ul><li>Guessing: every later step names a record, not a paragraph.</li><li>Silent loss of data from repeated tags.</li></ul></div></div>
''', "Sources: submission/archive_qa/parse.py, store.py; records.parquet value counts (1,783 records; web/server/data/MANIFEST.json); submission/DATA_NOTES.md (XML vs PDF audit)."))

# 7 locator
PAGES.append(S("Stage 3 · Page locator", "Every record gets a page, a section and a box", '''
<div class="cols2"><div>
<div class="cols3" style="margin-bottom:10px">
<div class="card ok"><div class="big" style="font-size:34px">99.2%</div><div class="lab">table-row and narrative records located exactly</div></div>
<div class="card ok"><div class="big" style="font-size:34px">94.5%</div><div class="lab">of records the PDF prints</div></div>
<div class="card abs"><div class="big" style="font-size:34px">78.8%</div><div class="lab">of all records (the rest are XML only)</div></div></div>
<p class="muted">The locator searches each PDF page text, with all whitespace removed, because the PDF splits some words ("Summar y", "Sur vey Station"). It returns page, section heading and highlight rectangles.</p></div>
<div class="card"><h2>XML-only records</h2>
<p class="muted" style="font-size:14.5px">219 records sit in fields the PDF has no label for (for example <code>wellheadElevation</code>, <code>fixedRig</code>, hole-start fields). 64 are tightWell and HPHT, excluded by design because the PDF prints Y and the XML says 0 in all 32 reports. Their citations name the XML only, as "XML only: field; not printed in the PDF".</p>
<h2 style="margin-top:8px">What it prevents</h2><ul><li>Citing a page that does not show the value.</li><li>Showing a reviewer a PDF value that conflicts with the XML.</li></ul></div></div>
<p class="faint" style="font-size:13px;margin-top:6px">74 records are not located: 31 rig-code aliases, 32 NPD aliases, 11 daysBehind values (blank in the PDF) and 5 empty summary or forecast texts (heading only).</p>
''', "Sources: submission/DATA_NOTES.md (PDF location coverage); submission/archive_qa/locate.py, xmlonly.py; web/server/API.md (GET /pages, xml_only)."))

# 8 router
PAGES.append(S("Stage 4 · Router", "From a question to the right reports", '''
<div class="cols2"><div>
<table><tr><th>Mode</th><th>When</th></tr>
<tr><td><span class="tag route">single_report</span></td><td>one well and one date: the report dated D</td></tr>
<tr><td><span class="tag route">multi_report</span></td><td>several wells or dates, or a date range</td></tr>
<tr><td><span class="tag route">archive_wide</span></td><td>no well or date named: all 32 reports</td></tr>
<tr><td><span class="tag abs">early abstain</span></td><td>the well or date is not in the archive: no model call, confidence 0.9</td></tr></table>
<p class="muted" style="margin-top:10px;font-size:14.5px">The router reads wells and dates in many spellings: F-11B, F 11 B, 15/9-F-11 B, NO 15/9-F-11 B, 15_9_F_11_B, F-1C and F-1-C; and 2014-03-14, 14 March 2014, March 14th 2014, 14/03/2014. Each date is paired with the well named for it ("the 24 September report for F-1B ... the 2013-08-12 report for F-1").</p></div>
<div class="card"><h2>Rules that matter</h2>
<ul><li><b>Filter by well before date.</b> F-1-B and F-1-C both have a report dated 2014-02-22.</li>
<li><b>Exact date D first.</b> D+1 is used only as a recorded fallback, and the context says so.</li>
<li>Topic words (cost, personnel, supervisor, weather, mud logging) set which sections to load.</li>
<li><b>Confidence level</b> in the trace: high = every target matched by exact date or range; medium = fallback or partial; low = whole archive. The API derives it from the router output.</li></ul>
<h2 style="margin-top:6px">What it prevents</h2><p class="muted" style="font-size:14.5px">Sending the model the wrong well, the wrong day, or the whole archive when one report is enough.</p></div></div>
''', "Sources: submission/archive_qa/route.py (route_question, find_dates), wells.py (find_wells); tests/test_generalise.py (phrasings, pairing); web/server/API.md (Trace, router.confidence)."))

# 9 context builder
PAGES.append(S("Stage 5 · Context builder", "What the model is allowed to see", '''
<div class="cols2"><div>
<pre>[F1C-20140326-FLUID-01] fluid | density=1.03 g/cm3;
type=NaCl brine; locationSample=Active pit; md=4094 m
| report 2014-03-26 | at 2014-03-25T21:00:00</pre>
<p class="muted" style="font-size:14.5px">One line per record: ID, type, fields, report date, time stamp. A single-report context is small (T2-016: 4 lines, about 181 tokens). Multi-report contexts are capped at about 12,000 tokens, and recall forces in the records that match the question's distinctive words first.</p>
<h3>Special lines</h3>
<ul style="font-size:14.5px"><li><b>WINDOW NOTE:</b> when a question names a clock time and a date, says the D-1 time stamp belongs to report D.</li>
<li><b>ABSENT record:</b> for cost, personnel, supervisor, weather, mud logging when the archive has no such field. It lists what was searched and near misses it rejected.</li></ul></div>
<div>
<ul style="font-size:14.5px"><li><b>NOTE-DISCREPANCY:</b> shown only when the question mentions a field where XML and PDF disagree.</li>
<li><b>Aggregates:</b> for multi-report and archive-wide questions that ask for a count, extreme or comparison, code computes count, min, max and the source records. Aggregate lines get IDs like <code>AGG-00000000-WATERDEPTH</code>. A citation to one is replaced by its source records.</li>
<li><b>Archive index:</b> <code>IDX-00000000-WELLBORES</code> lists wellbores, reports per wellbore and date ranges.</li>
<li><b>ABSENT-search:</b> if none of the question's content words occurs in any field name or record text, an ABSENT record says what was searched.</li></ul>
<div class="card abs"><h2>What it prevents</h2><p class="muted" style="font-size:14.5px">The model counting by hand across 32 reports, or reading a D-1 time stamp as a date mismatch. Code does the counting and the model reads the result.</p></div></div></div>
''', "Sources: submission/archive_qa/context.py (build_context, window_note), enrich.py (aggregates, ABSENT-search); GET /questions/T2-016 trace (est_tokens 181, 4 lines); submission/DATA_NOTES.md."))

# 10 model contract
PAGES.append(S("Stage 6 · The model contract", "A short prompt, a strict shape, fixed settings", '''
<div class="cols2"><div>
<pre>Answer the question using ONLY the evidence lines.
Reply with JSON only:
{"status":"answered"|"partial"|"abstain",
 "answer":str,"cited_ids":[str],"rationale":str}
Rules: cite the IDs of the lines you used; never invent
an ID; include units; if the lines do not contain the
information, status "abstain" with empty answer; if only
part of the question is supported, status "partial" and
answer that part only; never substitute a different
field for the one asked. rationale: one short sentence.
Record IDs carry the report date; a sample/event
timestamp may fall on the day before the report date
and still belongs to that report ...</pre>
<p class="faint" style="font-size:12.5px">About 250 tokens. The prompt's SHA is part of every cache key. Editing it invalidates the cache on purpose.</p></div>
<div><table><tr><th>Setting</th><th>Value</th></tr>
<tr><td>Primary model</td><td>anthropic/claude-haiku-5.5, temperature 0</td></tr>
<tr><td>Escalation model</td><td>anthropic/claude-sonnet-5.5, reasoning minimal</td></tr>
<tr><td>Output cap</td><td>400 tokens (3,000 for multi-report); retry at 1,500 if cut off</td></tr>
<tr><td>Format</td><td>strict json_schema, four fields</td></tr>
<tr><td>Provider</td><td>pinned to Anthropic, no fallbacks, require_parameters off</td></tr>
<tr><td>Runs</td><td>two Haiku runs per question; the second only feeds a disagreement flag</td></tr>
<tr><td>Concurrency, budget</td><td>8 workers, $3.00 spend guard per run</td></tr></table>
<div class="card flag" style="margin-top:10px"><h2>What it prevents</h2><p class="muted" style="font-size:14px">Free-form answers that cannot be checked, and the model deciding its own confidence.</p></div></div></div>
''', "Sources: submission/archive_qa/prompts.py; submission/archive_qa/config.py; submission/indexes/llm_cache.json (_meta: models, settings, prompt_sha 1628ad33a872932a); .env.example."))

# 11 verifier
PAGES.append(S("Stage 7 · The verifier", "Thirteen checks, all in code", '''
<div class="cols2"><div>
<table><tr><th>#</th><th>Check</th><th>In plain words</th></tr>
<tr><td>1</td><td>valid_json</td><td>The reply parses and has the four keys</td></tr>
<tr><td>2</td><td>status_valid</td><td>answered, partial or abstain</td></tr>
<tr><td>3</td><td>answer_nonempty</td><td>An answer has text</td></tr>
<tr><td>4</td><td>citations_well_formed</td><td>cited_ids is a list of strings</td></tr>
<tr><td>5</td><td>citations_in_context</td><td>Every cited ID was shown to the model</td></tr>
<tr><td>6</td><td>citation_required</td><td>An answer cites at least one record</td></tr>
<tr><td>7</td><td>abstain_citations</td><td>An abstention cites only ABSENT records</td></tr></table></div>
<div><table><tr><th>#</th><th>Check</th><th>In plain words</th></tr>
<tr><td>8</td><td>numbers_supported</td><td>Every number is in a cited record</td></tr>
<tr><td>9</td><td>units_match</td><td>The unit next to a number matches the record</td></tr>
<tr><td>10</td><td>dates_times_supported</td><td>Every date and time is in a cited record, its window or the question</td></tr>
<tr><td>11</td><td>no_false_not_found</td><td>No "nothing found" for a well that has a matching record</td></tr>
<tr><td>12</td><td>parts_addressed</td><td>Each part of a multi-part question is answered</td></tr>
<tr><td>13</td><td>no_missed_evidence</td><td>An abstention is not contradicted by a matching line</td></tr></table>
<p class="muted" style="font-size:13.5px;margin-top:8px">Details: dates and times are whole tokens, not digits. A derived number (sum, difference, mean) passes only if the answer says it is derived and both operands are cited and stated. Decimal commas, list numbers "(1)", short IDs like "ACT-13" and "24:00" are handled so correct answers are not rejected.</p></div></div>
<div class="card ok" style="margin-top:8px"><b>What it prevents:</b> <span class="muted">a wrong number that sounds right, a citation to a record the model never saw, and an abstention when the line was in the context. Failures go back to the model as feedback. They are never silently fixed.</span></div>
''', "Sources: submission/archive_qa/verify.py (verify, module docstring); check names from GET /questions/T2-017 trace (verifier[].checks)."))

# 12 escalation, arbitration, second pass, repair
PAGES.append(S("Stage 8 · Escalation, arbitration, second pass", "What happens when the first answer is not good enough", '<img class="dia" src="DIA/trust_layer.png" style="margin-bottom:10px">' + '''
<div class="cols4" style="font-size:13px">
<div class="card flag"><b>Escalate.</b> Verifier failed, or the model abstained although a matching line exists: one Sonnet 5.5 call that sees the verifier's message. Never escalates for a plain "no field" abstention.</div>
<div class="card flag"><b>Arbitrate.</b> The two Haiku runs disagree on status or key numbers: Sonnet decides. If it fails the checks, one retry with the message, then run 1 is kept and flagged.</div>
<div class="card route"><b>Second pass.</b> Multi-report or archive-wide only, once: the first pass abstained, was partial or tripped the abstain flag. Retry with aggregates, a field catalogue and full records of the named wells.</div>
<div class="card ok"><b>Citation repair.</b> Adds records whose content the answer clearly uses, and checks the answer still verifies. A partial answer is escalated once.</div></div>
''', "Sources: submission/archive_qa/answer.py (_answer_question), repair.py; diagram docs/presentation/diagrams/trust_layer.svg. Second pass real-data test: session run, not committed [VERIFY]: 5 of 5 abstain or partial cases rescued."))

# 13 cache, hybrid, writer, confidence
PAGES.append(S("Stage 9 · Answer cache and writer", "Same answers every run, with or without a key", '''
<div class="cols2"><div>
<div class="card ok" style="margin-bottom:10px"><h2>Answer cache</h2>
<p class="muted" style="font-size:14.5px">Key = sha256 of system prompt, context, question text, feedback, model, settings, prompt SHA and run label (length-prefixed). The file <code>submission/indexes/llm_cache.json</code> holds 130 entries (119 KB) and records the models and settings, so an offline replay rebuilds the same keys with no configuration.</p></div>
<table><tr><th>Situation</th><th>Result</th></tr>
<tr><td>Cached, any key state</td><td>answer from the cache, no network</td></tr>
<tr><td>Not cached, key present</td><td>model called; new answer saved to the runtime cache only</td></tr>
<tr><td>Not cached, no key</td><td>row "NOT EVALUATED: no API key and no cached answer", confidence 0, empty evidence</td></tr></table></div>
<div><div class="card brand" style="margin-bottom:10px"><h2>Writer</h2>
<p class="muted" style="font-size:14.5px">Writes <code>predictions.csv</code> (question_id, answer, evidence, confidence, notes). Evidence is built <b>only from records in the store</b>: unknown IDs are dropped. Per report, PDF page references first, then XML IDs; XML-only values are cited as such; abstentions list the files searched.</p></div>
<table><tr><th>Confidence rule</th><th class="n">Value</th></tr>
<tr><td>One verified record (single report)</td><td class="n">0.95</td></tr><tr><td>Two or three records</td><td class="n">0.80</td></tr><tr><td>Four or more records</td><td class="n">0.70</td></tr>
<tr><td>Partial</td><td class="n">0.40 to 0.60</td></tr><tr><td>Abstain, field not in archive</td><td class="n">0.85</td></tr><tr><td>Abstain, report does not exist</td><td class="n">0.90</td></tr><tr><td>Verifier failed</td><td class="n">0.20</td></tr></table></div></div>
''', "Sources: submission/archive_qa/llm.py (cache_key, LayeredCache), write.py, verify.py (confidence); submission/indexes/llm_cache.json; submission/README.md (hybrid mode)."))
