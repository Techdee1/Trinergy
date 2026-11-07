"""Answering: code finds the facts, the LLM phrases and reasons, a verifier checks.

Flow per question
  route -> early_abstain?  yes: compose the answer from the router's findings, NO LLM call
                           no : build context (with the date-window note) -> primary model, run 1 and a second
                                independent run 2 (disagreement flag) -> verify run 1 ->
                                escalate to the escalation model, once, ONLY if the verifier failed or the model
                                abstained although a matching context line exists -> verify -> (still failing) keep
                                the answer, confidence 0.2, note "VERIFIER FAILED: ..."
The committed answer is run 1 unless the verifier/escalation replaced it. Nothing here is specific to any question.
"""

from __future__ import annotations

import csv
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from . import config
from .context import Context, build_context, dump_context
from .llm import LLM
from .prompts import SYSTEM_PROMPT
from .route import RouteResult, route_question
from .verify import _ID_RX, STATUSES, confidence, numbers_in, split_parts, verify
from .wells import Report, parse_stem

@dataclass
class Answer:
    question_id: str
    question: str
    status: str
    answer: str
    cited_ids: list[str]
    rationale: str
    confidence: float
    notes: list[str] = field(default_factory=list)
    mode: str = ""
    candidates: list[str] = field(default_factory=list)
    model: str = ""
    verified: bool = False
    failures: list[str] = field(default_factory=list)
    early_abstain: bool = False
    absent: dict[str, dict] = field(default_factory=dict)
    evidence_extra: str = ""      # early-abstain "what was checked" text
    llm_calls: int = 0
    cost_usd: float = 0.0
    disagree: bool = False        # the two primary runs differ in status or key numbers

    @property
    def needs_review(self) -> bool:
        return (not self.early_abstain) and (not self.verified or self.confidence < 0.6 or self.disagree)


# ------------------------------------------------------------------ early abstain


def manifest_summary(reports: list[Report]) -> tuple[int, int, bool]:
    """(daily reports, wellbores, read_from_manifest). Reads document_manifest.csv when available.

    Wellbores are counted by canonicalising the manifest's file names: its `well_hint` column is unreliable
    (the year leaks into some hints, e.g. "15_9_F_12_2007", which would give 11 instead of 8)."""
    try:
        path = config.DATA_ROOT / "metadata" / "document_manifest.csv"
        with path.open(encoding="utf-8-sig", newline="") as f:
            rows = [r for r in csv.DictReader(f)
                    if "daily_drilling_reports" in r["relative_path"].replace("\\", "/") and r["file_type"].lower() == ".xml"]
        if rows:
            return len(rows), len({parse_stem(r["file_name"].rsplit(".", 1)[0])[0] for r in rows}), True
    except (OSError, KeyError, FileNotFoundError):
        pass
    return len(reports), len({r.well for r in reports}), False


def _nearest(reports: list[Report], well: str, day: str) -> tuple[Report, int] | None:
    d = date.fromisoformat(day)
    cands = [(abs((r.report_date - d).days), r) for r in reports if r.well == well]
    if not cands:
        return None
    delta, rep = min(cands, key=lambda t: (t[0], t[1].report_date))
    return rep, delta


