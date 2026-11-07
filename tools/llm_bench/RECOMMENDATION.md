# LLM benchmark and recommendation (OpenRouter, evidence → JSON answer step)

Run date 2026-11-07. Everything here comes from `results/` (`calls.csv`, `summary.csv`, `projection.csv`, `ledger.csv`, `raw/`).

**Spend:** $0.6202 in total, 409 call rows, per `results/ledger.csv`. OpenRouter's own `/key` counter shows `usage = 0.62018698`, an exact match. The cap was $1.00. The key has a $15 per-key limit, and $14.38 remains.
That total includes about $0.23 for a first Anthropic grid with wrong routing settings (`grid_v0`, kept as evidence), about $0.01 of probes, and $0.002 for the tool test.

**Test set:** 16 cases built from the 32 XML reports (several are used per case as fillers). Expected values are computed by code. The cases average 15 evidence lines, from 6 to 40. Each model got one call per case (temperature 0, `max_tokens` 400).
Our own question templates were used, not the 32 official questions.

**Read this first, because the sample is tiny.**
One call per model per case means a 1/16 difference (6 percentage points) is not statistically meaningful. The data is good for finding failure patterns and for cost and latency. It is not good for ranking models that are within 1–2 cases of each other.

## 1. Results (compact prompt, 16 cases per model)

| Model | $/M in | $/M out | Avg in tok | Avg out tok | Reasoning tok | $/call | p50 s | max s | JSON valid | Status acc | Answer acc | Halluc. cites | Empty / length | Determinism (decision fields / raw text, 4 cases ×3) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| deepseek/deepseek-v4-flash | 0.091 | 0.182 | 1293 | 69 | 0 | 0.00012 | 1.28 | 2.71 | 100% | 100% | 87.5% | 0 | 0 / 0 | not run |
| openai/gpt-oss-120b | 0.016 | 0.059 | 1304 | 230 | 162 | 0.00013 | 0.82 | 3.32 | 100% | 100% | 87.5% | 0 | 0 / 0 | 3/4 · 0/4 |
| meta-llama/llama-4-scout | 0.10 | 0.30 | 1230 | 59 | 0 | 0.00021 | 2.82 | 6.95 | 100% | 69% | 56% | 0 | 0 / 0 | not run |
| **anthropic/claude-haiku-5.5** | 0.10 | 0.50 | 2020 | 112 | 0 | 0.00026 | 1.21 | 1.71 | 100% | 100% | **100%** | 0 | 0 / 0 | **4/4** · 0/4 |
| qwen/qwen3.7-plus | 0.32 | 1.28 | 1532 | 99 | 0 | 0.00062 | 2.70 | 5.19 | 100% | 88% | 75% | 0 | 0 / 0 | not run |
| google/gemini-3-flash-preview | 0.50 | 3.00 | 1671 | 82 | 0 | 0.00108 | 1.34 | 3.69 | 100% | 94% | 94% | 0 | 0 / 0 | 4/4 · 1/4 |
| anthropic/claude-sonnet-5.5 | 2.00 | 10.00 | 2021 | 124 | 0* | 0.00528 | 2.12 | 2.88 | 100% | 94% | 94% | 0 | 0 / 0 | not run |
| anthropic/claude-opus-5.5 | 4.00 | 20.00 | 1769 | 136 | 20 | 0.00980 | 2.16 | 4.21 | 100% | 94% | 94% | 0 | 0 / 0 | not run |

Notes on the table:
- **Latency:** p50 and max combine the grid calls (parallelism 4) with the sequential repeat runs.
- **Reasoning:** every reasoning-capable model ran with reasoning off or minimal. Haiku, DeepSeek, Gemini and Qwen accepted `effort: none`. gpt-oss-120b accepted `minimal` but still spent about 162 reasoning tokens per call, which is 70% of its output. Sonnet and Opus have **mandatory** reasoning, so I used `minimal`. They reported 0 and about 20 reasoning tokens respectively. *Sonnet reports 0, which may be unreported rather than zero.
- **Determinism:** "decision fields" means status, numbers in the answer, and cited IDs. "Raw text" is the full response string. Even at temperature 0, **no model was bit-identical** across repeats. The wording of the answer and rationale changes. Haiku and Gemini were decision-stable on 4/4 cases, and gpt-oss on 3/4.
- **Hallucinated citations:** zero across all 405 successful calls in every phase. No invented IDs were seen.
- **Abstention cases:** all 8 models passed all four abstain and trap cases (cost with and without the ABSENT record, supervisor, POB, and the "mud logging company" vs drilling-contractor trap). Nobody substituted a related field.

