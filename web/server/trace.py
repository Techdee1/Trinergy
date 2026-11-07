"""Trace capture WITHOUT touching submission/.

The pipeline (`archive_qa.answer`) calls route_question / build_context / verify through its own module globals and the
model through the `llm` object it is handed. We observe those calls from outside:

* `install()` replaces the three module globals by pass-through wrappers. A wrapper does nothing unless a Tracer is
  active in the current context (ContextVar), calls the original with the SAME arguments and returns its result
  unchanged, so predictions, cache keys and contexts are byte-identical (web/server/tests/test_unchanged.py proves it).
* `TracedLLM` wraps the LLM object for one request and records every `ask` (including cache misses).

Events are emitted when the thing happens; the SSE stream is a live view of `Tracer.events`, so a stage that did not
occur can never be emitted.
"""

from __future__ import annotations

import contextvars
import logging
import threading
import time
from typing import Any, Callable

from submission.archive_qa import answer as _answer
from submission.archive_qa.llm import BudgetExceeded, CacheMiss

from . import tracebuild as tb
from .safety import redact

_CURRENT: contextvars.ContextVar["Tracer | None"] = contextvars.ContextVar("web_server_tracer", default=None)
_ORIG: dict[str, Callable] = {}
_lock = threading.Lock()
_installed = 0
_handler: "_WarnHandler | None" = None


class Tracer:
    def __init__(self, rec_index: dict[str, tuple[str, str]], sink: Callable[[dict], None] | None = None):
        self.t0 = time.perf_counter()
        self.rec_index = rec_index
        self.sink = sink
        self.events: list[dict] = []
        self.reports: list = []
        self.route = None
        self.contexts: list[dict] = []     # {"trace": dict, "ctx": Context, "text": str}
        self.calls: list[dict] = []        # model-call dicts + "_reply"
        self.verifies: list[dict] = []
        self.warnings: list[dict] = []
        self._second_pass_started = False

    # -- events
    def now_ms(self) -> int:
        return int((time.perf_counter() - self.t0) * 1000)

    def emit(self, stage: str, **data: Any) -> dict:
        ev = {"seq": len(self.events) + 1, "stage": stage, "t_ms": self.now_ms(), "data": data}
        self.events.append(ev)
        if self.sink and stage != "result":      # the result event carries the full response and is sent by the caller
            try:
                self.sink(ev)
            except Exception:  # noqa: BLE001 - a broken client must not break the pipeline
                pass
        return ev

    def warn(self, code: str, message: str) -> None:
        message = redact(message)
        if any(w["code"] == code for w in self.warnings):
            return
        self.warnings.append({"code": code, "message": message})
        self.emit("warning", code=code, message=message)

    # -- observations
    def on_route(self, res, reports) -> None:
        self.route, self.reports = res, reports
        self.emit("route", **tb.router_trace(res, reports))

    def on_context(self, ctx, enrich_mode: str) -> None:
        name = "second_pass" if enrich_mode == "full" else "first_pass"
        t = tb.context_trace(ctx, name, self.rec_index)
        self.contexts.append({"trace": t, "ctx": ctx, "text": ctx.text})
        self.emit("context_built", **t)
        if ctx.agg:
            self.emit("aggregates_added", pass_name=name, aggregates=t["aggregates"])

    def context_pass_of(self, text: str) -> str | None:
        for c in reversed(self.contexts):
            if c["text"] == text:
                return c["trace"]["pass_name"]
        return None

    def on_verify(self, parsed, ctx, result) -> None:
        target, tcall = "unknown", None
        for c in self.calls:
            rep = c.get("_reply")
            if rep is not None and rep.parsed is parsed:
                target, tcall = f"model_call {c['n']} ({c['purpose']})", c["n"]
        if tcall is None and isinstance(parsed, dict):
            for c in self.calls:      # the citation-repair re-check verifies a COPY of an answer with other cited_ids
                rep = c.get("_reply")
                if rep is not None and isinstance(rep.parsed, dict) and rep.parsed.get("answer") == parsed.get("answer"):
                    target, tcall = "citation_repair", c["n"]
        status = parsed.get("status") if isinstance(parsed, dict) else None
        checks = tb.classify_checks(parsed, ctx.ids, ctx.absent, ctx.agg, list(result.failures), list(result.flags))
        v = {"n": len(self.verifies) + 1, "target": target, "target_call": tcall,
             "reply_status": status if isinstance(status, str) else None, "ok": bool(result.ok), "checks": checks,
             "failures": list(result.failures), "flags": list(result.flags), "flagged_ids": list(result.flagged_ids)}
        self.verifies.append(v)
        self.emit("verify", **v)


