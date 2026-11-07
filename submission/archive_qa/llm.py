"""LLM access: OpenRouter client, deterministic disk cache, offline mode, cost ledger, spend guard.

Reviewers rerun the notebook WITHOUT an API key, so every answer must be replayable from
`indexes/llm_cache.json`. A cache miss in offline mode raises `CacheMiss`; nothing ever
silently falls back to abstaining.

Layers
  Backend      one real HTTP call (OpenRouterBackend) or a scripted double (FakeLLM)
  LLM          cache lookup -> (live only) budget guard -> backend with retries -> cache + ledger

The cache key is sha256(system prompt + context + question + feedback + model + settings).
Cache entries store the parsed response, model, usage and question id, never the context.
The model names used are also saved in the cache's `_meta`, so an offline run reproduces the same
keys without needing LLM_MODEL_* in the environment.

The API key is read from the environment variable `OpenRouter_Key` (or OPENROUTER_API_KEY) and is never
printed, logged or stored.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from . import config

KEY_ENV_NAMES = ("OpenRouter_Key", "OPENROUTER_API_KEY")
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
LEDGER_FIELDS = ["timestamp", "question_id", "role", "model", "prompt_tokens",
                 "completion_tokens", "cost_usd", "cache_hit"]


class CacheMiss(RuntimeError):
    """Offline mode and the answer is not in the committed cache."""


class BudgetExceeded(RuntimeError):
    """LLM_BUDGET_USD reached for this run."""


class ModelsNotSet(RuntimeError):
    """A key is present but LLM_MODEL_PRIMARY / LLM_MODEL_ESCALATION are not set."""


# ------------------------------------------------------------------ environment


def load_env_file(path: Path) -> dict[str, str]:
    """Tiny .env reader (no extra dependency). Returns the variables; never prints values."""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$", line)
        if not m or line.lstrip().startswith("#"):
            continue
        val = m.group(2)
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        out[m.group(1)] = val
    return out


def env_names(path: Path | None = None) -> list[str]:
    """Variable NAMES present in .env (values are never exposed)."""
    return sorted(load_env_file(path or (config.REPO_ROOT / ".env")))


def _env(name: str, dotenv: dict[str, str]) -> str | None:
    return (os.environ.get(name) or dotenv.get(name) or "").strip() or None


@dataclass
class LLMConfig:
    api_key: str | None = field(default=None, repr=False)  # never shown
    primary: str | None = None
    escalation: str | None = None
    fast: str | None = None
    budget_usd: float = 3.00
    concurrency: int = 4
    max_tokens: int = 500
    temperature: float = 0.0
    live: bool = False
    price_in_per_1m: float | None = None
    price_out_per_1m: float | None = None

    @property
    def settings(self) -> dict:
        return {"temperature": self.temperature, "max_tokens": self.max_tokens,
                "response_format": "json_object"}

    def describe(self) -> dict:
        """Safe summary: names and booleans only."""
        return {"mode": "live" if self.live else "offline", "key_present": bool(self.api_key),
                "primary": self.primary, "escalation": self.escalation, "fast": self.fast,
                "budget_usd": self.budget_usd, "concurrency": self.concurrency}


def load_config(live: bool = False, dotenv_path: Path | None = None) -> LLMConfig:
    """Build the config. `live=False` (default) is offline: the key is ignored and only the cache is used.

    Model names: environment/.env first, else the names recorded in the cache `_meta`.
    """
    dotenv = load_env_file(dotenv_path or (config.REPO_ROOT / ".env"))
    meta = Cache(config.LLM_CACHE_PATH).meta.get("models", {})
    key = next((v for n in KEY_ENV_NAMES if (v := _env(n, dotenv))), None)

    def model(name: str, slot: str) -> str | None:
        return _env(name, dotenv) or meta.get(slot)

    cfg = LLMConfig(
        api_key=key if live else None,
        primary=model("LLM_MODEL_PRIMARY", "primary"),
        escalation=model("LLM_MODEL_ESCALATION", "escalation"),
        fast=model("LLM_MODEL_FAST", "fast"),
        budget_usd=float(_env("LLM_BUDGET_USD", dotenv) or 3.00),
        concurrency=max(1, int(_env("LLM_CONCURRENCY", dotenv) or 4)),
        live=bool(live and key),
        price_in_per_1m=float(v) if (v := _env("LLM_PRICE_IN_PER_1M", dotenv)) else None,
        price_out_per_1m=float(v) if (v := _env("LLM_PRICE_OUT_PER_1M", dotenv)) else None,
    )
    if live and not key:
        raise RuntimeError(f"Live mode needs an API key in env var {KEY_ENV_NAMES[0]} (or {KEY_ENV_NAMES[1]}).")
    if live and not (cfg.primary and cfg.escalation):
        missing = [n for n, v in (("LLM_MODEL_PRIMARY", cfg.primary), ("LLM_MODEL_ESCALATION", cfg.escalation)) if not v]
        raise ModelsNotSet("Set in .env: " + ", ".join(missing))
    return cfg


# ------------------------------------------------------------------ backends


@dataclass
class RawResponse:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float | None = None


class Backend(Protocol):
    def chat(self, system: str, user: str, model: str, max_tokens: int, temperature: float) -> RawResponse: ...


class TransientError(RuntimeError):
    """429 or 5xx: worth retrying."""


class OpenRouterBackend:
    """OpenAI-compatible chat completions through OpenRouter (requests only)."""

    def __init__(self, api_key: str, timeout: float = 90.0, max_attempts: int = 3, backoff: float = 2.0):
        self._key = api_key
        self.timeout, self.max_attempts, self.backoff = timeout, max_attempts, backoff

    def _scrub(self, text: str) -> str:
        return text.replace(self._key, "***") if self._key else text

    def _once(self, system: str, user: str, model: str, max_tokens: int, temperature: float) -> RawResponse:
        import requests

        body = {
            "model": model, "temperature": temperature, "max_tokens": max_tokens, "seed": 0,
            "response_format": {"type": "json_object"}, "usage": {"include": True},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        r = requests.post(ENDPOINT, json=body, timeout=self.timeout,
                          headers={"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"})
        if r.status_code == 429 or r.status_code >= 500:
            raise TransientError(f"HTTP {r.status_code}: {self._scrub(r.text[:200])}")
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code} from OpenRouter: {self._scrub(r.text[:300])}")
        data = r.json()
        if "error" in data and "choices" not in data:  # errors can arrive with HTTP 200
            code = (data["error"] or {}).get("code")
            msg = self._scrub(json.dumps(data["error"])[:300])
            if code == 429 or (isinstance(code, int) and code >= 500):
                raise TransientError(msg)
            raise RuntimeError(f"OpenRouter error: {msg}")
        usage = data.get("usage") or {}
        return RawResponse(
            text=(data["choices"][0]["message"].get("content") or ""),
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            cost_usd=float(usage["cost"]) if usage.get("cost") is not None else None,
        )

    def chat(self, system, user, model, max_tokens, temperature=0.0) -> RawResponse:
        last: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                return self._once(system, user, model, max_tokens, temperature)
            except TransientError as e:  # retry ONLY 429/5xx
                last = e
                if attempt + 1 < self.max_attempts:
                    time.sleep(self.backoff * (2 ** attempt))
        raise RuntimeError(f"OpenRouter still failing after {self.max_attempts} attempts: {last}")


class FakeLLM:
    """Test double. `script` is a dict {substring-of-user-message: reply} or a callable
    (system, user, model) -> reply, where a reply is a dict (JSON-encoded) or a str."""

    def __init__(self, script: dict | Callable | None = None, tokens: tuple[int, int] = (100, 50), cost: float = 0.001):
        self.script, self.tokens, self.cost = script or {}, tokens, cost
        self.calls: list[dict] = []

    def chat(self, system, user, model, max_tokens, temperature=0.0) -> RawResponse:
        self.calls.append({"system": system, "user": user, "model": model, "max_tokens": max_tokens})
        if callable(self.script):
            reply = self.script(system, user, model)
        else:
            reply = next((v for k, v in self.script.items() if k in user), None)
            if reply is None:
                reply = {"status": "abstain", "answer": "fake", "cited_ids": [], "rationale": "fake"}
        text = reply if isinstance(reply, str) else json.dumps(reply)
        return RawResponse(text, *self.tokens, cost_usd=self.cost)


# ------------------------------------------------------------------ cache


class Cache:
    """JSON file {"_meta": {...}, "entries": {key: {...}}}. Thread-safe, written after every new entry."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self.meta: dict = {}
        self.entries: dict[str, dict] = {}
        if self.path.is_file():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.meta, self.entries = data.get("_meta", {}), data.get("entries", {})

    def get(self, key: str) -> dict | None:
        return self.entries.get(key)

    def put(self, key: str, entry: dict, meta: dict | None = None) -> None:
        with self._lock:
            self.entries[key] = entry
            if meta:
                self.meta.update(meta)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"_meta": self.meta, "entries": self.entries},
                                      indent=1, sort_keys=True, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.path)


