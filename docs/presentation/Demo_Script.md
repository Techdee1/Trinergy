# Demo script: Intelligent Well Archive (legacy 10-minute version)

> **Use [Demo_5_Minute_Guide.md](./Demo_5_Minute_Guide.md) for the current presentation.**
> The live slot is now five minutes: one minute for the notebook and four minutes for the dashboard.
> The printable visual runbook is [Demo_5_Minute_Guide.pdf](./Demo_5_Minute_Guide.pdf).

Team Trinergy. Track 2. Built for Heirs Energies. Data: Equinor Volve dataset.

Speakers (confirm names and roles with the team [VERIFY]): **PE** petroleum engineer, **AIE** AI engineer, **PD** product designer.

| Time | Block | Speaker | Screen |
|---|---|---|---|
| 0:00 to 1:30 | Problem and Heirs | PE | Slide: the problem |
| 1:30 to 3:00 | Approach and architecture | AIE | Slide: Flow diagram (`diagrams/pipeline.png`) |
| 3:00 to 4:30 | **Live demo 1: the notebook** (1:30) | AIE | Jupyter, `submission/solution.ipynb` |
| 4:30 to 8:00 | **Live demo 2: the dashboard** (3:30) | PD, with PE on evidence | Browser, TODO-URL |
| 8:00 to 9:30 | Results, honest limits, value, roadmap | AIE, then PE | Slide: numbers and limits |
| 9:30 to 10:00 | Close and ask | PD | Slide: the ask |

Sources for every number: `docs/presentation/Flow_and_Architecture.pdf`, page 25 (cheat sheet).

---

## Pre-talk checklist (do this 60 minutes before)

- [ ] **Battery and power.** Laptop on charger. Disable sleep. Close chat and email.
- [ ] **Display.** Mirror to the projector. Resolution 1920x1080. Browser zoom 100 percent. Notebook font large (Jupyter: View, zoom in twice). Do not Disturb on.
- [ ] **Bookmarks.** One bookmark for the dashboard (TODO-URL). One for `http://localhost:5173/?api=http://localhost:8000` (the offline fallback). Both in the bookmarks bar.
- [ ] **Key present but not visible.** `.env` at the repo root contains `OPENROUTER_KEY=...`. Do not open `.env` on screen. The first notebook cell prints only the variable name. Keep the key out of the browser URL and the clipboard history.
- [ ] **Warm the server (hosted).** Open TODO-URL/health until `warm_seconds` is not null, then open `/questions` once. Open the demo answers once: `#/question/T2-016`, `#/question/T2-032`, `#/question/T2-017`. The free Render plan sleeps after about 15 minutes idle and takes about a minute to wake. Use the Starter plan on the day (web/DEPLOY.md).
- [ ] **Run the smoke test:** `python web/server/smoke_remote.py TODO-URL --no-live` (no model call). Do not run `--rate-limit-test` right before presenting (web/DEPLOY.md).
- [ ] **Local fallback ready.** In two terminals, from the repo root: `conda activate nape`, then `uvicorn web.server.app:app --port 8000` and, in `web/app`, `npx vite preview --port 5173`. Check `http://localhost:5173/?api=http://localhost:8000` loads. Leave them running.
- [ ] **Notebook ready.** `conda activate nape`, `jupyter lab submission/solution.ipynb`, kernel "Python (nape)". Run once beforehand, then **Kernel, Restart Kernel and Clear Outputs**.
- [ ] **Demo file present.** `docs/presentation/demo_questions.csv` (3 questions). To show a live model call, delete `submission/indexes/llm_cache_runtime.json` first (it is git-ignored; it holds only runtime answers).
- [ ] **Hand check.** Water, clicker, a printed copy of this script and `QA_Prep.pdf`.

---

## 0:00 to 1:30. Problem and Heirs (PE)

**On screen:** the problem slide (page 2 of the Flow PDF).

**Say:**
"Decades of well history sit in daily drilling reports. When an engineer needs a casing depth or a mud weight, they search by hand. And when someone asks where that number came from, it is hard to show.

For Heirs there is another reason. Operators attest to the integrity of the data they submit. Every figure needs a source you can open.

So we built something different. You ask a question about the reports. You get the answer, and the page it came from. And if the archive does not contain the answer, it says so, and says what it searched. In this contest a correct 'not in the archive' scores a full point. An invented citation scores zero. We designed for that."

**Transition:** "My colleague will show how it works."

(Source for the regulatory wording: web/app/src/views/Impact.tsx. Confirm the NUPRC wording with Heirs [VERIFY].)

---

## 1:30 to 3:00. Approach and architecture (AIE)

**On screen:** `diagrams/pipeline.png` (page 4). Point left to right.

**Say:**
"Four principles. One: code finds the facts. We turn every report into small records with stable IDs, and code picks the records for each question. The model never searches the archive.

Two: the AI only phrases. A small model, Haiku 5.5, gets a handful of lines and writes a short answer in a fixed JSON shape.