def early_abstain_answer(question_id: str, question: str, route: RouteResult, reports: list[Report]) -> Answer:
    n_reports, n_wells, from_manifest = manifest_summary(reports)
    parts: list[str] = []
    checked: list[str] = []
    for well, day, msg in route.unmatched:
        if well and day and well in {r.well for r in reports}:
            nxt = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
            near = _nearest(reports, well, day)
            s = f"The archive has no daily drilling report for {well} dated {day} (nor {nxt})"
            if near:
                rep, delta = near
                s += f"; the nearest report for that well is dated {rep.iso} ({delta} day(s) away)"
            parts.append(s + ".")
            checked.append(f"reports for {well}: {', '.join(r.iso for r in reports if r.well == well)}")
        elif well and well not in {r.well for r in reports}:
            parts.append(f"Well {well} has no daily drilling report in the archive"
                         + (f" (asked for {day})." if day else "."))
            checked.append(f"no report for {well}")
        else:
            parts.append(msg[0].upper() + msg[1:] + ".")
    wells = sorted({r.well for r in reports})
    answer = ("Not answerable from the archive. " + " ".join(parts)
              + f" The archive contains {n_reports} daily drilling reports for {n_wells} wellbores ({', '.join(wells)}), "
              "so there is no report on which to base an answer.")
    src = "document_manifest.csv" if from_manifest else "the report files"
    evidence = f"Checked {src}: {n_reports} daily reports, {n_wells} wellbores" + (
        "; " + "; ".join(checked) if checked else "")
    return Answer(question_id, question, "abstain", answer, [], route.reason, confidence("abstain", 0, route.mode, True, early_abstain=True),
                  notes=["early abstain: no LLM call", route.reason], mode=route.mode, candidates=[],
                  verified=True, early_abstain=True, evidence_extra=evidence)


# ------------------------------------------------------------------ one question


def abstain_text(rationale: str, absent: dict[str, dict]) -> str:
    """Answer text for an abstention whose "answer" is empty (the prompt asks for ""): built only from what the
    model cited (ABSENT-* records) and its rationale, so nothing is invented."""
    parts = ["Not answerable from the archive."]
    for meta in absent.values():
        parts.append(f"No {meta['kind'].replace('_', ' ')} field exists (searched {meta['reports']} report(s), "
                     f"{meta['records']} record(s)).")
    if rationale.strip():
        parts.append(rationale.strip())
    return " ".join(parts)


_ISO_TS = re.compile(r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?)?")


def key_numbers(answer: str) -> set[float]:
    """Numbers an answer states (IDs and dates/timestamps removed), for comparing two runs."""
    text = _ISO_TS.sub(" ", _ID_RX.sub(" ", answer or ""))
    return {round(c[0], 6) for _t, c in numbers_in(text) if c}


def runs_differ(a: dict, b: dict) -> bool:
    """Do two parsed replies disagree on status or on the numbers they state?"""
    sa, sb = (a or {}).get("status"), (b or {}).get("status")
    if sa != sb:
        return True
    ta = (a or {}).get("answer") if isinstance((a or {}).get("answer"), str) else ""
    tb = (b or {}).get("answer") if isinstance((b or {}).get("answer"), str) else ""
    return key_numbers(ta) != key_numbers(tb)


def question_for_llm(question: str) -> str:
    """The question as sent to the model. A multi-part question gets its parts listed so each can be addressed
    (and named in the rationale); a single-part question is sent unchanged."""
    parts = split_parts(question)
    if len(parts) < 2:
        return question
    listing = " ".join(f"({i}) {p}." for i, p in enumerate(parts, 1))
    return f"{question}\nThis question has {len(parts)} parts: {listing} Address every part and name each part in the rationale."


def _ask(llm: LLM, ctx: Context, question: str, qid: str, model: str, role: str, feedback: str = "", run: str = ""):
    return llm.ask(SYSTEM_PROMPT, ctx.text, question, model, feedback=feedback, question_id=qid, role=role, run=run)


