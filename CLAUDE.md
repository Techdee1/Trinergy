# Project rules

**Goal:** NAPE AICE 2026 Hackathon, Track 2 "Intelligent Well Archive". Answer 32 questions about Volve
daily drilling reports with traceable evidence (file, page, section), and abstain when the archive does
not support an answer. A correct abstention scores a full point; an invented citation scores zero.
Scoring: presentation 40%, predictions.csv 40%, reviewers rerun our notebook 20% (under 30 minutes, same
CSV, **no API key**).

## Layout
- `submission/` is what gets judged. `submission/archive_qa/`: `config` (DATA_ROOT, one place), `wells`
  (canonical well names, report discovery), `parse` (WITSML XML -> records), `locate` (record -> PDF page
  and heading), `store` (build/load, `has_field`), `route` (question -> candidate reports).
- `submission/indexes/` built artefacts. `submission/DATA_NOTES.md` data surprises. `tests/` pytest.
- `external/` organiser repo clone (git-ignored). Never commit raw data, `.env` or secrets.

## Rules
- Everything is derived from the archive. **No hard-coded answers** to any question, and no well list:
  known wells come from the report file names.
- A report dated D covers D-1 to D. The router uses exact date D; D+1 only as a recorded fallback.
  Filter by well before date.
- The XML is authoritative (e.g. tightWell/HPHT: the PDF prints Y, the XML says 0). `-999.99` is
  missing, never a value. The literal "None" in summary/forecast fields is missing.
- Never invent a citation. Use `has_field` to tell "the archive has no such field" from a retrieval miss.
- No LLM or network calls until the answering session; when added, tests must mock them.
- Don't add libraries beyond `submission/requirements.txt` without asking. Keep code simple.
- pandas gotcha: the records column `attrs` collides with `Series.attrs`; use `row["attrs"]`.

## Commands (conda env `nape`, Python 3.12)
```bash
conda activate nape
python -m pytest -q
python -c "from submission.archive_qa.store import build_store; build_store()"
python -c "from submission.archive_qa import route; r = route.route_all(); route.save_routing_report(r)"
```
