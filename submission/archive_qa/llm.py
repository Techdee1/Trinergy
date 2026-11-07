"""LLM access: OpenRouter client, deterministic disk cache, offline mode, cost ledger, spend guard.

Reviewers rerun the notebook WITHOUT an API key, so every answer must be replayable from
`indexes/llm_cache.json`. A cache miss in offline mode raises `CacheMiss`; nothing ever
silently falls back to abstaining.

Layers
  Backend      one real HTTP call (OpenRouterBackend) or a scripted double (FakeLLM)
  LLM          cache lookup -> (live only) budget guard -> backend with retries -> cache + ledger

The cache key is sha256(system prompt + context + question + feedback + model + settings [+ run]).
`settings` is per role (primary / escalation) and includes max_tokens, reasoning, provider pin, response format
and the prompt's sha256. `run` salts the key of the second primary call (disagreement check): same request,
separate cache entry. Cache entries store the parsed response, model, usage and question id, never the context.
Models and settings used are also saved in the cache's `_meta`, so an offline run reproduces the same keys
without needing LLM_* in the environment.

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
from .prompts import ANSWER_SCHEMA, prompt_sha

KEY_ENV_NAMES = ("OpenRouter_Key", "OPENROUTER_API_KEY")
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MAX_TOKENS = config.LLM_PRIMARY_MAX_TOKENS_DEFAULT
REASONING_EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh")
LEDGER_FIELDS = ["timestamp", "question_id", "role", "model", "prompt_tokens",
                 "completion_tokens", "cost_usd", "cache_hit"]


class CacheMiss(RuntimeError):
    """Offline mode and the answer is not in the committed cache."""


class BudgetExceeded(RuntimeError):
    """LLM_BUDGET_USD reached for this run."""


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


def _env_set(name: str, dotenv: dict[str, str]) -> str | None:
    """Like _env but an explicitly empty value is returned as "" (so LLM_PROVIDER= can switch the pin off)."""
    if name in os.environ:
        return os.environ[name].strip()
    return dotenv[name].strip() if name in dotenv else None


@dataclass
class LLMConfig:
    api_key: str | None = field(default=None, repr=False)  # never shown
    primary: str | None = None
    escalation: str | None = None
    fast: str | None = None
    budget_usd: float = 3.00
    concurrency: int = config.LLM_CONCURRENCY_DEFAULT
    max_tokens: int = config.LLM_PRIMARY_MAX_TOKENS_DEFAULT                    # primary model (LLM_MAX_TOKENS)
    reasoning: str | None = config.LLM_PRIMARY_REASONING_DEFAULT              # primary model (LLM_REASONING)
    escalation_max_tokens: int = config.LLM_ESCALATION_MAX_TOKENS_DEFAULT
    retry_max_tokens: int = config.LLM_RETRY_MAX_TOKENS_DEFAULT              # primary retry after truncation / bad JSON
    multi_max_tokens: int = config.LLM_MULTI_MAX_TOKENS_DEFAULT              # primary calls for multi_report / archive_wide
    escalation_reasoning: str | None = config.LLM_ESCALATION_REASONING_DEFAULT
    provider: tuple[str, ...] = (config.LLM_PROVIDER_DEFAULT,)               # provider.order pin; () = no pin
    temperature: float = 0.0
    live: bool = False
    price_in_per_1m: float | None = None
    price_out_per_1m: float | None = None

    def role_settings(self, role: str) -> dict:
        """What is sent to the API for a role (and part of its cache key). `reasoning` and `provider` appear
        only when set. The pin never sets require_parameters=true: it makes every Anthropic request 404."""
        esc = role == "escalation"
        d: dict = {"temperature": self.temperature, "max_tokens": self.escalation_max_tokens if esc else self.max_tokens,
                   "response_format": "json_schema"}
        reasoning = self.escalation_reasoning if esc else self.reasoning
        if reasoning:
            d["reasoning"] = reasoning
        if self.provider:
            d["provider"] = {"order": list(self.provider), "allow_fallbacks": False, "require_parameters": False}
        return d

    @property
    def settings(self) -> dict:
        return self.role_settings("primary")

    def describe(self) -> dict:
        """Safe summary: names and booleans only."""
        return {"mode": "live" if self.live else "offline", "key_present": bool(self.api_key),
                "primary": self.primary, "escalation": self.escalation, "fast": self.fast,
                "max_tokens": self.max_tokens, "reasoning": self.reasoning,
                "retry_max_tokens": self.retry_max_tokens, "multi_max_tokens": self.multi_max_tokens,
                "escalation_max_tokens": self.escalation_max_tokens, "escalation_reasoning": self.escalation_reasoning,
                "provider": list(self.provider), "budget_usd": self.budget_usd, "concurrency": self.concurrency}


def load_config(live: bool = False, dotenv_path: Path | None = None) -> LLMConfig:
    """Build the config. `live=False` (default) is offline: the key is ignored and only the cache is used.

    Models, max_tokens, reasoning and provider: environment/.env first, else the values recorded in the cache
    `_meta` (so an offline replay rebuilds exactly the keys the live run wrote), else the code defaults.
    """
    dotenv = load_env_file(dotenv_path or (config.REPO_ROOT / ".env"))
    cache_meta = Cache(config.LLM_CACHE_PATH).meta
    meta = cache_meta.get("models", {})
    rec = cache_meta.get("settings", {})
    rec_p, rec_e = rec.get("primary", {}), rec.get("escalation", {})
    key = next((v for n in KEY_ENV_NAMES if (v := _env(n, dotenv))), None)

    def pick(name: str, recorded, default):
        return _env(name, dotenv) or recorded or default

    rec_order = (rec_p.get("provider") or {}).get("order")
    prov_env = _env_set("LLM_PROVIDER", dotenv)
    provider = (tuple(x.strip() for x in prov_env.split(",") if x.strip()) if prov_env is not None
                else tuple(rec_order) if rec_order is not None else (config.LLM_PROVIDER_DEFAULT,))
    cfg = LLMConfig(
        api_key=key if live else None,
        primary=pick("LLM_MODEL_PRIMARY", meta.get("primary"), config.LLM_MODEL_PRIMARY_DEFAULT),
        escalation=pick("LLM_MODEL_ESCALATION", meta.get("escalation"), config.LLM_MODEL_ESCALATION_DEFAULT),
        fast=_env("LLM_MODEL_FAST", dotenv) or meta.get("fast"),
        max_tokens=int(pick("LLM_MAX_TOKENS", rec_p.get("max_tokens"), config.LLM_PRIMARY_MAX_TOKENS_DEFAULT)),
        reasoning=pick("LLM_REASONING", rec_p.get("reasoning"), config.LLM_PRIMARY_REASONING_DEFAULT),
        escalation_max_tokens=int(pick("LLM_ESCALATION_MAX_TOKENS", rec_e.get("max_tokens"),
                                       config.LLM_ESCALATION_MAX_TOKENS_DEFAULT)),
        retry_max_tokens=int(pick("LLM_RETRY_MAX_TOKENS", (rec.get("retry") or {}).get("max_tokens"),
                                  config.LLM_RETRY_MAX_TOKENS_DEFAULT)),
        multi_max_tokens=int(pick("LLM_MULTI_MAX_TOKENS", (rec.get("multi") or {}).get("max_tokens"),
                                  config.LLM_MULTI_MAX_TOKENS_DEFAULT)),
        escalation_reasoning=pick("LLM_ESCALATION_REASONING", rec_e.get("reasoning"),
                                  config.LLM_ESCALATION_REASONING_DEFAULT),
        provider=provider,
        budget_usd=float(_env("LLM_BUDGET_USD", dotenv) or 3.00),
        concurrency=max(1, int(_env("LLM_CONCURRENCY", dotenv) or config.LLM_CONCURRENCY_DEFAULT)),
        live=bool(live and key),
        price_in_per_1m=float(v) if (v := _env("LLM_PRICE_IN_PER_1M", dotenv)) else None,
        price_out_per_1m=float(v) if (v := _env("LLM_PRICE_OUT_PER_1M", dotenv)) else None,
    )
    for name, n in (("LLM_MAX_TOKENS", cfg.max_tokens), ("LLM_ESCALATION_MAX_TOKENS", cfg.escalation_max_tokens),
                    ("LLM_RETRY_MAX_TOKENS", cfg.retry_max_tokens), ("LLM_MULTI_MAX_TOKENS", cfg.multi_max_tokens)):
        if n < 1:
            raise ValueError(f"{name} must be a positive integer, got {n}")
    for name, val in (("LLM_REASONING", cfg.reasoning), ("LLM_ESCALATION_REASONING", cfg.escalation_reasoning)):
        if val and val.lower() not in REASONING_EFFORTS:
            raise ValueError(f"{name} must be one of {list(REASONING_EFFORTS)}, got {val!r}")
    cfg.reasoning = cfg.reasoning.lower() if cfg.reasoning else None
    cfg.escalation_reasoning = cfg.escalation_reasoning.lower() if cfg.escalation_reasoning else None
    if live and not key:
        raise RuntimeError(f"Live mode needs an API key in env var {KEY_ENV_NAMES[0]} (or {KEY_ENV_NAMES[1]}).")
    return cfg


# ------------------------------------------------------------------ backends


@dataclass
class RawResponse:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float | None = None
    finish_reason: str | None = None   # "length" = the reply hit max_tokens


class Backend(Protocol):
    def chat(self, system: str, user: str, model: str, max_tokens: int, temperature: float,
             reasoning: str | None = None, provider: dict | None = None) -> RawResponse: ...


class TransientError(RuntimeError):
    """429 or 5xx: worth retrying."""


class OpenRouterBackend:
    """OpenAI-compatible chat completions through OpenRouter (requests only)."""

    def __init__(self, api_key: str, timeout: float = 90.0, max_attempts: int = 3, backoff: float = 2.0):
        self._key = api_key
        self.timeout, self.max_attempts, self.backoff = timeout, max_attempts, backoff

    def _scrub(self, text: str) -> str:
        return text.replace(self._key, "***") if self._key else text

    def _once(self, system: str, user: str, model: str, max_tokens: int, temperature: float,
              reasoning: str | None = None, provider: dict | None = None) -> RawResponse:
        import requests

        body = {
            "model": model, "temperature": temperature, "max_tokens": max_tokens,
            "response_format": {"type": "json_schema", "json_schema": {"name": "answer", "strict": True,
                                                                        "schema": ANSWER_SCHEMA}},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if reasoning:
            body["reasoning"] = {"effort": reasoning}
        if provider:  # e.g. {"order": ["Anthropic"], "allow_fallbacks": False, "require_parameters": False}
            body["provider"] = provider
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
            finish_reason=data["choices"][0].get("finish_reason"),
            text=(data["choices"][0]["message"].get("content") or ""),
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            cost_usd=float(usage["cost"]) if usage.get("cost") is not None else None,
        )

    def chat(self, system, user, model, max_tokens, temperature=0.0, reasoning=None, provider=None) -> RawResponse:
        last: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                return self._once(system, user, model, max_tokens, temperature, reasoning, provider)
            except TransientError as e:  # retry ONLY 429/5xx
                last = e
                if attempt + 1 < self.max_attempts:
                    time.sleep(self.backoff * (2 ** attempt))
        raise RuntimeError(f"OpenRouter still failing after {self.max_attempts} attempts: {last}")


def _takes_max_tokens(fn: Callable) -> bool:
    import inspect
    return len(inspect.signature(fn).parameters) >= 4


class FakeLLM:
    """Test double. `script` is a dict {substring-of-user-message: reply} or a callable
    (system, user, model) -> reply, where a reply is a dict (JSON-encoded) or a str."""

    def __init__(self, script: dict | Callable | None = None, tokens: tuple[int, int] = (100, 50), cost: float = 0.001):
        self.script, self.tokens, self.cost = script or {}, tokens, cost
        self.calls: list[dict] = []

    def chat(self, system, user, model, max_tokens, temperature=0.0, reasoning=None, provider=None) -> RawResponse:
        self.calls.append({"system": system, "user": user, "model": model, "max_tokens": max_tokens,
                           "reasoning": reasoning, "provider": provider, "temperature": temperature})
        finish = "stop"
        if callable(self.script):
            reply = self.script(system, user, model, max_tokens) if _takes_max_tokens(self.script) \
                else self.script(system, user, model)
        else:
            reply = next((v for k, v in self.script.items() if k in user), None)
            if reply is None:
                reply = {"status": "abstain", "answer": "fake", "cited_ids": [], "rationale": "fake"}
        if isinstance(reply, tuple):  # (reply, finish_reason), e.g. ('{"status": "ans', "length")
            reply, finish = reply
        text = reply if isinstance(reply, str) else json.dumps(reply)
        return RawResponse(text, *self.tokens, cost_usd=self.cost, finish_reason=finish)


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


def cache_key(system: str, context: str, question: str, feedback: str, model: str, settings: dict,
              run: str = "") -> str:
    h = hashlib.sha256()
    parts = (system, context, question, feedback, model, json.dumps(settings, sort_keys=True))
    for part in parts + ((f"run={run}",) if run else ()):  # run salts the key only when given
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
    finish_reason: str | None = None

    @property
    def truncated_or_invalid(self) -> bool:
        """The reply hit max_tokens, or is not valid JSON (a truncated JSON object never parses)."""
        return self.finish_reason in ("length", "max_tokens") or (
            isinstance(self.parsed, dict) and "__unparsed__" in self.parsed)


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
            question_id: str = "", role: str = "primary", run: str = "", max_tokens: int | None = None) -> Reply:
        """`role` ("escalation", else primary settings) picks the settings; `run` ("2") gives a repeat call its own
        cache entry. `max_tokens` overrides the role's cap (the truncation retry); it is part of the key."""
        rs = self.cfg.role_settings("escalation" if role == "escalation" else "primary")
        if max_tokens:
            rs = {**rs, "max_tokens": max_tokens}
        key = cache_key(system, context, question, feedback, model, {**rs, "prompt_sha": prompt_sha(system)}, run)
        hit = self.cache.get(key)
        if hit is not None:
            u = hit.get("usage", {})
            with self._lock:
                self.cache_hits += 1
            self._ledger(question_id, role, model, 0, 0, 0.0, True)
            return Reply(hit["response"], hit["model"], u.get("prompt_tokens", 0),
                         u.get("completion_tokens", 0), u.get("cost_usd", 0.0), True, hit.get("finish_reason"))
        if self.backend is None:
            raise CacheMiss(
                f"No cached LLM answer for question {question_id or '?'} (role={role}, model={model}). "
                "Offline mode only replays submission/indexes/llm_cache.json. To generate it, run the notebook "
                "with LIVE = True and an API key in the OpenRouter_Key environment variable.")
        with self._lock:
            if self.spent >= self.cfg.budget_usd:
                raise BudgetExceeded(f"Spend guard: ${self.spent:.4f} >= LLM_BUDGET_USD ${self.cfg.budget_usd:.2f}")
        raw = self.backend.chat(system, _user_message(context, question, feedback), model, rs["max_tokens"],
                                rs["temperature"], rs.get("reasoning"), rs.get("provider"))
        cost = raw.cost_usd
        if cost is None:  # provider did not report cost: use env prices if given
            cost = ((raw.prompt_tokens * (self.cfg.price_in_per_1m or 0)
                     + raw.completion_tokens * (self.cfg.price_out_per_1m or 0)) / 1e6)
        parsed = parse_json_reply(raw.text)
        usage = {"prompt_tokens": raw.prompt_tokens, "completion_tokens": raw.completion_tokens,
                 "cost_usd": round(cost, 6)}
        meta = {"models": {k: v for k, v in (("primary", self.cfg.primary), ("escalation", self.cfg.escalation),
                                              ("fast", self.cfg.fast)) if v},
                "settings": {"primary": self.cfg.role_settings("primary"),
                             "escalation": self.cfg.role_settings("escalation"),
                             "retry": {"max_tokens": self.cfg.retry_max_tokens},
                             "multi": {"max_tokens": self.cfg.multi_max_tokens}},
                "prompt_sha": prompt_sha(system)}
        self.cache.put(key, {"response": parsed, "model": model, "usage": usage, "question_id": question_id,
                             "role": role, "finish_reason": raw.finish_reason}, meta)
        with self._lock:
            self.spent += cost
            self.live_calls += 1
        self._ledger(question_id, role, model, raw.prompt_tokens, raw.completion_tokens, cost, False)
        return Reply(parsed, model, raw.prompt_tokens, raw.completion_tokens, cost, False, raw.finish_reason)

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
