# Project rules

**Goal:** a hackathon project ("Unlocking Dormant Value from Legacy Well Records to Actionable Digital Intelligence"). We turn scanned PDFs (well logs, core logs, technical reports) into structured data. Judges score system design, reproducibility and **LLM token cost**.

## Layout
- `src/config.py`: settings from `.env`. Always call `get_settings()` and never hardcode paths or keys.
- `src/ingest.py`: PDF → PNG per page (PyMuPDF) plus the native text layer.
- `src/image_utils.py`: crop, grayscale, downscale, PNG bytes.
- `src/llm.py`: `call_llm()` is the **only** way to call an LLM. It is provider-agnostic (openai/gemini/anthropic), caches responses, logs costs and retries.
- `src/cost.py`: ledger summary and cost projection. `src/pipeline.py`: the CLI entry point.
- `data/{raw,pages,cache,output}`: git-ignored. `cost_ledger.csv`: git-ignored.
- `notebooks/`: exploration only. Reusable code belongs in `src/`.

## Token cost principles
1. Use the text layer first when a page has one; images are the fallback.
2. Send cropped, downscaled (and grayscale where possible) images, never full pages without a reason.
3. Every call goes through the cache (sha256 of prompt + image + model).
4. Ask for compact structured JSON output and set `max_output_tokens`.
5. Every call is logged in `cost_ledger.csv`; pass a meaningful `source=`.

## Rules
- **No real API calls in tests.** Mock `src.llm._call_provider` or `src.llm._get_client` (the conftest blocks real clients).
- Never create or commit a real `.env` or any secrets.
- Don't add libraries beyond `requirements.txt` without asking.
- Keep code simple and readable; avoid abstractions we don't need yet.
- Domain-specific logic (schemas, page types, ID formats) goes only where a `TODO(extraction)` marks it, and only after we've looked at real data.

## Commands
```bash
source .venv/bin/activate
python -m pytest -q
python -m src.pipeline --input data/raw --limit 5
python -m src.cost --project 1000
```