Accuracy by case type (all models pooled): lookups 97%, unsupported 100%, partial 100%, trap 100%, multi-record compare 50%, derived (diff or sum) 88%, distractor 81%, multi-part 88%, **date-window 12%**.

## 2. Projected cost (measured average tokens; shares of the $15 team credit)

Our test contexts average 15 lines (about 1.3–2.0k input tokens). Real pipeline contexts ("a handful of lines") should be cheaper. These numbers are an upper bound.

| Model | 32 questions, one run | 10 reruns (320 calls) | % of $15 | 200 dashboard questions | % of $15 | 32 q with 25% (8 q) escalated to Sonnet |
|---|---|---|---|---|---|---|
| deepseek-v4-flash | $0.004 | $0.039 | 0.26% | $0.025 | 0.16% | $0.045 |
| gpt-oss-120b | $0.004 | $0.042 | 0.28% | $0.026 | 0.17% | $0.045 |
| llama-4-scout | $0.007 | $0.068 | 0.45% | $0.042 | 0.28% | $0.047 |
| **claude-haiku-5.5** | **$0.008** | **$0.083** | **0.55%** | **$0.052** | **0.34%** | **$0.049** |
| qwen3.7-plus | $0.020 | $0.197 | 1.3% | $0.123 | 0.82% | $0.057 |
| gemini-3-flash-preview | $0.035 | $0.346 | 2.3% | $0.216 | 1.4% | $0.068 |
| claude-sonnet-5.5 | $0.169 | $1.69 | 11.3% | $1.06 | 7.0% | n/a |
| claude-opus-5.5 | $0.314 | $3.14 | 20.9% | $1.96 | 13.1% | n/a |

With 25% of questions escalated to **Opus** instead of Sonnet, the Haiku base becomes $0.085 per 32 questions (0.56% of $15).
The takeaway: the LLM step is almost free at this scale. **Cost is not the binding constraint, accuracy and verifiability are.** Even running Opus on all 32 questions costs $0.31. Judges still reward showing the cost-performance reasoning, so keep the tiered design and the logged ledger.

## 3. Recommendation

| Role | Model ID | Why |
|---|---|---|
| **Batch primary (32 q)** | `anthropic/claude-haiku-5.5` | 16/16 on our cases, 100% decision-stable, p50 1.2s, $0.008 per run, 0 hallucinated cites |
| **Live dashboard / agent** | `anthropic/claude-haiku-5.5` (1.2s p50, 1.7s max). Ultra-cheap option: `openai/gpt-oss-120b` pinned to Crusoe (0.5s p50, 0.74s max, $0.0001/call, but 88–94% accuracy) | Both are well under the 5s target |
| **Escalation (verifier failed only)** | `anthropic/claude-sonnet-5.5` (minimal reasoning) | Same accuracy as Opus on our set at about half the price ($0.005/call). `claude-opus-5.5` is the manual last resort at $0.01/call |

Escalate **only when the code verifier fails**. Do **not** escalate on abstain. The larger models (Sonnet, Opus, Gemini, Qwen) abstained more on the date-window case, so a bigger model is not a fix for that. See section 4.

Settings that worked:
- `temperature: 0`, `max_tokens: 400` (0 truncations, 0 empties in 405 calls).
- **response_format** = `json_schema` (strict) with the 4-field contract, as in `openrouter_client.ANSWER_SCHEMA`.
- **Reasoning:** Haiku `{"effort":"none"}`. Sonnet and Opus `{"effort":"minimal"}` (`none` returns HTTP 400 "Reasoning is mandatory"). gpt-oss `{"effort":"minimal"}`.
- **Provider pinning for Anthropic is required, not optional.** `provider: {"order":["Anthropic"],"allow_fallbacks":false,"require_parameters":false}`.
  With `require_parameters:true`, every Anthropic request returned HTTP **404 "No endpoints found"**, because the AWS-hosted endpoint does not advertise structured outputs. Without a pin, the first Anthropic grid fell back to no `response_format` on 48 calls, giving 1 HTTP 404 and 4 invalid-JSON responses where the model wrote prose around the JSON. Fixed by the pin (0 invalid in the rerun).
