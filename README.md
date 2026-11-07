# Trinergy

Turning legacy well records (scanned well logs, core logs, technical reports) into structured digital data.

This repo is the foundation layer for the work: PDF ingest, image helpers, a provider-agnostic LLM call with caching and cost tracking, and a pipeline skeleton. The extraction logic for the actual task gets added once we have seen the real documents.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m ipykernel install --user --name nape --display-name "Python (nape)"
cp .env.example .env   # then fill in LLM_PROVIDER, LLM_API_KEY, LLM_MODEL and prices
source .venv/bin/activate
```

`LLM_PROVIDER` is one of `openai`, `gemini`, `anthropic`. Set `LLM_PRICE_INPUT_PER_1M` / `LLM_PRICE_OUTPUT_PER_1M` to the model's real prices, or the ledger will report $0.

## Layout

```
data/raw/      input PDFs (git-ignored)
data/pages/    rendered page PNGs: <pdf-stem>_<dpi>dpi/page_0001.png
data/cache/    LLM response cache, one JSON file per sha256 key
data/output/   pipeline outputs (pages.parquet manifest, results)
src/           config, ingest, image_utils, llm, cost, pipeline
notebooks/     01_explore.ipynb for looking at real documents
tests/         pytest suite (all LLM calls mocked)
cost_ledger.csv  one row per LLM call (git-ignored)
```

## Run

```bash
# Render pages and extract the text layer (no LLM calls yet)
python -m src.pipeline --input data/raw --limit 20
python -m src.pipeline --input data/raw/some_file.pdf --dpi 200

# Cost summary, and a projection for N items
python -m src.cost
python -m src.cost --project 5000 --calls-per-item 2

# Tests
python -m pytest -q
```

Calling the LLM from code:

```python
from src.llm import call_llm
from src import image_utils as iu

img = iu.downscale(iu.crop(iu.load(page.image_path), bbox), 1024)
result = call_llm("Return JSON with ...", image=img, max_output_tokens=300,
                  source=f"{pdf_name}:p{page.page_number}")
```

## Token cost strategy

- **Use the text layer first.** If a page has native text, send text, not pixels; only fall back to images for scans.
- **Send crops, not full pages.** Crop to the region of interest, convert to grayscale where colour doesn't matter, and downscale (`IMAGE_MAX_SIDE`) before calling the model.
- **Cache by hash.** Each response is stored under `sha256(prompt + image bytes + model)`, so the same call is never paid for twice, including on re-runs.
- **Keep output compact and structured.** Ask for small JSON objects with short keys, and set `max_output_tokens` per call.
- **Log every call.** Every call, cache hits included, is appended to `cost_ledger.csv` with its tokens and USD cost. `python -m src.cost` summarises the ledger and projects the cost of a full run from the measured average.
- **Trial with `--limit`.** Measure on a few pages before running everything.
