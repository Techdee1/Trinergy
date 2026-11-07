# Intelligent Well Archive – backend API

Local FastAPI service over the frozen `submission/archive_qa` pipeline. Interactive OpenAPI: `GET /docs` (JSON: `/openapi.json`).
Trimmed real responses are in [samples/](samples/); the full trace of T2-017 is `samples/T2-017.json`.

```bash
conda activate nape
pip install -r web/server/requirements.txt          # fastapi, uvicorn (httpx for tests)
uvicorn web.server.app:app --port 8000               # run from the repo root
python -m pytest web/server/tests -q                 # no network unless a key is configured (see "Tests")
```

Everything works offline for the 32 challenge questions (and the 40 unseen ones, see "Data the server needs"). With
`OPENROUTER_KEY` (aliases as in the notebook; environment or `.env`) uncached questions are sent to the model.
**The key is never returned, logged or stored**: `/health` only says whether live mode is on.

## Configuration (environment)

| variable | default | meaning |
|---|---|---|
| `RUNTIME_CACHE_DIR` | `web/server/.runtime` | everything the server writes: runtime LLM cache, ledger, spend, page PNGs, saved `/ask` answers |
| `SERVER_BUDGET_USD` | `2.00` | cumulative live spend cap (persisted in `RUNTIME_CACHE_DIR/spend.json`, survives restarts) |
| `ALLOWED_ORIGINS` | `http://localhost:3000,http://localhost:5173` | CORS, comma separated |
| `RATE_LIMIT_PER_MIN` / `RATE_LIMIT_PER_DAY` | `6` / `40` | per client IP, applies to `POST /ask` and `/ask/stream` |
| `MAX_QUESTION_CHARS` | `400` | longer questions are rejected with 422 before any work |
| `ASK_TIMEOUT_S` | `120` | request timeout for `/ask` and `/ask/stream` |
| `MAX_CONCURRENT_ASKS` | `4` | simultaneous questions in flight |
| `TRUST_PROXY` | `0` | `1` = take the client IP from `X-Forwarded-For` (set only behind a trusted proxy) |
| `TRAJECTORY_MIN_STATIONS` | `3` | wellbores with fewer usable survey stations are `skipped` |
| `WARM_ON_START` | `1` | replay the 72 catalog questions in the background at start (≈10 s, offline, free) |

Model names, token caps, reasoning and provider pin are the pipeline's own (`LLM_MODEL_PRIMARY`, …, see `submission/README.md`).

## Errors

Every error body is `{"detail": {"code": "...", "message": "...", ...}}`.

| status | code | when |
|---|---|---|
| 404 | `unknown_question` / `unknown_record` | no such id |
| 404 | `xml_only` | `/pages/...` for a record whose value is not printed in the PDF (message says why; `xml_file` given) |
| 404 | `pdf_unavailable` | the PDF is not on this server |
| 422 | `validation_error` / `question_too_long` / `question_empty` | bad body |
| 429 | `rate_limited` | `Retry-After` header in seconds |
| 503 | `budget_exhausted` | `SERVER_BUDGET_USD` used up **and** the question has no cached answer (cached questions are still answered) |
| 504 | `timeout` | `ASK_TIMEOUT_S` exceeded |

## Endpoints

### `GET /health` → `Health`
`{status, live_mode, models:{primary, escalation}, version, budget_remaining_usd, details}`. `live_mode` = a key exists **and** budget remains.
`details`: counts, `warm_seconds`, `provider_fallback_active`, limits, `key_configured` (boolean only).

### `GET /questions[?set=challenge|unseen]`
`{count, sets:{challenge:32, unseen:40}, questions:[{id, set, question, status, confidence, flags, router_mode}]}`.
`status`: `answered | partial | abstain | not_evaluated`. `flags` (sorted, any of): `early_abstain`, `router_unmapped`, `not_evaluated`,
`verifier_failed`, `runs_disagree`, `needs_review`, `low_confidence`, `second_pass`, `escalated`, `arbitrated`, `d1_fallback`,
`context_truncated`, `xml_only_evidence`, `provider_fallback`. Statuses come from an offline replay of the caches (never spends).