def answer_question(question_id: str, question: str, records: pd.DataFrame, reports: list[Report],
                    llm: LLM, dump: bool = True) -> Answer:
    route = route_question(question, reports)
    if route.early_abstain:
        return early_abstain_answer(question_id, question, route, reports)

    ctx = build_context(question_id, question, route, records)
    if dump:
        dump_context(ctx, route, question)
    primary, escalation = llm.cfg.primary, llm.cfg.escalation or llm.cfg.primary
    if not primary:
        raise RuntimeError("LLM_MODEL_PRIMARY is not set (and no model names are recorded in the cache).")

    q_llm = question_for_llm(question)
    notes: list[str] = []
    first = _ask(llm, ctx, q_llm, question_id, primary, "primary")
    calls, cost = 1, first.cost_usd
    # second independent run of the same request (own cache entry): disagreement flag, never the committed answer
    second = None
    try:
        second = _ask(llm, ctx, q_llm, question_id, primary, "primary_run2", run="2")
        calls, cost = calls + 1, cost + second.cost_usd
    except RuntimeError as e:
        if type(e).__name__ in ("CacheMiss", "BudgetExceeded"):
            raise
        notes.append(f"REVIEW: second run failed ({type(e).__name__}); disagreement not checked")

    reply, result = first, verify(first.parsed, ctx, records, question)
    if result.needs_escalation:  # the ONLY escalation triggers: verifier failure, or abstain with a matching line
        why = "verifier failed" if result.failures else "abstained although a matching evidence line exists"
        notes.append(f"first answer: {why} ({primary}); escalated to {escalation}")
        esc = _ask(llm, ctx, q_llm, question_id, escalation, "escalation", feedback=result.message)
        calls, cost = calls + 1, cost + esc.cost_usd
        esc_result = verify(esc.parsed, ctx, records, question)
        if esc_result.ok or not result.ok:       # use the escalated answer unless it is worse than the first one
            reply, result = esc, esc_result
        else:
            notes.append("REVIEW: escalated answer failed verification; kept the first run")
        if result.flags and result.ok:
            notes.append(f"abstention confirmed by the escalation model despite matching line(s) {result.flagged_ids}")

    p = reply.parsed if isinstance(reply.parsed, dict) else {}
    status = p.get("status") if p.get("status") in STATUSES else "abstain"
    cited = [c for c in (p.get("cited_ids") or []) if isinstance(c, str)] if isinstance(p.get("cited_ids"), list) else []
    cited = [c for c in dict.fromkeys(cited)]
    real = [c for c in cited if c in ctx.ids and c not in ctx.absent]
    absent_cited = [c for c in cited if c in ctx.absent]
    answer_text = p.get("answer") if isinstance(p.get("answer"), str) and p.get("answer").strip() else (
        abstain_text(str(p.get("rationale") or ""), {i: ctx.absent[i] for i in absent_cited}) if status == "abstain"
        else "(the model returned no usable answer)")
    conf = confidence(status, len(real), route.mode, result.ok, absent_cited=bool(absent_cited), truncated=ctx.truncated)
    if not result.ok:
        notes.append("VERIFIER FAILED: " + " | ".join(result.failures))
    disagree = second is not None and runs_differ(first.parsed, second.parsed)
    if disagree:
        s2 = second.parsed if isinstance(second.parsed, dict) else {}
        notes.append(f"REVIEW: runs disagree (run 1: {(first.parsed or {}).get('status')} {sorted(key_numbers((first.parsed or {}).get('answer', '')))}; "
                     f"run 2: {s2.get('status')} {sorted(key_numbers(s2.get('answer', '') if isinstance(s2.get('answer'), str) else ''))})")
    if ctx.truncated:
        notes.append("context truncated (multi-report cap)")
    if "FALLBACK" in route.reason:
        notes.append("router used D+1 fallback")
    notes.append(f"model={reply.model}")
    return Answer(
        question_id, question, status, answer_text, [c for c in cited if c in ctx.ids], str(p.get("rationale") or ""),
        conf, notes, route.mode, list(route.candidate_files), reply.model, result.ok, result.failures, False,
        {i: ctx.absent[i] for i in absent_cited}, "", calls, cost, disagree)


def answer_all(questions: pd.DataFrame, records: pd.DataFrame, reports: list[Report], llm: LLM,
               ids: list[str] | None = None, dump: bool = True) -> list[Answer]:
    """Answer questions (all, or only `ids`) in question order. LLM_CONCURRENCY workers."""
    rows = [q for q in questions.itertuples(index=False) if ids is None or q.question_id in ids]

    def one(q):
        return answer_question(q.question_id, q.question_text, records, reports, llm, dump)

    if llm.cfg.concurrency <= 1 or len(rows) <= 1:
        return [one(q) for q in rows]
    with ThreadPoolExecutor(max_workers=llm.cfg.concurrency) as pool:
        return list(pool.map(one, rows))  # map preserves order; the first exception propagates