# ------------------------------------------------------------------ module-global wrappers


def _wrap_route(orig):
    def route_question(*a, **k):
        res = orig(*a, **k)
        t = _CURRENT.get()
        if t is not None:
            reports = a[1] if len(a) > 1 else k.get("reports")
            t.on_route(res, reports if reports is not None else [])
        return res
    return route_question


def _wrap_build_context(orig):
    def build_context(*a, **k):
        t = _CURRENT.get()
        mode = k.get("enrich_mode", a[5] if len(a) > 5 else "auto")
        if t is not None and mode == "full":
            t.emit("second_pass", reason="the first pass abstained, was partial, or abstained although a matching line exists; "
                                         "retrying once with the enriched context (aggregates, field catalogue, full records "
                                         "of the named wells)")
        ctx = orig(*a, **k)
        if t is not None:
            t.on_context(ctx, mode)
        return ctx
    return build_context


def _wrap_verify(orig):
    def verify(parsed, context, *a, **k):
        res = orig(parsed, context, *a, **k)
        t = _CURRENT.get()
        if t is not None:
            t.on_verify(parsed, context, res)
        return res
    return verify


class _WarnHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        t = _CURRENT.get()
        if t is None or record.levelno < logging.WARNING:
            return
        msg = record.getMessage()
        t.warn("provider_fallback" if "pinned provider" in msg else "pipeline_warning", msg)


def install() -> None:
    global _installed, _handler
    with _lock:
        if _installed == 0:
            for name, wrap in (("route_question", _wrap_route), ("build_context", _wrap_build_context),
                               ("verify", _wrap_verify)):
                _ORIG[name] = getattr(_answer, name)
                setattr(_answer, name, wrap(_ORIG[name]))
            _handler = _WarnHandler(level=logging.WARNING)
            logging.getLogger("archive_qa").addHandler(_handler)
        _installed += 1


def uninstall() -> None:
    global _installed, _handler
    with _lock:
        _installed = max(0, _installed - 1)
        if _installed == 0:
            for name, fn in _ORIG.items():
                setattr(_answer, name, fn)
            _ORIG.clear()
            if _handler is not None:
                logging.getLogger("archive_qa").removeHandler(_handler)
                _handler = None


def original(name: str) -> Callable:
    """The unwrapped pipeline function (used for the server's own pre-checks so they emit no events)."""
    return _ORIG.get(name) or getattr(_answer, name)


class activate:
    """`with activate(tracer):` makes wrappers record into `tracer` in this thread/context."""

    def __init__(self, tracer: Tracer):
        self.tracer, self._tok = tracer, None

    def __enter__(self):
        self._tok = _CURRENT.set(self.tracer)
        return self.tracer

    def __exit__(self, *exc):
        _CURRENT.reset(self._tok)


# ------------------------------------------------------------------ LLM proxy


def _purpose(role: str, run: str, feedback: str) -> tuple[str, str | None]:
    """(human purpose, escalation kind or None). The kind comes from the exact feedback prefixes in answer.py."""
    if role == "escalation":
        if feedback.startswith("ARBITRATION") and "previous arbitration answer failed" in feedback:
            return "arbitration retry (the arbiter's first answer failed verification)", "arbitrate_retry"
        if feedback.startswith("ARBITRATION"):
            return "arbitration of two disagreeing primary runs", "arbitrate"
        if feedback.startswith("PARTIAL"):
            return "escalation of a partial answer", "partial"
        return "escalation after the verifier rejected the first answer", "verifier"
    base = {"primary": "primary run 1", "primary_run2": "primary run 2 (independent repeat, disagreement check)",
            "primary_second_pass": "primary run on the enriched second-pass context"}.get(role)
    if base:
        return base, None
    if role.endswith("_retry"):
        return "same-model retry after a truncated or invalid reply (" + role[:-6] + ")", None
    return role, None