- **Other models:** keep `require_parameters:true`. For gpt-oss, pin `Crusoe`. Unpinned it was served by 5 different providers (Crusoe, Groq, AkashML, DekaLLM, PrimeIntellect), with a worst-case latency of 3.3s. Pinned, the worst case was 0.74s, at the same cost.
- **Retries:** 3 attempts, backoff 1s/2s/4s on 429 and 5xx and network errors, honour `Retry-After`, never retry 400, 402 or 404. We saw zero 429s, so this is a safety net only.
- **Parallelism:** 8 concurrent calls finished in about 1.3–1.5s wall time (17 calls, zero errors, zero retries). **Parallelise the 32 questions at 8 workers.** The whole batch then takes roughly 5–8s.
- **Cache:** commit `results/cache`-style answers keyed by sha256 of (system, context, question, model, settings). Outputs are not bit-reproducible even at temperature 0, so the cache is what makes reviewer reruns deterministic.

## 4. Winning prompt and failure patterns

**Prompt variants (4 models × 16 cases):**

| Variant | Extra input | Haiku | DeepSeek | Gemini | gpt-oss |
|---|---|---|---|---|---|
| `compact` (`SYSTEM_COMPACT`, ~190 tokens) | baseline | 100% | 87.5% | 93.8% | 87.5% |
| `compact_ts` (compact + one timestamp sentence) | +55 tok | 100% | **93.8%** | 93.8% | 87.5% |
| `explicit` (12 rules, ~620 tokens) | +470 tok (about +20% cost) | 93.8% | 87.5% | 93.8% | **93.8%** |

**Winner: `compact_ts`** (in `prompts.py`). It is the cheapest prompt that fixes anything. The long explicit prompt costs about 20% more, gave no gain for Haiku (it introduced an arithmetic slip, 26.14 m instead of 25.94 m), and helped only gpt-oss.
The honest read is that prompt length is **not worth paying for** on strong models. The one worthwhile addition is the timestamp sentence (and even that did not fix Gemini).
The differences between variants are within 1 case, so treat this as weak evidence.

**Failure patterns (these should shape the verifier):**
1. **Date-window (report date D, event timestamp D−1): the most common failure.** Sonnet, Opus, Gemini and Qwen **abstained** even though the line was in context, because the question's date differed from the timestamp. Haiku answered. gpt-oss and DeepSeek answered but didn't mention the timestamp.
   Fix in the **pipeline, not the model**: when routing a question to a report, pass the event timestamp explicitly, or normalise "at HH:MM on D" to the report's window before the LLM call. Treat "abstain while a gold-routed line has the matching field" as a router signal, not a reason to escalate.
2. **Under-answering ("partial" on fully supported lookups):** Llama-4-scout marked 5 supported single-record questions as `partial`, and it was the only model that failed distractors with wrong or mixed values. Don't use it.
3. **Dropping a requested sub-part:** gpt-oss, DeepSeek and Qwen gave the right number on "which is higher, give the value" but never said which. Haiku, Gemini, Sonnet and Opus did. Status was still `answered`, so a status or citation verifier misses it.
4. **Distractor confusion:** Qwen abstained on the near-duplicate fluid case. Llama picked values from the wrong record (1.4 instead of 1.32 g/cm3).
5. **Arithmetic slips on derived numbers:** Qwen answered 19 m (correct: 18), Llama answered 26.0 m (correct: 25.94), and Haiku slipped once under the explicit prompt (26.14 vs 25.94). The verifier rule ("every number in the answer appears in a cited line, or is the sum, difference or mean of two cited numbers") accepted every correct derived answer, but it **caught only Haiku's slip**. It **accepted Qwen's 19 and Llama's 26.0 by coincidence**: when the cited lines carry many numbers (depths, tops, bottoms), the set of pairwise sums, differences and means is large enough to land near a wrong value.
   Tighten it: allow derived values only from numbers the model names in its rationale or answer, require an exact (rounded-to-source-precision) match, and test only numbers that the question's wording asks for. Or ask the model to return the operands and recompute in code.