### `GET /questions/{id}` → `QuestionDetail`
Also accepts `ASK-xxxxxxxx` ids returned by `/ask`. See "QuestionDetail" and "Trace" below.

### `GET /pages/{record_id}.png[?zoom=1.5&highlight=true]` · `GET /pages/{record_id}/boxes`
The PDF page that holds the record, evidence highlighted (PyMuPDF; cached under `RUNTIME_CACHE_DIR/pages`; the PDF is never modified).
`/boxes` returns `{record_id, pdf_file, page, section, locator_match, xml_file, page_width, page_height, match, boxes:[{x0,y0,x1,y1,nx0,ny0,nx1,ny1}], png_url, note}`;
coordinates are PDF points from the top-left, `n*` are fractions of the page. `match` = what was highlighted: `row` (whole table row),
`value`, `label`, `heading` (only the section heading could be found) – never `none` for a located record (tested on all 1,700+).
XML-only evidence has **no page**: HTTP 404 `xml_only`. A cited record carries `evidence.page_url = null` in that case, so a client can decide
without trying.

### `GET /archive`
`{wells:[{well, wellbores, reports}], wellbores:[{wellbore, well, reports, first_report, last_report}],
reports:[{file, pdf_file, well, wellbore, date, period_start, period_end, pages, records}], record_counts:{by_type, total, derived_notes}}`.
*wellbore* is the pipeline's canonical name (`15/9-F-1-C`); *well* is the parent slot (`15/9-F-1`), both derived from the file names.
`derived_notes` are XML-vs-PDF discrepancy records computed at build time, not archive records.

### `GET /trajectories`
Per wellbore survey stations with **minimum-curvature** `x` (east), `y` (north), `tvd`, all flagged `approximate` (top level and per wellbore),
plus `caveats`. Stations are those printed in the daily reports (duplicates by measured depth ignored, a station with a missing md/inclination/azimuth
is dropped – `-999.99` is never a value). `x`,`y` start at 0 at the first station; `tvd` starts at its reported TVD.
`max_tvd_difference_m` compares the computed TVD with the archive's (≤ 0.1 m for every wellbore here, which is a check of the method).
A wellbore with fewer than `TRAJECTORY_MIN_STATIONS` usable stations has `status: "skipped"`, an empty `stations` list and a `reason`
(15/9-F-1: all 7 stations lack an azimuth).

