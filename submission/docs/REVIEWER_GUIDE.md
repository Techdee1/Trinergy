# Reviewer guide: Intelligent Well Archive (Track 2)

Team Trinergy. NAPE AICE 2026, Track 2. Data: Equinor Volve dataset.
This guide is for an outside reviewer who wants to rerun the work, check it, and understand what it does and does not do. Short sentences, plain words. Terms are explained where they first appear. For the design see [ARCHITECTURE.md](ARCHITECTURE.md). For data findings see [../DATA_NOTES.md](../DATA_NOTES.md).

## 1. Quick start (three commands)

You need the organiser's Track 2 data (see "Where the data comes from" below) and the conda environment.

```bash
conda env create -f environment.yml                      # once; creates the "nape" environment
conda activate nape && python -m ipykernel install --user --name nape --display-name "Python (nape)"
jupyter lab submission/solution.ipynb                    # choose the "Python (nape)" kernel, then Run All
```

**With no API key (the default for reviewers).** Run all cells. The notebook answers the 32 published questions from the committed cache `submission/indexes/llm_cache.json`. No network is used. It rewrites `submission/predictions.csv` with identical content (md5 `90717d3e7767eee3f53b739bb32923fc`). Measured on a clean clone on 2026-11-08: about 14 seconds from a fresh kernel (about 10 seconds of compute).

**With your own API key.** Put one line in a `.env` file at the repository root (copy `.env.example`; spaces around `=` are fine), or set an environment variable:

```
OPENROUTER_KEY=<your key>
```

The canonical name is `OPENROUTER_KEY`. Accepted aliases, checked in this order: `OPENROUTER_API_KEY`, `OpenRouter_Key`, `openrouter_api_key`. The first cell of the notebook prints which variable it found, never its value. With no key it prints `no key found: live mode off, using cached answers`.

**Where the data comes from.** The data root is the first of these that contains `metadata/document_manifest.csv`: `$NAPE_DATA_ROOT`, `./data/track_2`, `../data/track_2`, `../../data/track_2`, `../nape-aice-2026-hackathon/data/track_2`, `external/nape-aice-2026-hackathon/data/track_2`. Raw data is never committed. If none is found, the error lists every path tried (see [../README.md](../README.md), Data).

## 2. What the notebook does, cell by cell

The notebook is `submission/solution.ipynb`. Numbers below are from the no-key clean-clone run.

| Cell | What it does | Expected output |
|---|---|---|
| 1 | Key status | `no key found: live mode off, using cached answers`, or `API key found in variable <NAME> (value never shown)` |
| 2 | Imports and two settings: `QUESTIONS_CSV`, `OUTPUT_PATH` (both default to None) | none |
| 4 | Config check | 32 XML reports, 32 PDF reports, and the model settings (names and flags only, never the key) |
| 6 | Load or build the evidence store | `1783 records, 32 reports`; PDF-locator statistics |
| 8 | Read and route the questions | `single_report 24, multi_report 7, archive_wide 1 | early abstentions: 2` |
| 10 | Answer and verify | `answered 24, abstain 8`, `every question was evaluated`, then a status table |
| 12 | Write the predictions file and validate it | `rows: 32`, `validator: organiser validate_submission.py`, `valid: True` |
| 14 | Cost summary | `live calls this run: 0, cache hits: 71, spent this run: $0.0000` |
| 16 | Human review queue | `0 answer(s) need human review` |
| 18 | Optional review pack (off by default) | none unless `BUILD_REVIEW = True` |

## 3. Running other questions

1. Make a CSV with one column of question ids and one of question text. Column names are found case-insensitively. Ids: `question_id`, `id`, `qid`, `question_no`. Text: `question_text`, `question`, `text`, `prompt`, `query`. Quote any text that contains commas.
2. In cell 2 set `QUESTIONS_CSV = "path/to/your_questions.csv"` (relative to `submission/`, or absolute). You can also set the environment variable `NAPE_QUESTIONS_CSV`.
3. Run cell 2 and the cells below it.
4. The output goes to `submission/predictions_<your file name>.csv`. It never overwrites the committed `predictions.csv` unless you set `OUTPUT_PATH` to that file on purpose (environment variable `NAPE_OUTPUT_PATH`). The notebook validates the output against the organiser's format.

An example input file is [`submission/docs/demo_questions.csv`](demo_questions.csv).

## 4. How reproducibility works

- **Cache.** Every model answer is stored with a key. The key is a sha256 over the system prompt, the evidence context, the question text, any feedback, the model, the settings, the prompt hash and a run label. The file also records the models and settings, so an offline replay rebuilds the same keys with no configuration. It holds 130 entries.
- **Question text is part of the key.** If a question changes, its key changes, and it misses instead of returning a stale answer.
- **Hybrid mode.** Cache first, always. If a question is not cached and a key exists, the model is called and the new answer is saved to `submission/indexes/llm_cache_runtime.json` (git-ignored). The committed cache is never modified by a notebook run.
- **No key and not cached.** The row reads `NOT EVALUATED: no API key and no cached answer`, evidence is empty, confidence is 0. A summary at the end of the cell lists these. Nothing is guessed.
- **If the pinned provider is unavailable.** Requests are pinned to the Anthropic provider. If that is not available for your key, the run falls back to OpenRouter's default routing for the same model and logs a warning. Missing optional settings never stop a run.
- **Why a cache at all.** Models are not bit-identical even at temperature 0. The cache is what makes the rerun identical.

