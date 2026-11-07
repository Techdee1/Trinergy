"""Benchmark runner. Resumable: a (phase, model, variant, case, rep, pin) already in calls.csv is skipped.

    python bench.py grid                      # all models x all cases, compact prompt
    python bench.py latency  m1,m2,m3         # 4 lookup cases x3 repeats (also determinism)
    python bench.py pinned   m1,m2,m3         # same, provider pinned (order + allow_fallbacks false)
    python bench.py parallel model            # 8 parallel calls x2 rounds
    python bench.py variant  m1,m2            # explicit prompt on all cases
Spend is capped at CAP_USD through openrouter_client's guard (reads results/ledger.csv).
"""
from __future__ import annotations

import csv
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv

import openrouter_client as oc
from prompts import SYSTEM_COMPACT, SYSTEM_COMPACT_TS, SYSTEM_EXPLICIT
from scoring import score

HERE = Path(__file__).parent
RES = HERE / "results"
RAW = RES / "raw"
CALLS = RES / "calls.csv"
CAP_USD = 1.00
CFG = oc.ClientConfig(cache_dir=RES / "cache", ledger_path=RES / "ledger.csv", spend_cap_usd=CAP_USD)

MODELS = [  # tier, id
    ("cheap", "openai/gpt-oss-120b"),
    ("cheap", "meta-llama/llama-4-scout"),
    ("cheap", "deepseek/deepseek-v4-flash"),
    ("cheap", "anthropic/claude-haiku-5.5"),
    ("mid", "google/gemini-3-flash-preview"),
    ("mid", "qwen/qwen3.7-plus"),
    ("top", "anthropic/claude-sonnet-5.5"),
    ("top", "anthropic/claude-opus-5.5"),
]
VARIANTS = {"compact": SYSTEM_COMPACT, "explicit": SYSTEM_EXPLICIT, "compact_ts": SYSTEM_COMPACT_TS}
REASONING_CHAIN = [{"effort": "none"}, {"effort": "minimal"}, {"effort": "low"}]
FIELDS = ["phase", "model", "variant", "case_id", "case_type", "rep", "pin", "provider", "latency_s", "input_tokens",
          "output_tokens", "reasoning_tokens", "cost", "http_status", "finish_reason", "error", "attempts",
          "retries", "reasoning_setting", "json_mode", "json_valid", "empty", "truncated", "status", "status_ok",
          "answer_correct", "cited_exist", "invented_ids", "cite_has_value", "gold_cited", "verifier_ok",
          "unit_ok", "forbidden_hit", "parts_ok", "n_cited", "raw_text"]

_lock = threading.Lock()
_model_cfg: dict[str, dict] = {}  # learned per-model reasoning / json_mode that the API accepted
PRICES: dict[str, tuple[float, float]] = {}
REASONING_MODELS: set[str] = set()


def load_model_meta() -> None:
    for m in json.loads((RES / "models_raw.json").read_text()):
        PRICES[m["id"]] = (float(m["pricing"]["prompt"]) * 1e6, float(m["pricing"]["completion"]) * 1e6)
        if "reasoning" in (m.get("supported_parameters") or []):
            REASONING_MODELS.add(m["id"])


def done_keys() -> set[tuple]:
    if not CALLS.exists():
        return set()
    with CALLS.open(newline="") as f:
        return {(r["phase"], r["model"], r["variant"], r["case_id"], r["rep"], r["pin"]) for r in csv.DictReader(f)}