### `GET /costs`
`ledger` (committed `cost_summary.csv` total), `derived_from_cache` (recomputed from `llm_cache.json`; must match), `per_question`
(challenge, unseen, ad-hoc), `model_mix` (+ `by_role`), `other_caches` (generalisation, runtime), `cache_hit_rate`
(`asks` = this server's `/ask` traffic, `startup_replay` kept separate so replays cannot inflate it), `budget`.
Costs of cached calls are the cost *when generated*; `incurred` costs (what this server paid now) are in each trace.

### `GET /generalisation`
Read-only view of `submission/eval/generalisation` (`results.json`, `scores.json`, `expected.json`, baselines).
`{available, message, summary:{questions, mean_score, baseline_mean_score, by_category, status_counts, cost_usd, scoring}, questions:[…, score, baseline_score, detail_url]}`.
If the (git-ignored) outputs are missing: `{available:false, message:"…how to produce them…", summary:null, questions:[]}`.

### `POST /ask` `{question}` → `QuestionDetail`
The notebook's `answer_question` in hybrid mode: cache first (committed, then generalisation, then runtime), live model only for a miss and only
if a key exists and budget remains. New answers are written **only** to `RUNTIME_CACHE_DIR`. A question whose text equals a catalog question
returns that question's id and `set`; any other gets `id = ASK-<sha8>`, `set = "adhoc"`, and is saved so `GET /questions/{id}` returns it.

* No key and not cached → HTTP 200, `status: "not_evaluated"`, `answer: "NOT EVALUATED: …"`, `confidence: 0`, no citations, flag `not_evaluated`.
* The router names a well/date that does not exist → `abstain` with no model call (`early_abstain`).
* **Server gate**: the router maps the question to *no* well, date or topic **and** it has no cached answer → `abstain`, flag `router_unmapped`,
  `trace.router.gate`, no model call (otherwise the pipeline would send the whole archive to a model). A cached answer always wins over the gate.
* A model call that fails (HTTP error, …) → `not_evaluated` with the redacted reason in `trace.warnings`; never a guess.

### `POST /ask/stream` `{question}` → `text/event-stream`
Same rules and same final object. One SSE event per **real** stage, emitted when it happens (`event:` = stage, `id:` = seq,
`data:` = `StageEvent` JSON `{seq, stage, t_ms, data}`), then `result` (`data` = the full `QuestionDetail`) or `error` (`{code, message}`).
`: keepalive` comments every 10 s while a model call is running.

| stage | when | `data` |
|---|---|---|
| `route` | always first | `RouterTrace` |
| `gate` | server gate fired | `{gate, message}` |
| `context_built` | each context built (first pass, and second pass if it runs) | `ContextTrace` |
| `aggregates_added` | only if that context contains computed aggregates | `{pass_name, aggregates}` |
| `second_pass` | the pipeline decided to retry once with the enriched context | `{reason}` |
| `escalate` | **before** an escalation call (verifier rejection / partial answer) | `{trigger, model, context_pass, reason}` |
| `arbitrate` | **before** an arbitration call | `{retry, model, context_pass, reason}` |
| `model_call` | after every lookup/call | `ModelCall` |
| `verify` | after every verifier run | `VerifyTrace` |
| `warning` | e.g. provider fallback | `{code, message}` |
| `result` / `error` | last | full response / error |

The events in the stream are, in order and with equal payloads, the events in `trace.events` of the final response (the `result` stage inside the
trace is a short summary). Tests assert this for all 32 challenge questions and for live, escalated, early-abstain and not-evaluated runs.
Errors raised before the stream starts (422, 429) are ordinary HTTP errors. `budget_exhausted` can only be known at the end, so it arrives as an `error` event.

## QuestionDetail

`{id, set, question, status, answer, rationale, confidence, verified, flags, router_mode, source, evidence, cited_records, trace}`

* `confidence`: the pipeline's rule-based confidence (never from the model); 0 for `not_evaluated`.
* `source`: `cache` (every model call was a hit) · `live` · `mixed` · `none` (no model call: early abstain, gate, not evaluated).
* `evidence`: the `predictions.csv` evidence string, byte for byte.
* `cited_records[]`: `{id, type, text, report, well, report_date, evidence:{kind: pdf|xml_only|absent, label, pdf_file, page, section, xml_file, xml_only_paths, page_url, boxes_url}}`.
  `kind: "absent"` = an `ABSENT-*` pseudo-record (what was searched when the archive has no such field). Records the question is about but the PDF
  does not print (e.g. `tightWell`/HPHT, where the PDF prints Y and the XML says 0) are `xml_only`, label `XML only: …`.

## Trace

Shared by every endpoint. All of it is observed from the pipeline's real calls (see "How the trace is captured").

* `router`: `mode`, `confidence:{level, basis}` (**server-derived** from the router's output: high = every target resolved by exact date/range, medium = D+1
  fallback, partial match or well-only, low = whole archive / unmapped; the router has no score of its own), `reason` (verbatim), `wells_named`,
  `dates_named`, `date_range`, `topics`, `early_abstain`, `wells_considered[{well, in_archive, reports_available}]`,
  `reports_selected[{report, well, date, reason}]` (reason is derived from the selection rules in `route.py`), `unmatched[]`, `gate`.
* `contexts[]`: `pass_name` (`first_pass`/`second_pass`), `final` (the one the answer came from), `est_tokens`, `lines`, `truncated`, `notes`,
  `records[{id, type, report}]` (everything the model could cite), `aggregates[{id, text, sources}]`, `absent[{id, kind, reports_searched, records_searched, considered_and_rejected}]`.
* `model_calls[]`: `n, purpose, role, run, model, context_pass, outcome, cache_hit, prompt_tokens, completion_tokens, latency_ms, cost_usd, incurred_usd, finish_reason, max_tokens, reply_status, reply_cited, feedback, error`.
  `outcome`: `cache_hit` · `live` · `cache_miss_offline` (a lookup that missed with no way to call a model: no tokens, not a model call) · `budget_blocked` · `error`.
  `cost_usd`/tokens of a cache hit are those of the original generation; `incurred_usd` is what was charged now (0 for a hit).
* `verifier[]`: `n, target` (the model call checked, or `citation_repair` = the re-check after citations were repaired), `ok`, `checks[{name, label, result: pass|fail|flag|not_applicable, detail}]`, `failures`, `flags`, `flagged_ids`.
  The verifier returns messages, not a checklist; each message is mapped to a named check by its wording, so `pass` means "this check produced no message" and `other` collects anything unmapped.
* `retries` (calls that were same-model retries after truncation/invalid JSON), `escalations[{seq, kind, trigger, model, reason, call}]`,
  `second_pass{ran, reason, used_for_answer, outcome}`, `arbitration{ran, retried, calls, outcome}`.
* `cited{model_cited, final, aggregates_cited, absent_cited}`: `model_cited` = the ids in the reply the committed answer came from; `final` = the evidence ids
  (aggregates expanded to their source records; repaired citations included).
* `decisions[]`: the pipeline's own notes, verbatim (why it escalated, disagreement text, repairs, `VERIFIER FAILED: …`).
* `warnings[{code, message}]`: e.g. `provider_fallback` – the pinned Anthropic provider is unavailable for the key and OpenRouter's default routing was used for the same model (message redacted).
* `totals`: `model_calls, live_calls, cache_hits, prompt_tokens, completion_tokens, generation_cost_usd, incurred_cost_usd, model_latency_ms, wall_ms`.
* `events[]`: the stage events (see the stage table).

## Guarantees and how they are enforced

* **The submission is frozen.** Nothing in `submission/`, `tools/` or `.env` is edited and the pipeline gets no hook. `web/server/trace.py` observes it from outside:
  pass-through wrappers on the three module globals `answer.route_question / build_context / verify` (active only while a request's tracer is set, same
  arguments, same return value) and a proxy around the LLM object. Tests (`test_unchanged.py`): predictions regenerated through the traced path are byte
  identical to `predictions.csv`; every call of every challenge question is a hit in the committed cache (same keys) and the contexts equal the original builder's;
  hashes of `llm_cache.json`, `predictions.csv`, `answers.json`, `cost_summary.csv` and a snapshot of `submission/archive_qa`, `indexes/`, `solution.ipynb` are
  unchanged after live asks; `logs/cost_ledger.csv` is not touched either (the server keeps its own ledger in `RUNTIME_CACHE_DIR`).
* **Caches.** Read order: committed `llm_cache.json` → `submission/eval/generalisation/runtime_cache*.json` (read-only) → `RUNTIME_CACHE_DIR/llm_cache_runtime.json`; writes go to the last only.
  If `records.parquet` is missing it is built into `RUNTIME_CACHE_DIR`, not into `submission/`.
* **Secrets.** The key is read by the pipeline's own `llm.find_key`; every error message and log record is passed through a redactor that knows the key value and the `sk-or-…`/`Bearer …` shapes.
* **Abuse.** Length cap, per-IP rate limit, concurrency cap, timeout, persisted spend cap, CORS allow-list.

## Data the server needs

* The organiser data (XML and PDF) via the pipeline's `NAPE_DATA_ROOT` rules (PDFs are needed for `/pages` and `/archive` page counts).
* For the **40 unseen questions** to show their answers offline, the git-ignored files `submission/eval/generalisation/{runtime_cache.json, runtime_cache_second_pass.json}`
  (answers) and `{results.json, scores.json, expected.json}` (for `/generalisation`) must be present; otherwise those questions replay as `not_evaluated`
  (the 32 challenge questions only need the committed cache).

## Tests

`python -m pytest web/server/tests -q`. No network unless a key is configured: only `test_offscript.py` calls a model, and only when a key is found
(it prints the 20-question table and writes it to `RUNTIME_CACHE_DIR/offscript/table.md`; reruns replay from that cache for free). All other tests use
a scripted model double and a temporary runtime directory.