## 5. Output format and confidence

`predictions.csv` has five columns: `question_id`, `answer`, `evidence`, `confidence`, `notes`.

| Situation | Confidence |
|---|---|
| One verified record, single report | 0.95 |
| One verified record, multi-report or archive-wide | 0.90 |
| Two or three records | 0.80 |
| Four or more records | 0.70 |
| Truncated context | minus 0.05 |
| Partial answer | 0.40 to 0.60 |
| Abstain, field not in the archive | 0.85 |
| Abstain, report does not exist (no model call) | 0.90 |
| Abstain, other | 0.75 |
| Verifier failed | 0.20 |
| NOT EVALUATED | 0 |

Confidence is set by these rules in `submission/archive_qa/verify.py` (function `confidence`). The model never sets it.

## 6. Evidence and page references

The evidence string is built by code, from records in the store only. An ID that is not in the store is dropped, never printed.

```
15_9_F_1_C_2014_03_26.pdf p.1 (Drilling Fluid); 15_9_F_1_C_2014_03_26.xml F1C-20140326-FLUID-01
```

Read it as: PDF file, page, section heading; then XML file and record ID. Record IDs have the form well code, report date, record type, then a field name or number (for example `F15D-20150810-ACT-01`).

**XML-only fields.** Some values are in the XML but the PDF never prints them (NPD numbers, rig code, wellhead elevation, hole-section start, `fixedRig`, pre-spud date, `mudClass`, BOP rating, bit grading and nozzles, and others). They are cited as `XML only: <field>; not printed in the PDF`, with no page. For abstentions the evidence names the files searched, for example `15_9_F_15_D_2015_08_10.pdf: all sections checked, no cost field`.

**Page location accuracy** (from `DATA_NOTES.md`): 99.2 percent of table-row and narrative records are located to the exact row; 94.5 percent of the records the PDF prints; 78.8 percent of all records.

## 7. The verifier

A model answer is accepted only if all 13 checks pass. A failure goes back to the model as a message. It is never silently fixed. Code: `submission/archive_qa/verify.py`.

1. `valid_json`: the reply parses and has the four keys.
2. `status_valid`: status is answered, partial or abstain.
3. `answer_nonempty`: an answer has text.
4. `citations_well_formed`: `cited_ids` is a list of strings.
5. `citations_in_context`: every cited ID was in the evidence the model was shown.
6. `citation_required`: an answer cites at least one record.
7. `abstain_citations`: an abstention cites only ABSENT records.
8. `numbers_supported`: every number appears in a cited record. A derived number (sum, difference, mean) passes only if the answer says it is derived and both operands are cited and stated.
9. `units_match`: the unit next to a number matches the cited record.
10. `dates_times_supported`: every date and time appears in a cited record, its report window or the question. Dates and times are whole tokens, not digits.
11. `no_false_not_found`: no "nothing found" claim for a well whose context holds a matching record.
12. `parts_addressed`: each part of a multi-part question is answered.
13. `no_missed_evidence`: an abstention is not contradicted by a matching evidence line.

What happens next: if check 1 to 12 fail, or an abstention is contradicted, one Sonnet 5.5 call sees the verifier's message. If the two Haiku runs disagree on status or key numbers, Sonnet arbitrates (one retry). For multi-report questions, a first pass that abstains or is partial gets one second pass with an enriched context (computed aggregates, a field catalogue, full records of the named wells). After that, citation repair adds records whose content the answer clearly uses. If an answer still fails, it is kept, flagged for review, and given confidence 0.20.

## 8. Data traps handled

| Trap | Handling |
|---|---|
| A report dated D covers D-1 to D | Each record carries its window. A WINDOW NOTE tells the model the D-1 time stamp belongs to report D. |
| 15/9-19-A report dated 1980-01-01 is a placeholder (1997 spud date, no text) | Still cited: its kick-off depth is printed on PDF page 1. |
| Same-date reports (F-1-B and F-1-C, 2014-02-22) | Filter by well, then by date. |
| Well-name variants (`15/9-F-11 B`, `F-11B`, `F-11-T2`, XML `NO 15/9-F-1 C`) | One canonical name; tested spellings; each date paired with its own well. |
| `-999.99` and the text `None` | Missing, never values. |
| No report for 15/9-F-14; none for F-15-D on 2013-12-15 | Early abstain, no model call. |
| Western Atlas (company name) | A wireline logging company, not mud logging. The mud-logging question abstains. |
| Fields the archive lacks (cost, personnel, supervisor, weather, mud logging) | ABSENT record says what was searched; the answer abstains. |

## 9. XML versus PDF findings

The XML is authoritative. Verified findings (see `DATA_NOTES.md`, XML vs PDF audit):

