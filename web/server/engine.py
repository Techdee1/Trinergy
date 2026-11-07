"""The engine: loads the archive once, runs a question through the SAME function the notebook uses
(`archive_qa.answer.answer_question`), and turns the result plus the captured events into the API response.

Data: ONLY the data pack (web/server/data) is read; no organiser XML/PDF file is opened (see build_data.py).
Caches: answers are read from the committed cache, then the pack's read-only unseen-set cache, then the server's runtime
cache; new answers are written ONLY to the runtime cache (RUNTIME_CACHE_DIR). Nothing under submission/ is written.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from pathlib import Path

import pandas as pd

from submission.archive_qa import answer as qa, config, enrich, llm as qllm, write
from submission.archive_qa.verify import confidence
from submission.archive_qa.xmlonly import xml_only_paths

from . import trace as tr
from . import tracebuild as tb
from .datapack import ATTRIBUTION, DataPack
from .guards import SpendLedger
from .safety import redact, register_secret
from .schemas import QuestionDetail
from .settings import Settings

log = logging.getLogger("web.server.engine")
ARCHIVE_TERMS = {enrich._stem(w) for w in ("wellbore", "wellbores", "archive")}      # questions about the archive itself
GENERIC_TOPICS = {"summary_24h", "activity", "forecast_24h"}     # router topics that name no specific field ("what happened")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class AskDisabled(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


class StackedCache:
    """Read-through over several caches; writes go only to `writable`. Same interface the pipeline's LLM expects."""

    def __init__(self, base: qllm.Cache, readonly: list[qllm.Cache], writable: qllm.Cache):
        self.layers = [base, *readonly, writable]
        self.writable = writable

    def get(self, key: str):
        for c in self.layers:
            hit = c.get(key)
            if hit is not None:
                return hit
        return None

    def put(self, key: str, entry: dict, meta: dict | None = None) -> None:
        self.writable.put(key, entry, meta)

    @property
    def entries(self) -> dict:
        out: dict = {}
        for c in reversed(self.layers):
            out.update(c.entries)
        return out

    @property
    def meta(self) -> dict:
        out: dict = {}
        for c in reversed(self.layers):
            out.update(c.meta)
        return out


class ReplayLLM(qllm.LLM):
    """Offline replays (warm-up, GET endpoints) keep no ledger: they would only append cache-hit rows at every start."""

    def _ledger(self, *a, **k) -> None:
        return None


def _pin_data_root(root: Path) -> None:
    """Point the pipeline's `config.DATA_ROOT` at the pack's manifest-only root. The only raw-data read left in the answering path is
    `answer.manifest_summary` (the early-abstain text quotes document_manifest.csv); the pack carries that one file."""
    old = os.environ.get("NAPE_DATA_ROOT")
    os.environ["NAPE_DATA_ROOT"] = str(root)
    try:
        config._cache.pop("root", None)
        _ = config.DATA_ROOT
    finally:
        if old is None:
            os.environ.pop("NAPE_DATA_ROOT", None)
        else:
            os.environ["NAPE_DATA_ROOT"] = old


def clean_question(text: str) -> str:
    return _CONTROL.sub(" ", text).strip()