def cache_key(system: str, context: str, question: str, feedback: str, model: str, settings: dict) -> str:
    h = hashlib.sha256()
    for part in (system, context, question, feedback, model, json.dumps(settings, sort_keys=True)):
        b = part.encode("utf-8")
        h.update(len(b).to_bytes(8, "big"))  # length-prefixed so field boundaries cannot collide
        h.update(b)
    return h.hexdigest()


def parse_json_reply(text: str) -> dict:
    """Parse the model's JSON. On failure return {"__unparsed__": text} so the verifier reports it."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    for candidate in (cleaned, cleaned[cleaned.find("{"): cleaned.rfind("}") + 1] if "{" in cleaned else ""):
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    return {"__unparsed__": text[:2000]}


# ------------------------------------------------------------------ LLM facade


@dataclass
class Reply:
    parsed: dict
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    cache_hit: bool


class LLM:
    """Cache + ledger + budget around a Backend. `backend=None` means offline (cache only)."""

    def __init__(self, cfg: LLMConfig, backend: Backend | None = None, cache: Cache | None = None,
                 ledger_path: Path | None = None):
        self.cfg = cfg
        self.backend = backend
        self.cache = cache or Cache(config.LLM_CACHE_PATH)
        self.ledger_path = Path(ledger_path) if ledger_path else config.COST_LEDGER_PATH
        self.spent = 0.0
        self.live_calls = 0
        self.cache_hits = 0
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls, live: bool = False) -> "LLM":
        cfg = load_config(live=live)
        backend = OpenRouterBackend(cfg.api_key) if cfg.live else None
        return cls(cfg, backend)

    def ask(self, system: str, context: str, question: str, model: str, *, feedback: str = "",
            question_id: str = "", role: str = "primary") -> Reply:
        key = cache_key(system, context, question, feedback, model, self.cfg.settings)
        hit = self.cache.get(key)
        if hit is not None:
            u = hit.get("usage", {})
            with self._lock:
                self.cache_hits += 1
            self._ledger(question_id, role, model, 0, 0, 0.0, True)
            return Reply(hit["response"], hit["model"], u.get("prompt_tokens", 0),
                         u.get("completion_tokens", 0), u.get("cost_usd", 0.0), True)
        if self.backend is None:
            raise CacheMiss(
                f"No cached LLM answer for question {question_id or '?'} (role={role}, model={model}). "
                "Offline mode only replays submission/indexes/llm_cache.json. To generate it, run the notebook "
                "with LIVE = True and an API key in the OpenRouter_Key environment variable.")
        with self._lock:
            if self.spent >= self.cfg.budget_usd:
                raise BudgetExceeded(f"Spend guard: ${self.spent:.4f} >= LLM_BUDGET_USD ${self.cfg.budget_usd:.2f}")
        raw = self.backend.chat(system, _user_message(context, question, feedback), model,
                                self.cfg.max_tokens, self.cfg.temperature)
        cost = raw.cost_usd
        if cost is None:  # provider did not report cost: use env prices if given
            cost = ((raw.prompt_tokens * (self.cfg.price_in_per_1m or 0)
                     + raw.completion_tokens * (self.cfg.price_out_per_1m or 0)) / 1e6)
        parsed = parse_json_reply(raw.text)
        usage = {"prompt_tokens": raw.prompt_tokens, "completion_tokens": raw.completion_tokens,
                 "cost_usd": round(cost, 6)}
        meta = {"models": {k: v for k, v in (("primary", self.cfg.primary), ("escalation", self.cfg.escalation),
                                              ("fast", self.cfg.fast)) if v},
                "settings": self.cfg.settings}
        self.cache.put(key, {"response": parsed, "model": model, "usage": usage, "question_id": question_id,
                             "role": role}, meta)
        with self._lock:
            self.spent += cost
            self.live_calls += 1
        self._ledger(question_id, role, model, raw.prompt_tokens, raw.completion_tokens, cost, False)
        return Reply(parsed, model, raw.prompt_tokens, raw.completion_tokens, cost, False)

    def _ledger(self, qid, role, model, p_tok, c_tok, cost, hit) -> None:
        try:
            with self._lock:
                new = not self.ledger_path.exists()
                self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
                with self.ledger_path.open("a", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=LEDGER_FIELDS)
                    if new:
                        w.writeheader()
                    w.writerow({"timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                "question_id": qid, "role": role, "model": model, "prompt_tokens": p_tok,
                                "completion_tokens": c_tok, "cost_usd": f"{cost:.6f}", "cache_hit": hit})
        except OSError:
            pass  # a read-only checkout must not stop an offline replay


def _user_message(context: str, question: str, feedback: str) -> str:
    msg = f"EVIDENCE:\n{context}\n\nQUESTION: {question}\n"
    if feedback:
        msg += f"\nVERIFIER FEEDBACK on your previous answer (fix every point):\n{feedback}\n"
    return msg


# ------------------------------------------------------------------ cost summary


def write_cost_summary(cache: Cache, llm: LLM | None = None, path: Path | None = None) -> Path:
    """Committed summary derived from the cache: calls, tokens, USD per question, plus a TOTAL row.

    `cache_hits` in the TOTAL row is this run's count (0 for rows, which describe cached generation).
    """
    path = Path(path or config.COST_SUMMARY_PATH)
    per_q: dict[str, dict[str, Any]] = {}
    for e in cache.entries.values():
        q = e.get("question_id") or "?"
        u = e.get("usage", {})
        row = per_q.setdefault(q, {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0})
        row["calls"] += 1
        row["prompt_tokens"] += u.get("prompt_tokens", 0)
        row["completion_tokens"] += u.get("completion_tokens", 0)
        row["cost_usd"] += u.get("cost_usd", 0.0)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["question_id", "calls", "cache_hits", "prompt_tokens", "completion_tokens", "cost_usd"]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        tot = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0}
        for q in sorted(per_q):
            r = per_q[q]
            w.writerow({"question_id": q, "cache_hits": 0, **{k: (f"{v:.6f}" if k == "cost_usd" else v) for k, v in r.items()}})
            for k in tot:
                tot[k] += r[k]
        n_q = len([q for q in per_q if q != "?"]) or 1
        w.writerow({"question_id": f"TOTAL (cost per question ${tot['cost_usd'] / n_q:.6f})",
                    "cache_hits": llm.cache_hits if llm else 0,
                    **{k: (f"{v:.6f}" if k == "cost_usd" else v) for k, v in tot.items()}})
    return path
