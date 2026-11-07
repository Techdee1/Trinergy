"""Small typed OpenRouter client for the evidence-to-answer LLM step.

Features: sha256 disk cache, cost ledger CSV, retry on 429/5xx, global spend guard,
key from the environment only (never printed, never written).

    result = call_llm(SYSTEM, context, question, "anthropic/claude-haiku-5.5")
    result.parsed  -> {"status": ..., "answer": ..., "cited_ids": [...], "rationale": ...} or None
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

BASE_URL = "https://openrouter.ai/api/v1"
KEY_ENV_NAMES = ("OpenRouter_Key", "OPENROUTER_API_KEY")  # first one found wins
RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3
LEDGER_FIELDS = ["timestamp", "model", "provider", "input_tokens", "output_tokens",
                 "reasoning_tokens", "cost", "cache_hit", "latency", "source"]

ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["answered", "partial", "abstain"]},
        "answer": {"type": "string"},
        "cited_ids": {"type": "array", "items": {"type": "string"}},
        "rationale": {"type": "string"},
    },
    "required": ["status", "answer", "cited_ids", "rationale"],
    "additionalProperties": False,
}


class SpendGuardError(RuntimeError):
    """Raised before a call that could push total spend over the cap."""


class MissingKeyError(RuntimeError):
    pass


@dataclass
class ClientConfig:
    cache_dir: Path = Path("cache")
    ledger_path: Path = Path("ledger.csv")
    spend_cap_usd: float = 1.00
    timeout_s: float = 90.0


@dataclass
class LLMResult:
    parsed: dict[str, Any] | None
    raw_text: str
    model: str
    provider: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cost: float = 0.0
    latency_s: float = 0.0
    http_status: int = 0
    finish_reason: str = ""
    cache_hit: bool = False
    attempts: int = 1
    error: str = ""          # "", "http_<code>", "json_parse", "empty", "network"
    retry_log: list[str] = field(default_factory=list)


# ---- module state -------------------------------------------------------------
_lock = threading.Lock()
_spent_session = 0.0


def _get_key() -> str:
    for name in KEY_ENV_NAMES:
        val = os.environ.get(name, "").strip()
        if val:
            return val
    raise MissingKeyError(f"set one of {KEY_ENV_NAMES} in the environment")


def _http_post(url: str, headers: dict[str, str], payload: dict[str, Any], timeout: float):
    """Single network seam: tests replace this function."""
    return requests.post(url, headers=headers, json=payload, timeout=timeout)


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def ledger_total(path: Path) -> float:
    """Total real spend recorded in a ledger file."""
    if not path.exists():
        return 0.0
    with path.open(newline="") as f:
        return sum(float(r["cost"] or 0) for r in csv.DictReader(f))


def _append_ledger(cfg: ClientConfig, res: LLMResult, source: str) -> None:
    new = not cfg.ledger_path.exists()
    cfg.ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with cfg.ledger_path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LEDGER_FIELDS)
        if new:
            w.writeheader()
        w.writerow({
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "model": res.model, "provider": res.provider,
            "input_tokens": res.input_tokens, "output_tokens": res.output_tokens,
            "reasoning_tokens": res.reasoning_tokens, "cost": f"{res.cost:.8f}",
            "cache_hit": res.cache_hit, "latency": f"{res.latency_s:.3f}", "source": source,
        })


def cache_key(system: str, context: str, question: str, model: str, settings: dict[str, Any]) -> str:
    blob = json.dumps([system, context, question, model, settings], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()


def _extract_provider(body: dict[str, Any]) -> str:
    if isinstance(body.get("provider"), str):
        return body["provider"]
    meta = body.get("openrouter_metadata") or {}
    for ep in (meta.get("endpoints") or {}).get("available", []):
        if ep.get("selected"):
            return str(ep.get("provider", ""))
    return ""


def _parse_json(text: str) -> dict[str, Any] | None:
    """Parse the contract JSON. Tolerates a ```json fence; rejects anything off-contract."""
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[4:] if t.lower().startswith("json") else t
    try:
        obj = json.loads(t)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    if obj.get("status") not in ("answered", "partial", "abstain"):
        return None
    if not isinstance(obj.get("answer"), str) or not isinstance(obj.get("cited_ids"), list):
        return None
    obj.setdefault("rationale", "")
    return obj


def call_llm(
    system: str,
    context: str,
    question: str,
    model: str,
    *,
    max_tokens: int = 400,
    temperature: float = 0.0,
    reasoning: dict[str, Any] | None = None,
    provider: dict[str, Any] | None = None,
    json_mode: str = "json_schema",      # "json_schema" | "json_object" | "none"
    prices_per_m: tuple[float, float] | None = None,  # (in, out) USD per 1M, for the spend guard
    config: ClientConfig | None = None,
    use_cache: bool = True,
    source: str = "",
) -> LLMResult:
    global _spent_session
    cfg = config or ClientConfig()
    settings = {"t": temperature, "max_tokens": max_tokens, "reasoning": reasoning,
                "provider": provider, "json_mode": json_mode}
    key = cache_key(system, context, question, model, settings)
    cache_file = cfg.cache_dir / f"{key}.json"

    if use_cache and cache_file.exists():
        res = LLMResult(**json.loads(cache_file.read_text()))
        res.cache_hit, res.cost, res.latency_s = True, 0.0, 0.0
        _append_ledger(cfg, res, source)
        return res

    # --- spend guard: worst-case cost of this call must fit under the cap
    est = 0.0
    if prices_per_m:
        est_in = (len(system) + len(context) + len(question)) / 3.0
        est = (est_in * prices_per_m[0] + max_tokens * prices_per_m[1]) / 1e6
    with _lock:
        spent = max(ledger_total(cfg.ledger_path), _spent_session)
        if spent + est > cfg.spend_cap_usd or spent >= cfg.spend_cap_usd:
            raise SpendGuardError(f"spent ${spent:.4f} + est ${est:.4f} would exceed cap ${cfg.spend_cap_usd:.2f}")

    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": f"EVIDENCE:\n{context}\n\nQUESTION: {question}"}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode == "json_schema":
        payload["response_format"] = {"type": "json_schema",
                                      "json_schema": {"name": "answer", "strict": True, "schema": ANSWER_SCHEMA}}
    elif json_mode == "json_object":
        payload["response_format"] = {"type": "json_object"}
    prov = dict(provider or {})
    if json_mode != "none":
        prov.setdefault("require_parameters", True)
    if prov:
        payload["provider"] = prov
    if reasoning is not None:
        payload["reasoning"] = reasoning

    headers = {"Authorization": f"Bearer {_get_key()}", "Content-Type": "application/json",
               "X-OpenRouter-Metadata": "enabled", "X-OpenRouter-Title": "llm-bench"}

    res = LLMResult(parsed=None, raw_text="", model=model)
    resp = None
    t0 = time.perf_counter()
    for attempt in range(1, MAX_ATTEMPTS + 1):
        res.attempts = attempt
        try:
            resp = _http_post(f"{BASE_URL}/chat/completions", headers, payload, cfg.timeout_s)
            status = resp.status_code
        except requests.RequestException as e:  # timeouts, connection resets
            resp, status = None, 0
            res.retry_log.append(f"attempt {attempt}: network {type(e).__name__}")
        else:
            if status not in RETRY_STATUS:
                break
            res.retry_log.append(f"attempt {attempt}: http {status}")
        if attempt < MAX_ATTEMPTS:
            wait = 2.0 ** (attempt - 1)
            if resp is not None and resp.headers.get("Retry-After", "").isdigit():
                wait = min(float(resp.headers["Retry-After"]), 10.0)
            _sleep(wait)
    res.latency_s = time.perf_counter() - t0

    if resp is None:
        res.error = "network"
        return res
    res.http_status = resp.status_code
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if resp.status_code != 200:
        res.error = f"http_{resp.status_code}"
        res.raw_text = json.dumps(body.get("error", body))[:500]
        return res

    usage = body.get("usage") or {}
    choice = (body.get("choices") or [{}])[0]
    res.raw_text = (choice.get("message") or {}).get("content") or ""
    res.finish_reason = choice.get("finish_reason") or ""
    res.provider = _extract_provider(body)
    res.input_tokens = int(usage.get("prompt_tokens") or 0)
    res.output_tokens = int(usage.get("completion_tokens") or 0)
    res.reasoning_tokens = int((usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)
    res.cost = float(usage.get("cost") or 0.0)

    with _lock:
        _spent_session = max(_spent_session, ledger_total(cfg.ledger_path)) + res.cost
        _append_ledger(cfg, res, source)

    if not res.raw_text.strip():
        res.error = "empty"
        return res
    res.parsed = _parse_json(res.raw_text)
    if res.parsed is None:
        res.error = "json_parse"
        return res

    if use_cache:  # only cache good answers
        cfg.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(asdict(res)))
    return res
