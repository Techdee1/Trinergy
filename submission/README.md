> **Reviewer documentation:** [Reviewer guide](docs/REVIEWER_GUIDE.md) (quick start, notebook cell by cell, other questions, reproducibility) and [Architecture](docs/ARCHITECTURE.md) (design, diagrams, API, deployment).

# Track 2 — Intelligent Well Archive

## Quick start

1. Create the environment (below) and open `submission/solution.ipynb` with the `nape` kernel.
2. **Offline, no key:** run all cells. The 32 published questions are answered from the committed cache
   `indexes/llm_cache.json` and `predictions.csv` is reproduced byte for byte (about 10 seconds, no network).
3. **Your own key or your own questions:** put `OPENROUTER_KEY=<your key>` in a `.env` file (copy `.env.example`; spaces around
   `=` are fine) or set the `OPENROUTER_KEY` environment variable. `OPENROUTER_API_KEY`, `OpenRouter_Key` and
   `openrouter_api_key` are accepted as aliases. The notebook's first cell prints which variable it found (never its
   value), or `no key found: live mode off, using cached answers`.
4. For a different question set, set `QUESTIONS_CSV` in the second code cell (a CSV with an id column and a question column;
   names such as `question_id`/`id` and `question_text`/`question`/`text`/`prompt`, any letter case). `OUTPUT_PATH` defaults
   to `submission/predictions.csv` for the published questions and to a new `predictions_<file>.csv` for any other file, so a
   different run never overwrites the committed `predictions.csv` unless `OUTPUT_PATH` names it.

Behaviour is hybrid: a question already in the cache is answered from it, with or without a key; a question that is not
cached is sent to the model if a key exists, and otherwise gets a row with the answer `NOT EVALUATED: no API key and no
cached answer`, empty evidence and confidence 0 (a summary at the end of the run lists them). New answers are saved to
`indexes/llm_cache_runtime.json` (git-ignored); the committed cache is never modified by a notebook run. If the pinned
Anthropic provider is not available on your key, the run falls back to OpenRouter's default routing for the same model
and logs a warning.

See [DATA_NOTES.md](DATA_NOTES.md) for data findings and limitations.

## Setup (conda, Python 3.12)

```bash
conda env create -f environment.yml     # from the repo root; creates env "nape"
conda activate nape
python -m ipykernel install --user --name nape --display-name "Python (nape)"
```

No API key and no network access are needed for the 32 published questions.

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

The notebook replays `indexes/llm_cache.json` offline, so reviewers need none of this. To answer other questions, set in `.env`
or the environment (the API key goes in `OPENROUTER_KEY`, never in code). All values
below are the defaults in `archive_qa/config.py`; see `.env.example`.

| variable | meaning | default |
|---|---|---|
| `LLM_MODEL_PRIMARY`, `LLM_MODEL_ESCALATION`, `LLM_MODEL_FAST` | OpenRouter model ids | `anthropic/claude-haiku-5.5`, `anthropic/claude-sonnet-5.5`, unset |
| `LLM_MAX_TOKENS` | max output tokens, primary call on a `single_report` question | 400 |
| `LLM_MULTI_MAX_TOKENS` | max output tokens, primary call on a `multi_report` / `archive_wide` question | 3000 |
| `LLM_RETRY_MAX_TOKENS` | cap for the single primary retry after a truncated (`finish_reason=length`) or invalid-JSON reply | 1500 |
| `LLM_ESCALATION_MAX_TOKENS` | max output tokens for escalation and arbiter calls | 1500 |
| `LLM_REASONING`, `LLM_ESCALATION_REASONING` | reasoning effort (`none`, `minimal`, `low`, `medium`, `high`, `xhigh`); sent only when set | `none`, `minimal` |
| `LLM_PROVIDER` | provider pin (`provider.order`, no fallbacks, `require_parameters` off); empty = no pin | `Anthropic` |
| `LLM_BUDGET_USD` | spend guard per run | 3.00 |
| `LLM_CONCURRENCY` | parallel questions | 8 |

Model names, the token caps (`max_tokens`, `multi`, `retry`, `escalation`), `reasoning` and the provider pin are recorded
in the cache's `_meta`, so an offline replay rebuilds the same cache keys without any of these variables.