Three: a verifier checks. Thirteen checks in code. A number, a date or an ID that is not in the cited records is rejected. If it fails, a bigger model, Sonnet, gets one try with the verifier's message.

Four: abstaining is a valid answer. If the archive has no such field, the answer says what was searched.

Everything is cached, so anyone can rerun it without a key and get the same file. Let me show that."

**Transition:** "This is the notebook the reviewers will run. I will run it with no setup."

---

## 3:00 to 4:30. Live demo 1: the notebook run (AIE, 1:30)

Fresh kernel, nothing run yet. Screen: Jupyter with `submission/solution.ipynb`. Cell numbers below are the notebook's cell indexes.

| Clock | Action | Point at | Say |
|---|---|---|---|
| 3:00 | Menu **Run, Run All Cells** (kernel was restarted). | | "Fresh kernel. Run all." |
| 3:05 | Cell 1 output | `API key found in variable OPENROUTER_KEY (value never shown)` (or, if you run without a key, `no key found: live mode off, using cached answers`) | "First cell says which key variable it found. The name, never the value. With no key it says it will use the cache." |
| 3:15 | Cell 4 output | `xml_reports: 32, pdf_reports: 32` | "32 reports, 32 PDFs." |
| 3:20 | Cell 6 output | `1783 records, 32 reports`; located 99.2% | "1,783 records. Each one is located on its PDF page." |
| 3:25 | Cell 8 output | `single_report 24, multi_report 7, archive_wide 1`, `early abstentions: 2` | "The router sends 24 questions to one report, 7 to several, one to the whole archive, and two to an early abstain because the report does not exist." |
| 3:35 | Cell 10 output | `answered 24, abstain 8`, `every question was evaluated` | "24 answered, 8 abstained. All of this in about 10 seconds, from the cache." |
| 3:50 | Cell 12 output | `validator: organiser validate_submission.py`, `valid: True` | "The organiser's own validator says valid. Same file, same checksum, every run." |
| 4:00 | Cell 14 output | `live calls this run: 0, cache hits: 71, spent this run: $0.0000` | "Zero live calls. Zero dollars. For the record, generating all 32 cost 65 cents: about 2 cents a question." |

**Reference output (a clean-clone, no-key run on 2026-11-08, about 14 seconds from a fresh kernel):** cell 1 `no key found: live mode off, using cached answers`; cell 8 `32 questions ... single_report 24, multi_report 7, archive_wide 1 | early abstentions: 2`; cell 10 `answered 24, abstain 8`; cell 12 `valid: True`; cell 14 `live calls this run: 0, cache hits: 71, spent this run: $0.0000`; cell 16 `0 answer(s) need human review`.

### The "other questions" moment (4:00 to 4:30)

**Say:** "And it is not only for our 32 questions. Give it a CSV of your own."

1. In cell 2, change one line:
   `QUESTIONS_CSV = "../docs/presentation/demo_questions.csv"`
   (the path is relative to the notebook folder `submission/`). Re-run from cell 2 downward (Run, Run Selected Cell and All Below).
2. The output file is **`submission/predictions_demo_questions.csv`**. It never touches the committed `predictions.csv`. The notebook prints this path in cell 8.
3. Point at cell 10: three questions, `answered 2, abstain 1`. Open the output file or show cell 12's table. Show **one evidence row**, DQ-1:

   `15_9_F_11_B_2013_05_29.pdf p.1 (Summary report); 15_9_F_11_B_2013_05_29.xml F11B-20130529-STATUS-MDCSGLAST`

**Say:** "Three unseen questions. A lookup in the F-11B report: 2570.7 metres, with the page and the XML ID. A comparison across two wells: 91 metres against 84. And a field the archive does not have, helicopter flights: it abstains and names what it searched."

**Recorded real run of the three demo questions (2026-11-08, cold runtime cache, key present):**

| Id | Question type | Answer | Confidence | Evidence |
|---|---|---|---|---|
| DQ-1 | single-report lookup | `2570.7 m MD (mdCsgLast)` | 0.95 | `15_9_F_11_B_2013_05_29.pdf p.1 (Summary report); ...xml F11B-20130529-STATUS-MDCSGLAST` |
| DQ-2 | comparison | `Well 15/9-F-1-B was in deeper water, at 91 m, versus 84 m for well 15/9-19 A.` | 0.80 | two PDF pages and two XML IDs (`...19A-19971110-STATUS-WATERDEPTH`, `...F1B-20130924-STATUS-WATERDEPTH`) |
| DQ-3 | field not in the archive | `Not answerable from the archive. No helicopter, flight field exists (searched 1 report(s), 61 record(s)). ...` | 0.85 | `15_9_F_1_B_2014_01_29.pdf: all sections checked, no helicopter, flight field` |

Timing and cost of that run: the whole notebook took **6.7 seconds** from a fresh kernel (nbconvert), **6 live model calls**, **$0.0027**. Answers are then saved in the git-ignored runtime cache, so a second run is free and instant.