def append_row(row: dict) -> None:
    with _lock:
        new = not CALLS.exists()
        with CALLS.open("a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
            if new:
                w.writeheader()
            w.writerow(row)


ANTHROPIC_PIN = {"order": ["Anthropic"], "allow_fallbacks": False, "require_parameters": False}


def default_provider(model: str) -> dict | None:
    """Anthropic endpoints other than the first-party one reject json_schema under require_parameters."""
    return dict(ANTHROPIC_PIN) if model.startswith("anthropic/") else None


def err_message(res: oc.LLMResult) -> str:
    try:
        return str(json.loads(res.raw_text).get("message", "")).lower()
    except ValueError:
        return res.raw_text.lower()


def call_with_fallbacks(model: str, system: str, case: dict, provider: dict | None) -> tuple[oc.LLMResult, dict]:
    """Learn which reasoning setting / json mode the model accepts (400s cost nothing)."""
    provider = provider or default_provider(model)
    st = _model_cfg.setdefault(model, {"reasoning_idx": 0 if model in REASONING_MODELS else None, "json_mode": "json_schema"})
    while True:
        reasoning = REASONING_CHAIN[st["reasoning_idx"]] if st["reasoning_idx"] is not None else None
        res = oc.call_llm(system, case["context"], case["question"], model, max_tokens=400, reasoning=reasoning,
                          provider=provider, json_mode=st["json_mode"], prices_per_m=PRICES.get(model),
                          config=CFG, use_cache=False, source=f"bench:{case['id']}")
        msg = err_message(res) if res.http_status in (400, 404) else ""
        if res.http_status in (400, 404) and ("reason" in msg or "effort" in msg) and st["reasoning_idx"] is not None:
            if st["reasoning_idx"] + 1 < len(REASONING_CHAIN):
                st["reasoning_idx"] += 1
                continue
            st["reasoning_idx"] = None
            continue
        if res.http_status in (400, 404) and st["json_mode"] == "json_schema":
            st["json_mode"] = "json_object"
            continue
        if res.http_status in (400, 404) and st["json_mode"] == "json_object":
            st["json_mode"] = "none"
            continue
        return res, dict(st, reasoning=reasoning)


def run_one(phase: str, model: str, variant: str, case: dict, rep: int, provider: dict | None = None) -> dict | None:
    pin = json.dumps(provider, sort_keys=True) if provider else ""
    key = (phase, model, variant, case["id"], str(rep), pin)
    if key in done_keys():
        return None
    try:
        res, st = call_with_fallbacks(model, VARIANTS[variant], case, provider)
    except oc.SpendGuardError as e:
        print("SPEND GUARD:", e, flush=True)
        raise
    sc = score(case, res.parsed, res.finish_reason, res.raw_text, res.error)
    row = {"phase": phase, "model": model, "variant": variant, "case_id": case["id"], "case_type": case["type"],
           "rep": rep, "pin": pin, "provider": res.provider, "latency_s": round(res.latency_s, 3),
           "input_tokens": res.input_tokens, "output_tokens": res.output_tokens, "reasoning_tokens": res.reasoning_tokens,
           "cost": res.cost, "http_status": res.http_status, "finish_reason": res.finish_reason, "error": res.error,
           "attempts": res.attempts, "retries": "; ".join(res.retry_log),
           "reasoning_setting": json.dumps(st.get("reasoning")), "json_mode": st["json_mode"],
           "raw_text": res.raw_text.replace("\n", " ")[:1500], **sc}
    append_row(row)
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / f"{phase}__{model.replace('/', '_')}__{variant}__{case['id']}__{rep}{'__pin' if pin else ''}.json").write_text(
        json.dumps({"raw_text": res.raw_text, "parsed": res.parsed, "provider": res.provider,
                    "finish_reason": res.finish_reason}, indent=1))
    return row


def load_cases() -> list[dict]:
    return json.loads((HERE / "cases.json").read_text())


def total_spend() -> float:
    return oc.ledger_total(CFG.ledger_path)


def pool_run(jobs: list[tuple], workers: int) -> None:
    def work(j):
        try:
            return run_one(*j)
        except oc.SpendGuardError:
            return "STOP"
    with ThreadPoolExecutor(workers) as ex:
        for r in ex.map(work, jobs):
            if r == "STOP":
                print("stopped by spend guard", flush=True)
                break
    print(f"spend so far: ${total_spend():.4f}", flush=True)


def main() -> None:
    load_dotenv(HERE.parent.parent / ".env")
    load_model_meta()
    cases = load_cases()
    phase = sys.argv[1]
    models = sys.argv[2].split(",") if len(sys.argv) > 2 else [m for _, m in MODELS]
    lookups = [c for c in cases if c["type"] == "A_lookup"]

    if phase == "grid":
        pool_run([("grid", m, "compact", c, 0) for m in models for c in cases], workers=4)
    elif phase == "latency":  # sequential for clean latency; 3 repeats of the 4 lookups
        pool_run([("latency", m, "compact", c, r) for m in models for c in lookups for r in range(3)], workers=1)
    elif phase == "pinned":
        pins = json.loads(sys.argv[3])  # {"model": "ProviderName"}
        jobs = [("pinned", m, "compact", c, r, {"order": [pins[m]], "allow_fallbacks": False})
                for m in models for c in lookups for r in range(3)]
        pool_run(jobs, workers=1)
    elif phase == "parallel":
        m = models[0]
        run_one("parallel2", m, "compact", cases[0], 99)  # warm-up: learn accepted settings serially (avoids a race)
        for rnd in range(2):
            jobs = [("parallel2", m, "compact", cases[i % len(cases)], 100 + rnd * 8 + i) for i in range(8)]
            t0 = time.perf_counter()
            pool_run(jobs, workers=8)
            print(f"round {rnd}: wall {time.perf_counter() - t0:.2f}s for 8 calls", flush=True)
    elif phase == "variant":
        pool_run([("variant", m, "explicit", c, 0) for m in models for c in cases], workers=4)
    elif phase == "variant_ts":
        pool_run([("variant", m, "compact_ts", c, 0) for m in models for c in cases], workers=4)
    else:
        raise SystemExit(f"unknown phase {phase}")


if __name__ == "__main__":
    main()
