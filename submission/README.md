# Track 2 — Intelligent Well Archive (work in progress)

Status: batches 1-2 done (evidence store and question router). Answering, evidence formatting and
`predictions.csv` generation come later. See [DATA_NOTES.md](DATA_NOTES.md) for data findings and limitations.

## Setup (conda, Python 3.12)

```bash
conda env create -f environment.yml     # from the repo root; creates env "nape"
conda activate nape
python -m ipykernel install --user --name nape --display-name "Python (nape)"
```

No API key and no network access are needed.

## Data

The Track 2 data root is the **first** of these that contains `metadata/document_manifest.csv`
(relative paths are relative to the current directory, like the organiser's starter notebook):

1. `$NAPE_DATA_ROOT`
2. `./data/track_2`
3. `../data/track_2`
4. `../../data/track_2`
5. `../nape-aice-2026-hackathon/data/track_2`
6. `external/nape-aice-2026-hackathon/data/track_2`
7. `<repo root>/external/nape-aice-2026-hackathon/data/track_2` (added so it also resolves when the
   notebook runs from `submission/`)

If none qualifies, a `FileNotFoundError` lists every path tried. Either run from a folder where one of the
above resolves (e.g. the organiser repo root) or set `NAPE_DATA_ROOT` to the folder containing `documents/`,
`metadata/` and `open_test/`. To fetch the data yourself:

```bash
git clone --depth 1 https://github.com/NAPE-Innovation/nape-aice-2026-hackathon external/nape-aice-2026-hackathon
```

The raw data is never committed. `submission/indexes/records.parquet` and `routing_report.csv` are
git-ignored; the notebook rebuilds them in seconds.

## Build the evidence store

```bash
python -c "from submission.archive_qa.store import build_store; build_store()"
```

Writes `submission/indexes/records.parquet` and prints record counts per report and per section and the
PDF-locator statistics. The build is deterministic and takes a few seconds.

## Run the router

```bash
python -c "from submission.archive_qa import route; r = route.route_all(); route.save_routing_report(r); print(r)"
```

Writes `submission/indexes/routing_report.csv`.

## Notebook

`submission/solution.ipynb` does all of the above top to bottom (config check, build or load store,
locator stats, routing report). Run it with the `nape` kernel.

## Tests

```bash
python -m pytest -q
```

## Limitations (so far)

See [DATA_NOTES.md](DATA_NOTES.md). Some question topics (cost, personnel, supervisor, weather) have no
field in the archive; the router does not abstain on topic, a later step decides that using `has_field`.

## LLM settings (only needed to regenerate the answer cache)

The notebook replays `indexes/llm_cache.json` offline, so reviewers need none of this. To regenerate it
(`LIVE = True`), set in `.env` or the environment (the API key goes in `OpenRouter_Key`, never in code):

| variable | meaning | default |
|---|---|---|
| `LLM_MODEL_PRIMARY`, `LLM_MODEL_ESCALATION`, `LLM_MODEL_FAST` | OpenRouter model ids | required (fast optional) |
| `LLM_MAX_TOKENS` | max output tokens per call | 1500 |
| `LLM_REASONING` | reasoning effort (`none`, `minimal`, `low`, `medium`, `high`, `xhigh`); sent only when set | unset |
| `LLM_BUDGET_USD` | spend guard per run | 3.00 |
| `LLM_CONCURRENCY` | parallel questions | 4 |

Model names, `max_tokens` and `reasoning` are recorded in the cache's `_meta`, so an offline replay rebuilds the
same cache keys without any of these variables.
