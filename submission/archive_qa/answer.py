"""Answering: code finds the facts, the LLM phrases and reasons, a verifier checks.

Flow per question
  route -> early_abstain?  yes: compose the answer from the router's findings, NO LLM call
                           no : build context -> primary model -> verify -> (on failure) escalation model with the
                                verifier's message -> verify -> (still failing) keep the answer, confidence 0.2,
                                note "VERIFIER FAILED: ..." so it lands in the human review queue
Nothing here is specific to any question.
"""

from __future__ import annotations

import csv
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from . import config
from .context import Context, build_context, dump_context
from .llm import LLM
from .route import RouteResult, route_question
from .verify import STATUSES, confidence, verify
from .wells import Report, parse_stem

SYSTEM_PROMPT = """You answer questions about daily drilling reports (WITSML) using ONLY the EVIDENCE lines you are given. Each line starts with a [RECORD_ID].
Rules:
1. Use only the evidence lines. No outside knowledge. Never invent a record ID: cite only IDs that appear in the evidence.
2. A report dated D covers D-1 00:00 to D 00:00, and questions give the report date. An event or sample "at 21:00 on D" is usually timestamped D-1 inside report D: answer from report D and state the actual timestamp shown after "at".
3. Quote numbers exactly as written, with their units (m, mMD, g/cm3, in, bar ...). Do not round or convert.
4. Answer EVERY part of a multi-part question. If only some parts are supported by the evidence, use status "partial": give the supported parts and say exactly what is missing.
5. "missing" means the report records no value. If the requested information is absent from the evidence (including when an [ABSENT-...] line says the field does not exist), use status "abstain": say what is absent, what was checked, and what the evidence does contain. Cite the ABSENT-* ID if there is one.
6. Never substitute a related field for the one asked (a wireline logging company is not a mud-logging company; a different well, report date or depth is not a match). If the exact thing asked is not in the evidence, abstain or answer partially.
7. For "deepest", "maximum" or comparisons, check every matching record. Survey lines are listed in ascending measured depth.
Return ONLY a JSON object: {"status": "answered"|"partial"|"abstain", "answer": "...", "cited_ids": ["ID", ...], "rationale": "one or two sentences"}"""


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

    @property
    def needs_review(self) -> bool:
        return (not self.early_abstain) and (not self.verified or self.confidence < 0.6)


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


def _ask(llm: LLM, ctx: Context, question: str, qid: str, model: str, role: str, feedback: str = ""):
    return llm.ask(SYSTEM_PROMPT, ctx.text, question, model, feedback=feedback, question_id=qid, role=role)


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

    calls, cost, notes = 0, 0.0, []
    reply = _ask(llm, ctx, question, question_id, primary, "primary")
    calls, cost = calls + 1, cost + reply.cost_usd
    result = verify(reply.parsed, ctx, records, question)
    if not result.ok:
        notes.append(f"first answer failed verification ({primary}); escalated to {escalation}")
        reply = _ask(llm, ctx, question, question_id, escalation, "escalation", feedback=result.message)
        calls, cost = calls + 1, cost + reply.cost_usd
        result = verify(reply.parsed, ctx, records, question)

    p = reply.parsed if isinstance(reply.parsed, dict) else {}
    status = p.get("status") if p.get("status") in STATUSES else "abstain"
    answer_text = p.get("answer") if isinstance(p.get("answer"), str) and p.get("answer").strip() else (
        "(the model returned no usable answer)")
    cited = [c for c in (p.get("cited_ids") or []) if isinstance(c, str)] if isinstance(p.get("cited_ids"), list) else []
    cited = [c for c in dict.fromkeys(cited)]
    real = [c for c in cited if c in ctx.ids and c not in ctx.absent]
    absent_cited = [c for c in cited if c in ctx.absent]
    conf = confidence(status, len(real), route.mode, result.ok, absent_cited=bool(absent_cited), truncated=ctx.truncated)
    if not result.ok:
        notes.append("VERIFIER FAILED: " + " | ".join(result.failures))
    if ctx.truncated:
        notes.append("context truncated (multi-report cap)")
    if "FALLBACK" in route.reason:
        notes.append("router used D+1 fallback")
    notes.append(f"model={reply.model}")
    return Answer(
        question_id, question, status, answer_text, [c for c in cited if c in ctx.ids], str(p.get("rationale") or ""),
        conf, notes, route.mode, list(route.candidate_files), reply.model, result.ok, result.failures, False,
        {i: ctx.absent[i] for i in absent_cited}, "", calls, cost)


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