If the key is missing or the network is down: the three rows show `NOT EVALUATED: no API key and no cached answer`. Say so calmly: "That is the honest behaviour: never a guess." Then move on.

**Transition:** "That was the engine. Now the way people will actually use it." (hand the laptop or screen to PD)

---

## 4:30 to 8:00. Live demo 2: the dashboard (PD with PE, 3:30)

The dashboard walk-through is written in **`web/app/docs/UI_Demo_Plan.md`** (minute by minute, with the Narrator and Driver roles, the words, and a 60-second fallback version). Keep its timing: **3:30**. This script only fixes the cue-in and cue-out. That plan starts from the Overview and expects the notebook run to have just ended.

**Cue in (PD):** "This is the same pipeline behind an API. Every screen is real data; nothing is mocked." Open the dashboard at TODO-URL.

**What the walk-through covers (from web/app/README.md, Views):** Overview, a question's answer view with the PDF page and highlight, the mission-control replay (2D, then 3D), the questions board, generalisation, cost, and Ask. The anchor questions in that plan are T2-016 (date window), T2-032 (the Western Atlas trap, an abstention) and T2-017 (multi-report with escalation). All are cached.

**Cue out (PD):** "Everything you saw can be rerun offline in the notebook. Back to the results."

**If the dashboard fails:** see Fallbacks below.

---

## 8:00 to 9:30. Results, honest limits, value, roadmap (AIE, then PE)

**On screen:** headline numbers (page 3) then limits (page 24).

**AIE says (0:50):**
"The numbers. 32 questions: 24 answered, 8 honest abstentions. All 32 cost 65 cents to generate. Running it again is free.

On 40 unseen questions we went from 31 correct to 40, by adding code that computes counts and comparisons, and by fixing one routing bug. I want to be straight about that: we fixed those after seeing the failures, so 40 of 40 is tuned, not a blind test. The engineer's hand check of the 32 and an independent test are still pending."

**PE says (0:40):**
"What it cannot do yet. It has seen 32 reports from one field. It has no scanned documents, because this archive has a text layer on every page. Cost, personnel and weather are not in the archive, so those questions abstain, correctly.

What we want next: a pilot on a small set of real Heirs daily reports, scored on your engineers' own questions. Then completion reports and well tests, with page evidence. We have not measured the time saved at Heirs yet. That is what the pilot is for."

**Transition:** "So, what do we want from you?"

---

## 9:30 to 10:00. Close and ask (PD)

**Say:**
"Every answer carries its proof, and when the archive does not know, it says so. We would like to run a pilot on real Heirs reports, and to agree where the model call may run. Thank you. We are happy to take questions."

**Stop.** Do not add more. Open `QA_Prep.pdf` if needed.

---

## Fallbacks (exact commands)

### The Wi-Fi fails
1. Switch to the bookmark `http://localhost:5173/?api=http://localhost:8000` (already running locally).
2. If it is not running, from the repo root:
   ```bash
   conda activate nape
   uvicorn web.server.app:app --port 8000          # terminal 1; offline for the 72 catalog questions
   cd web/app && npx vite preview --port 5173      # terminal 2; serves the committed dist/
   ```
3. The notebook needs no network without a key. New questions will show `NOT EVALUATED`; say that is the designed behaviour.

### The Render server is asleep or down
1. Do not retry in a loop (the rate limiter counts retries; web/DEPLOY.md).
2. Open the local fallback (above). The dashboard footer shows which API it uses (`set by ?api=`).
3. Say: "The hosted copy is waking up. This is the same code on the laptop."

### The 3D view fails
1. Press the 2D toggle in Mission control (3D is lazy-loaded and has a 2D fallback; web/app/README.md).
2. Or open `#/question/T2-017` and use the trace timeline.
3. In Focus mode press `F` to leave; `[` collapses the sidebar.

### The notebook fails
1. Run the same thing from a terminal and show the executed copy:
   ```bash
   cd submission
   jupyter nbconvert --to notebook --execute solution.ipynb --output /tmp/solution_run.ipynb
   jupyter lab /tmp/solution_run.ipynb
   ```
2. Or prove the reproduction directly:
   ```bash
   cd submission && md5sum predictions.csv        # 90717d3e7767eee3f53b739bb32923fc
   python -m pytest -q ../tests/test_generalise.py -k byte_identical
   ```
3. If a kernel is missing: `python -m ipykernel install --user --name nape --display-name "Python (nape)"`.

### A judge asks to try a question live
- Type it in the dashboard Ask view, or put it in a CSV and use `QUESTIONS_CSV`. A vague question gets a clarification and costs nothing. A new specific question costs a few cents and is bounded by the server budget and the key's own limit. If a limit is hit, say so: that is the guard working.

---

## Honest lines to keep ready

- "The 40 of 40 on unseen questions was tuned on those questions. We have not had a blind test yet."
- "The petroleum engineer's hand check of the 32 answers is pending."
- "We have not deployed inside Heirs and we have not measured time saved there."
- "No scanned documents in this archive. We have not built OCR."