class TracedLLM:
    def __init__(self, llm, tracer: Tracer):
        self._llm, self.tracer = llm, tracer

    def __getattr__(self, name):
        return getattr(self._llm, name)

    def ask(self, system, context, question, model, *, feedback="", question_id="", role="primary", run="", max_tokens=None):
        t = self.tracer
        purpose, kind = _purpose(role, run, feedback)
        cpass = t.context_pass_of(context)
        if kind in ("arbitrate", "arbitrate_retry"):
            t.emit("arbitrate", retry=kind == "arbitrate_retry", model=model, context_pass=cpass,
                   reason="two independent primary runs differ in status or key numbers" if kind == "arbitrate"
                   else "the arbiter's answer failed verification; one more attempt with the verifier's message")
        elif kind in ("verifier", "partial"):
            t.emit("escalate", trigger="partial_answer" if kind == "partial" else "verifier_failed_or_missed_evidence",
                   model=model, context_pass=cpass,
                   reason=(feedback[:300] if kind == "verifier" else "the final answer was partial; one escalation"))
        n = len(t.calls) + 1
        base = {"n": n, "purpose": purpose, "role": role, "run": run, "model": model, "context_pass": cpass,
                "max_tokens": max_tokens, "feedback": feedback[:400] if feedback else None, "_reply": None}
        t0 = time.perf_counter()
        try:
            reply = self._llm.ask(system, context, question, model, feedback=feedback, question_id=question_id,
                                  role=role, run=run, max_tokens=max_tokens)
        except (CacheMiss, BudgetExceeded, Exception) as e:  # noqa: BLE001 - recorded, then re-raised unchanged
            outcome = "cache_miss_offline" if isinstance(e, CacheMiss) else "budget_blocked" if isinstance(e, BudgetExceeded) else "error"
            rec = {**base, "outcome": outcome, "cache_hit": False, "prompt_tokens": 0, "completion_tokens": 0,
                   "latency_ms": int((time.perf_counter() - t0) * 1000), "cost_usd": 0.0, "incurred_usd": 0.0,
                   "finish_reason": None, "reply_status": None, "reply_cited": [],
                   "error": redact(f"{type(e).__name__}: {e}")[:300]}
            t.calls.append(rec)
            t.emit("model_call", **{k: v for k, v in rec.items() if not k.startswith("_")})
            raise
        p = reply.parsed if isinstance(reply.parsed, dict) else {}
        rec = {**base, "outcome": "cache_hit" if reply.cache_hit else "live", "cache_hit": bool(reply.cache_hit),
               "prompt_tokens": int(reply.prompt_tokens), "completion_tokens": int(reply.completion_tokens),
               "latency_ms": int((time.perf_counter() - t0) * 1000), "cost_usd": float(reply.cost_usd or 0.0),
               "incurred_usd": 0.0 if reply.cache_hit else float(reply.cost_usd or 0.0),
               "finish_reason": reply.finish_reason,
               "reply_status": p.get("status") if isinstance(p.get("status"), str) else None,
               "reply_cited": [c for c in (p.get("cited_ids") or []) if isinstance(c, str)] if isinstance(p.get("cited_ids"), list) else [],
               "error": None}
        rec["_reply"] = reply
        t.calls.append(rec)
        t.emit("model_call", **{k: v for k, v in rec.items() if not k.startswith("_")})
        if not reply.cache_hit and getattr(getattr(self._llm, "backend", None), "_pin_disabled", False):
            t.warn("provider_fallback", "the pinned provider (Anthropic) is unavailable for this key; the call used OpenRouter's "
                                        "default routing for the same model")
        return reply