class Engine:
    def __init__(self, settings: Settings | None = None, backend=None):
        self.s = settings or Settings()
        self.s.runtime_dir.mkdir(parents=True, exist_ok=True)
        tr.install()
        self.pack = DataPack(self.s.data_dir)
        _pin_data_root(self.pack.manifest_root)
        self.records = self.pack.records
        self.reports = self.pack.reports
        self.field_names = self._field_names()
        self.rec_index = {r: (s, f) for r, s, f in zip(self.records["record_id"], self.records["section"], self.records["source_file"])}
        self.by_id = self.records.set_index("record_id", drop=False)
        # --- LLM: hybrid (live iff a key exists); cache layers; ledger in the runtime dir, not in logs/
        name, key = qllm.find_key()
        register_secret(key)
        self.key_present = bool(key)
        self.cfg = qllm.load_config()
        self.spend = SpendLedger(self.s.runtime_dir / "spend.json", self.s.server_budget_usd)
        self.cfg.budget_usd = max(0.0, self.spend.remaining)          # the pipeline's own guard, aligned with ours
        ro = [qllm.Cache(self.pack.gen_cache)] if self.pack.gen_cache.is_file() else []
        self.runtime_cache = qllm.Cache(self.s.runtime_dir / "llm_cache_runtime.json")
        self.cache = StackedCache(qllm.Cache(config.LLM_CACHE_PATH), ro, self.runtime_cache)
        ledger = self.s.runtime_dir / "ledger.csv"
        offline_cfg = qllm.load_config(live=False)
        self.replay_llm = ReplayLLM(offline_cfg, None, self.cache, ledger_path=ledger)
        if backend is not None:                      # tests: a scripted backend stands in for OpenRouter
            self.cfg.live, self.key_present = True, True
        elif self.cfg.live:
            backend = qllm.OpenRouterBackend(self.cfg.api_key)
        self.llm = qllm.LLM(self.cfg, backend, self.cache, ledger_path=ledger) if backend is not None else self.replay_llm
        # --- catalog + memo
        self.catalog = self.pack.catalog
        self._examples: list[str] | None = None
        self.text_to_id = {c["question"].strip(): c["id"] for c in self.catalog}
        self.memo: dict[str, QuestionDetail] = {}
        self.stats = {k: {"requests": 0, "model_calls": 0, "cache_hits": 0, "live_calls": 0} for k in ("replay", "ask")}
        self._lock = threading.Lock()
        self.asks_dir = self.s.runtime_dir / "asks"
        self.warm_seconds: float | None = None

    # ------------------------------------------------------------------ loading
    def _field_names(self) -> list[str]:
        """Every field name the archive has (record fields and row attributes), for the vagueness check."""
        return sorted(set(self.records["field"]) | {k for a in self.records["attrs"].dropna() for k in json.loads(a)})

    def warm(self) -> None:
        """Replay every catalog question offline (no key, no spend) so /questions is instant."""
        t0 = time.perf_counter()
        for c in self.catalog:
            self.replayed(c["id"])
        self.warm_seconds = round(time.perf_counter() - t0, 1)
        log.info("warmed %d questions in %.1fs", len(self.catalog), self.warm_seconds)

    def close(self) -> None:
        tr.uninstall()

    # ------------------------------------------------------------------ running
    def entry(self, qid: str) -> dict | None:
        return next((c for c in self.catalog if c["id"] == qid), None)

    def replayed(self, qid: str) -> QuestionDetail | None:
        """A catalog question answered OFFLINE (cache only). Memoised; never spends."""
        if qid in self.memo:
            return self.memo[qid]
        c = self.entry(qid)
        if c is None:
            return self.load_ask(qid)
        d = self.run(c["id"], c["question"], c["set"], live=False)
        self._count("replay", d)
        self.memo[qid] = d
        return d

    def _is_vague(self, question: str, res) -> bool:
        """No recognisable well, date or field term: the router found no well/date/period, its topics are at most the generic
        narrative ones ("what happened"), no archive field name is covered by the question and it does not ask about the archive itself
        (wellbores / archive). (Cached questions are exempt, see _gate.)"""
        if res.mode != "archive_wide" or res.early_abstain or res.wells or res.dates or set(res.sections) - GENERIC_TOPICS:
            return False
        if any(enrich.field_matches(n, question) for n in self.field_names):
            return False
        return not (set(enrich.content_terms(question)) & ARCHIVE_TERMS)

    def _gate(self, qid: str, question: str):
        """Clarification gate: a vague question WITHOUT a cached answer gets a friendly clarification and no model call
        (the pipeline would otherwise hand the whole archive to a model: cost, and a guess). A cached answer always wins: the
        probe is un-traced and offline, so it emits no events and spends nothing."""
        res = tr.original("route_question")(question, self.reports)
        if not self._is_vague(question, res):
            return None
        probe = qa.answer_question(qid, question, self.records, self.reports, self.replay_llm, dump=False)
        return res if probe.status == "not_evaluated" else None

    def clarification_examples(self) -> list[str]:
        """Three real, answered and verified questions of the catalog (one per kind), so the examples are always answerable."""
        if self._examples is None:
            picks: list[str] = []
            want = [("challenge", ("single_report",)), ("challenge", ("multi_report", "archive_wide")), ("unseen", ("single_report",))]
            for qset, modes in want:
                for c in self.catalog:
                    d = self.replayed(c["id"]) if c["set"] == qset else None
                    if d and d.status == "answered" and d.verified and d.router_mode in modes and c["question"] not in picks:
                        picks.append(c["question"])
                        break
            self._examples = picks
        return self._examples

    def _gate_answer(self, qid: str, question: str, res, tracer: tr.Tracer) -> qa.Answer:
        examples = self.clarification_examples()
        msg = ("I could not tell what to look up: the question names no well, no report date and no field of the daily drilling "
               "reports (such as depth, casing, mud, survey, bit, activities or summaries). Name a well and a date, or a field, "
               "and ask again.")
        tracer.on_route(res, self.reports)
        tracer.emit("gate", gate="needs_clarification", message=msg, examples=examples)
        text = msg + (" For example: " + " ".join(f"({i}) {e}" for i, e in enumerate(examples, 1)) if examples else "")
        a = qa.Answer(qid, question, "abstain", text, [], "NEEDS CLARIFICATION: " + res.reason,
                      confidence("abstain", 0, "archive_wide", True, early_abstain=True),
                      notes=["clarification gate: no recognisable well, date or field term and no cached answer; no model call"],
                      mode="archive_wide", verified=True, early_abstain=True,
                      evidence_extra="Nothing was looked up: the question names no well, date or field")
        a.clarification_examples = examples          # picked up by _detail
        return a

    def run(self, qid: str, question: str, qset: str, *, live: bool, sink=None) -> QuestionDetail:
        tracer = tr.Tracer(self.rec_index, sink)
        client = self.llm if live else self.replay_llm
        gate = None
        res = self._gate(qid, question)            # before activate(): the probe must leave no trace
        with tr.activate(tracer):
            if res is not None:
                ans = self._gate_answer(qid, question, res, tracer)
                gate = "needs_clarification"
            else:
                try:
                    ans = qa.answer_question(qid, question, self.records, self.reports, tr.TracedLLM(client, tracer), dump=False)
                except Exception as e:  # noqa: BLE001 - same policy as answer_all: a failed model call is NOT EVALUATED, never a guess
                    log.warning("question %s failed: %s", qid, self.safe_error(e))
                    tracer.warn("model_call_failed", self.safe_error(e))
                    ans = qa.not_evaluated(qid, question, f"NOT EVALUATED: the model call failed ({type(e).__name__})")
        detail = self._detail(qid, qset, question, ans, tracer, gate)
        return detail

    def _count(self, kind: str, d: QuestionDetail) -> None:
        t = d.trace.totals
        with self._lock:
            st = self.stats[kind]
            st["requests"] += 1
            st["model_calls"] += t.model_calls
            st["cache_hits"] += t.cache_hits
            st["live_calls"] += t.live_calls

    def ask(self, question: str, sink=None) -> QuestionDetail:
        """POST /ask: hybrid (cache first, live if a key exists and budget remains). Same function the notebook uses."""
        question = clean_question(question)
        qid = self.text_to_id.get(question) or "ASK-" + hashlib.sha256(question.encode()).hexdigest()[:8]
        entry = self.entry(qid)
        qset = entry["set"] if entry else "adhoc"
        budget_ok = self.spend.remaining > 0
        live = self.key_present and budget_ok
        detail = self.run(qid, question, qset, live=live, sink=sink)
        self._count("ask", detail)
        incurred = detail.trace.totals.incurred_cost_usd
        self.spend.add(incurred)
        if detail.status == "not_evaluated" and self.key_present and not budget_ok:
            raise AskDisabled("budget_exhausted", f"The server's live-model budget (SERVER_BUDGET_USD=${self.s.server_budget_usd:.2f}) "
                                                   "is used up, so only cached questions can be answered. This question has no cached answer.")
        if qset == "adhoc":
            self.save_ask(detail)
        return detail

    # ------------------------------------------------------------------ persisted ad-hoc answers
    def save_ask(self, d: QuestionDetail) -> None:
        self.memo[d.id] = d
        try:
            self.asks_dir.mkdir(parents=True, exist_ok=True)
            (self.asks_dir / f"{d.id}.json").write_text(d.model_dump_json(), encoding="utf-8")
        except OSError:
            pass

    def load_ask(self, qid: str) -> QuestionDetail | None:
        if qid in self.memo:
            return self.memo[qid]
        if not re.fullmatch(r"ASK-[0-9a-f]{8}", qid):
            return None
        try:
            d = QuestionDetail.model_validate_json((self.asks_dir / f"{qid}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        self.memo[qid] = d
        return d

    # ------------------------------------------------------------------ response assembly
    def _cited(self, ans: qa.Answer, question: str) -> list[dict]:
        out = []
        for rid in ans.cited_ids:
            if rid not in self.by_id.index:
                continue
            r = self.by_id.loc[rid]
            xo = xml_only_paths(r, question, ans.answer)
            has_page = pd.notna(r.get("pdf_page")) and isinstance(r.get("pdf_file"), str)
            xml = r["source_file"]
            if xo:
                ev = {"kind": "xml_only", "label": "XML only: " + "; ".join(f"{p} ({k})" for p, k in xo), "xml_file": xml,
                      "xml_only_paths": [p for p, _ in xo], "pdf_file": None, "page": None, "section": None}
            elif has_page:
                sec = r["pdf_section"] if isinstance(r["pdf_section"], str) else None
                ev = {"kind": "pdf", "label": f"{r['pdf_file']} p.{int(r['pdf_page'])}" + (f" ({sec})" if sec else ""),
                      "pdf_file": r["pdf_file"], "page": int(r["pdf_page"]), "section": sec, "xml_file": xml,
                      "page_url": f"/pages/{rid}.png", "boxes_url": f"/pages/{rid}/boxes"}
            else:
                ev = {"kind": "xml_only", "label": "XML only: no PDF page located for this record", "xml_file": xml,
                      "xml_only_paths": [str(r["field"])]}
            out.append({"id": rid, "type": r["section"], "text": r["text"], "report": xml[:-4], "well": r["well"],
                        "report_date": r["report_date"], "evidence": ev})
        for rid, meta in sorted(ans.absent.items()):
            ev_lines = write.absent_evidence(rid, meta)
            out.append({"id": rid, "type": "absent", "report": None, "well": None, "report_date": None,
                        "text": f"Searched {meta['reports']} report(s) and {meta['records']} record(s): no "
                                f"{meta['kind'].replace('_', ' ')} field exists.",
                        "evidence": {"kind": "absent", "label": "; ".join(ev_lines)}})
        return out

    def _detail(self, qid: str, qset: str, question: str, ans: qa.Answer, t: tr.Tracer, gate: str | None) -> QuestionDetail:
        calls = [{k: v for k, v in c.items() if not k.startswith("_")} for c in t.calls]
        live_n = sum(1 for c in calls if c["outcome"] == "live")
        hit_n = sum(1 for c in calls if c["outcome"] == "cache_hit")
        totals = {"model_calls": len(calls), "live_calls": live_n, "cache_hits": hit_n,
                  "prompt_tokens": sum(c["prompt_tokens"] or 0 for c in calls), "completion_tokens": sum(c["completion_tokens"] or 0 for c in calls),
                  "calls_without_token_report": sum(1 for c in calls if c["tokens_source"] != "provider_reported" and c["outcome"] in ("live", "cache_hit")),
                  "generation_cost_usd": round(sum(c["cost_usd"] for c in calls), 6),
                  "incurred_cost_usd": round(sum(c["incurred_usd"] for c in calls), 6),
                  "model_latency_ms": sum(c["latency_ms"] for c in calls), "wall_ms": t.now_ms()}
        # contexts: which one the committed answer came from
        ctxs = [dict(c["trace"]) for c in t.contexts]
        final_pass = "second_pass" if ans.trace_mode == "second_pass" else "first_pass"
        for c in ctxs:
            c["final"] = False
        for c in ctxs if final_pass == "first_pass" else reversed(ctxs):
            if c["pass_name"] == final_pass:
                c["final"] = True
                break
        final_ctx = next((c["ctx"] for c in t.contexts if c["trace"]["pass_name"] == final_pass), None) if t.contexts else None
        if final_pass == "second_pass":
            final_ctx = next((c["ctx"] for c in reversed(t.contexts) if c["trace"]["pass_name"] == "second_pass"), final_ctx)
        # the reply the committed answer came from (raw model citations)
        model_cited = None
        for c in reversed(t.calls):
            rep = c.get("_reply")
            p = rep.parsed if rep is not None and isinstance(rep.parsed, dict) else None
            if p and p.get("status") == ans.status and (ans.status == "abstain" or str(p.get("answer") or "").strip() == ans.answer.strip()):
                model_cited = list(c["reply_cited"])
                break
        agg = final_ctx.agg if final_ctx is not None else {}
        cited = {"model_cited": model_cited, "final": list(ans.cited_ids),
                 "aggregates_cited": [x for x in (model_cited or []) if x in agg], "absent_cited": sorted(ans.absent)}
        # escalations / second pass / arbitration, from the events that actually happened
        esc, pending = [], None
        for ev in t.events:
            if ev["stage"] in ("escalate", "arbitrate"):
                pending = {"seq": ev["seq"], "kind": ev["stage"], **ev["data"], "call": None}
                esc.append(pending)
            elif ev["stage"] == "model_call" and pending is not None and pending["call"] is None:
                pending["call"] = ev["data"]["n"]
        escalations = [e for e in esc if e["kind"] == "escalate"]
        arbs = [e for e in esc if e["kind"] == "arbitrate"]
        sp_ev = next((e for e in t.events if e["stage"] == "second_pass"), None)
        note_sp = next((n for n in ans.notes if n.startswith("second pass")), None)
        note_arb = next((n for n in ans.notes if "arbitrat" in n), None)
        decisions = [n for n in ans.notes]
        trace = {
            "router": tb.router_trace(t.route, self.reports, gate) if t.route is not None else None,
            "contexts": ctxs, "model_calls": calls, "verifier": t.verifies,
            "retries": [c["n"] for c in calls if c["role"].endswith("_retry")],
            "escalations": escalations,
            "second_pass": {"ran": sp_ev is not None, "reason": sp_ev["data"]["reason"] if sp_ev else None,
                            "used_for_answer": ans.trace_mode == "second_pass", "outcome": note_sp},
            "arbitration": {"ran": bool(arbs), "retried": any(a.get("retry") for a in arbs),
                            "calls": [a["call"] for a in arbs if a["call"]], "outcome": note_arb},
            "cited": cited, "decisions": decisions, "warnings": t.warnings, "totals": totals,
        }
        if trace["router"] is None:       # cannot happen (every path routes first), but never emit a partial schema
            raise RuntimeError("no route event captured")
        cited_records = self._cited(ans, question)
        flags = self._flags(ans, trace, cited_records, gate, final_ctx)
        source = "none" if not (live_n or hit_n) else "mixed" if live_n and hit_n else "live" if live_n else "cache"
        t.emit("result", status=ans.status, confidence=ans.confidence, source=source, flags=flags)
        trace["events"] = t.events
        return QuestionDetail.model_validate({
            "id": qid, "set": qset, "question": question, "status": ans.status, "answer": ans.answer,
            "rationale": re.sub(r"^EARLY ABSTAIN:\s*", "", ans.rationale or "").strip(), "confidence": float(ans.confidence),
            "verified": bool(ans.verified), "flags": flags, "router_mode": trace["router"]["mode"], "source": source,
            "evidence": write.build_evidence(ans, self.records), "cited_records": cited_records, "trace": trace,
            "clarification": ({"message": ans.answer.split(" For example:")[0], "examples": ans.clarification_examples}
                              if gate and hasattr(ans, "clarification_examples") else None)})

    @staticmethod
    def _flags(ans: qa.Answer, trace: dict, cited: list[dict], gate: str | None, final_ctx) -> list[str]:
        f: set[str] = set()
        if ans.status == "not_evaluated":
            f.add("not_evaluated")
        if gate:
            f.add("needs_clarification")
        elif ans.early_abstain:
            f.add("early_abstain")
        if ans.status != "not_evaluated" and not ans.verified:
            f.add("verifier_failed")
        if ans.disagree:
            f.add("runs_disagree")
        if ans.needs_review:
            f.add("needs_review")
        if ans.status != "not_evaluated" and ans.confidence < 0.6:
            f.add("low_confidence")
        if trace["second_pass"]["ran"]:
            f.add("second_pass")
        if trace["escalations"]:
            f.add("escalated")
        if trace["arbitration"]["ran"]:
            f.add("arbitrated")
        if any("FALLBACK" in n for n in [trace["router"]["reason"]]):
            f.add("d1_fallback")
        if final_ctx is not None and final_ctx.truncated:
            f.add("context_truncated")
        if any(c["evidence"]["kind"] == "xml_only" for c in cited):
            f.add("xml_only_evidence")
        if any(w["code"] == "provider_fallback" for w in trace["warnings"]):
            f.add("provider_fallback")
        return sorted(f)

    # ------------------------------------------------------------------ misc
    def models(self) -> dict:
        return {"primary": self.cfg.primary, "escalation": self.cfg.escalation}

    @property
    def live_mode(self) -> bool:
        return bool(self.cfg.live) and self.spend.remaining > 0

    @property
    def provider_fallback_active(self) -> bool:
        return bool(getattr(getattr(self.llm, "backend", None), "_pin_disabled", False))

    def safe_error(self, e: Exception) -> str:
        return redact(f"{type(e).__name__}: {e}")[:300]