- Tight well and HPHT: the PDF prints `Y` in all 32 reports; the XML has `0` in all 32. The locator never gives these a PDF location.
- Days ahead and behind: the PDF is blank in the 11 reports where the XML has `daysBehind`.
- Bit table: the PDF bit-run end depth is 2574 where the XML `mdHoleStop` is 2577 (report `15_9_F_11_T2_2013_04_28`).
- Fluid samples: the PDF sorts them by time of day; the XML is in report order.

Derived NOTE records (64 flag fields, 11 days-behind, 1 bit end depth) are stored at build time and shown to the model only when the question mentions that field.

## 10. Cost and model settings

| Item | Value | Source |
|---|---|---|
| Primary model | `anthropic/claude-haiku-5.5`, temperature 0 | `submission/archive_qa/config.py` |
| Escalation model | `anthropic/claude-sonnet-5.5`, reasoning `minimal` | same |
| Output caps | 400 tokens; 3,000 for multi-report; retry at 1,500 | same |
| Provider | pinned to Anthropic, no fallbacks, `require_parameters` off | same |
| Spend guard | `LLM_BUDGET_USD` 3.00 per run | same |
| 32 questions, cached | 130 calls, $0.651, about $0.022 per question | `submission/indexes/cost_summary.csv` (written by the notebook run) |
| Model split | Haiku 104 calls, 12.7 percent of cost; Sonnet 26 calls, 87.3 percent | `GET /costs` ([../../web/server/API.md](../../web/server/API.md)) |

All settings can be overridden with `LLM_*` environment variables; see `.env.example` and the table in [../README.md](../README.md).

## 11. File map

```
environment.yml, pytest.ini, CLAUDE.md          environment, test config, project rules
submission/
  solution.ipynb                                the notebook the reviewers run
  predictions.csv                               the committed predictions (32 rows)
  README.md, DATA_NOTES.md                      setup; data findings and limits
  requirements.txt                              pinned libraries
  archive_qa/                                   the pipeline
    config.py wells.py parse.py locate.py store.py     data, parser, page locator, evidence store
    route.py context.py enrich.py match.py             router, context builder, aggregates
    prompts.py llm.py answer.py                        prompt, model client and cache, answer loop
    verify.py repair.py discrepancy.py xmlonly.py      verifier, citation repair, XML-PDF notes
    write.py pipeline.py                               predictions writer, question-file handling
  indexes/llm_cache.json                        committed answer cache (130 entries)
  indexes/records.parquet                       evidence store, rebuilt by the notebook (git-ignored)
  eval/                                         evaluation tools; eval/generalisation = 40 unseen questions
  docs/                                         this guide and ARCHITECTURE.md
tests/                                          pipeline tests (345 pass, 1 skipped)
web/server/                                     optional backend API (99 tests)
web/app/                                        optional dashboard (React + TypeScript)
```

## 12. Testing

```bash
conda activate nape
python -m pytest -q                              # pipeline: 345 passed, 1 skipped (about 30 s)
python -m pytest web/server/tests -q             # API: 99 passed (about 97 s); run in its own session
```

Tests that matter most for a reviewer: `tests/test_generalise.py` asserts that the 32 questions route and build contexts exactly as before, that with no key and no `.env` the 32 reproduce a byte-identical `predictions.csv` with no network socket opened, and that a changed question misses the cache. Tests that need the organiser data skip if it is not found (set `NAPE_DATA_ROOT`).

## 13. Known limitations

- One field, 32 reports. Scale is not tested.
- No scanned documents. Every PDF page here has a text layer; OCR is not built.
- No cost, personnel, supervisor or weather fields exist in the archive, so those questions abstain.
- The 40 unseen questions went from 31 to 40 correct after fixes made while looking at the failures. That is a tuned result, not a blind test.
- The petroleum engineer's hand check of the 32 answers (`submission/eval/key_template.csv`) and an independent test are pending. The hidden-test score is unknown.
- The verifier checks that facts are supported, not that the right field was chosen. A right number from a wrong field can pass.
- The page locator reaches 78.8 percent of all records; the rest are cited from the XML only.

## 14. The optional dashboard

A React and TypeScript dashboard and a FastAPI backend sit on top of the same pipeline. You do not need them to run or review the submission.

- **What it is:** answer view with the PDF page and highlight boxes, a replay of the real trace, a 3D view, the 72-question board, generalisation, cost, and an Ask box.
- **Code and guides:** backend in `web/server/` (API guide: [web/server/API.md](../../web/server/API.md)); dashboard in `web/app/` ([web/app/README.md](../../web/app/README.md)); deployment in [web/DEPLOY.md](../../web/DEPLOY.md).
- **Run it locally:** `uvicorn web.server.app:app --port 8000` from the repository root, then in `web/app` run `npx vite preview --port 5173` and open `http://localhost:5173/?api=http://localhost:8000`.
- **Hosted link:** none yet. The repository deploys nothing by itself; see [web/DEPLOY.md](../../web/DEPLOY.md) to deploy.