6. **Verifier blind spots (important):** of 18 wrong answers across the grid, the number and citation rules caught **1** (Llama's wrong D1 value). The other 17 were wrong abstentions, wrong status, missing sub-parts or missing timestamp mentions, none of which move a number or an ID. Add cheap checks for these:
   - abstain while the question's well, date and field match a context line;
   - a multi-part question where an expected term (for example the activity text) is absent from the answer;
   - `partial` or `abstain` with no missing-info statement in the rationale.
7. **Not seen (good):** invented IDs (0), wrong units (1 Llama miss), answering cost, supervisor or POB, substituting the drilling contractor for a mud-logging company, empty responses, `finish_reason: length`.

## 5. Suggested split of the $15

Measured costs are far below the planning guess, so the reserve can be bigger.

| Bucket | Plan | Notes |
|---|---|---|
| Benchmark (done) | **$0.62** | spent |
| Development and answering runs | $2.00 | about 25 full 32-question runs with Haiku is $0.21; the rest covers experiments |
| Final run plus escalations | $0.50 | 32 q on Haiku ($0.01), plus Sonnet on any verifier failure, plus a few reruns |
| Dashboard, agent building and demo | $3.00 | one Haiku 3-step tool loop costs about $0.0006, so 1,000 demo loops is about $0.6 |
| Reserve | **$8.88** | any VLM or image work in the main pipeline would come out of this |

Keep the per-key limit at $15. It is already set on this key. The workspace limit is $150, and the account balance could not be read (`/credits` needs a management key).

## 6. Risks and surprises

- **Anthropic routing trap:** `require_parameters:true` makes every Claude request 404. Without a pin, requests can silently land on endpoints without schema enforcement. This cost me about $0.23 on a wasted first grid.
- **Mandatory reasoning:** Sonnet and Opus return HTTP 400 on `effort:none`. Treat the 400 as free, but handle it. The client-side fallback chain I used in `bench.py` also had a race under threads (3 bad calls in a parallel run); it was fixed by warming the settings up serially first.
- **Provider variety hurts latency and determinism:** gpt-oss was served by 5 providers, and DeepSeek by 4 (Baidu, DeepInfra, Parasail, Venice). Pin for any live use.
- **Not bit-reproducible at temperature 0:** commit the answer cache. Don't promise reviewers identical raw text.
- **Preview models:** `google/gemini-3-flash-preview` is a preview, so its price or availability can change.
- **Small sample:** 16 cases × 1 call. The ranking among Haiku, Gemini, Sonnet and Opus is within noise. Run a larger set before hard-coding any claim like "Haiku beats Opus".
- **Date-window case is ambiguous by design:** a strict reader could argue that abstaining is right. I used your stated expectation (answer from the D−1 line and mention the timestamp), and reported it separately.
- **Models that look cheap but burn tokens:** gpt-oss-120b spends 70% of its output on reasoning even at `minimal` (230 tokens vs DeepSeek's 69). It is still tiny in dollars.
- **Wireline trap deviation:** the XML has no wireline "service company" field, so the "mud logging company" trap uses the real `drilling contractor` line.
- **Prompt caching:** skipped as instructed (the ~200-token prompt is below every provider's minimum prefix).
- **Unverified:** the `/credits` endpoint (403, management key needed) and per-key rate limits (the `rate_limit` field is deprecated). At 8 parallel calls we saw no throttling.

## 7. Files
- `build_cases.py` → `cases.json` (16 cases, expected values computed from the XML)
- `prompts.py`, `scoring.py` (scorer and verifier rule), `bench.py` (runner), `rescore.py`, `analyze.py`
- `openrouter_client.py` + `test_openrouter_client.py` (9 mocked tests, no network)
- `tool_test.py` (3-step tool loop): gpt-oss-120b succeeded 3/3 (2 tool calls each, $0.00003–0.00007, about 3.5s). Haiku succeeded 3/3 but made 4–6 tool calls per loop (one malformed argument string), at about $0.0006 and about 3.8s.
  Both are reliable enough for the agent demo, and gpt-oss is about 10× cheaper per loop.
- `probe.py`, `probe2.py` (routing probes), `step1_key_check.py`, `step2_models.py` (key check and live model list)
- `results/`: `calls.csv`, `summary.csv`, `projection.csv`, `ledger.csv`, `models_raw.json`, `raw/`
