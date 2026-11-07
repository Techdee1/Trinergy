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
from .llm import LLM, CacheMiss
from .prompts import SYSTEM_PROMPT
from .repair import repair_citations
from .route import RouteResult, route_question
from .verify import (_ID_RX, _NUM_RX, STATUSES, _candidates, confidence, enumerator_spans, mask_temporal,
                     split_parts, verify)
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
        if meta.get("near"):
            parts.append("Considered and rejected: " + "; ".join(
                f"{n['what']} ({n['reason']})" for n in meta["near"]) + ".")
    if rationale.strip():
        parts.append(rationale.strip())
    return " ".join(parts)


def _canon_time(tok: str) -> str:
    h, rest = tok.split(":", 1)
    t = h.zfill(2) + ":" + rest
    return t[:-3] if re.fullmatch(r"\d\d:\d\d:00", t) else t


def _tokens(text: str) -> set[str]:
    """Numbers (not date/time digits, not list enumerators) and whole times stated in `text`."""
    masked, temporal = mask_temporal(_ID_RX.sub(" ", text or ""))
    skip = enumerator_spans(masked)
    out = {f"t:{_canon_time(t.replace('T', ' ').split(' ')[-1] if '-' in t else t)}" for t in temporal
           if ":" in t}                                       # times, also those inside a datetime
    for m in _NUM_RX.finditer(masked):
        cands = _candidates(m.group(0))
        if cands and not any(a <= m.start() and m.end() <= b for a, b in skip):
            out.add(f"n:{round(cands[0], 6):g}")
    return out


def key_tokens(answer: str, question: str = "") -> set[str]:
    """What an answer states, for comparing two runs: its numbers and whole times, minus those that merely echo
    the question (a run that repeats "36" from '36" hole opener' must not disagree with one that does not)."""
    return _tokens(answer) - _tokens(question)


def key_numbers(answer: str) -> set[float]:
    """Numbers an answer states (IDs and dates/times removed). Kept for callers that want plain floats."""
    return {float(t[2:]) for t in _tokens(answer) if t.startswith("n:")}


def runs_differ(a: dict, b: dict, question: str = "") -> bool:
    """Do two parsed replies disagree on status or on the key numbers/times they state (question echoes excluded)?"""
    sa, sb = (a or {}).get("status"), (b or {}).get("status")
    if sa != sb:
        return True
    ta = (a or {}).get("answer") if isinstance((a or {}).get("answer"), str) else ""
    tb = (b or {}).get("answer") if isinstance((b or {}).get("answer"), str) else ""
    return key_tokens(ta, question) != key_tokens(tb, question)


def disagreement_text(a: dict, b: dict, question: str) -> str:
    """Short description of how two runs differ, for the notes and the arbiter."""
    def get(p, k):
        return (p or {}).get(k) if isinstance((p or {}).get(k), str) else ""
    ka, kb = key_tokens(get(a, "answer"), question), key_tokens(get(b, "answer"), question)
    return (f"run 1: {(a or {}).get('status')}, run 2: {(b or {}).get('status')}; "
            f"only in run 1: {sorted(ka - kb)}; only in run 2: {sorted(kb - ka)}")


def partial_feedback(parsed: dict) -> str:
    ans = (parsed or {}).get("answer") if isinstance((parsed or {}).get("answer"), str) else ""
    return ("PARTIAL: your previous answer was marked partial (it addressed only part of the question): "
            f"{ans[:800]!r}. Re-read every evidence line. If the evidence supports an answer to the missing part(s), give a "
            "complete answer citing those lines; if some part is truly absent from the evidence, keep status \"partial\" "
            "and state exactly what is missing.")


def arbitration_feedback(a: dict, b: dict, question: str) -> str:
    def block(name, p):
        ans = ((p or {}).get("answer") or "")[:1200] if isinstance((p or {}).get("answer"), str) else ""
        return f"{name}: status={(p or {}).get('status')}; answer={ans!r}"
    return ("ARBITRATION: two independent runs of this question gave different answers (" + disagreement_text(a, b, question)
            + "). Decide from the evidence lines only, cite the lines you use, and answer in the same JSON format.\n"
            + block("Run A", a) + "\n" + block("Run B", b))


def question_for_llm(question: str) -> str:
    """The question as sent to the model. A multi-part question gets its parts listed so each can be addressed
    (and named in the rationale); a single-part question is sent unchanged."""
    parts = split_parts(question)
    if len(parts) < 2:
        return question
    listing = " ".join(f"({i}) {p}." for i, p in enumerate(parts, 1))
    return f"{question}\nThis question has {len(parts)} parts: {listing} Address every part and name each part in the rationale."


def normalise_reply(parsed, ctx: Context):
    """Citations for an abstention are set in code, before verification: exactly the ABSENT-* ids present in the
    context (none if there are none). Whatever the model cited on an abstain (real records, malformed or invented
    ids) is dropped, since an abstention may cite only ABSENT-* records. Returns a copy; the cache is untouched."""
    if isinstance(parsed, dict) and parsed.get("status") == "abstain":
        return {**parsed, "cited_ids": sorted(ctx.absent)}
    return parsed


def _ask(llm: LLM, ctx: Context, question: str, qid: str, model: str, role: str, feedback: str = "", run: str = "",
         max_tokens: int | None = None):
    reply = llm.ask(SYSTEM_PROMPT, ctx.text, question, model, feedback=feedback, question_id=qid, role=role, run=run,
                    max_tokens=max_tokens)
    reply.parsed = normalise_reply(reply.parsed, ctx)
    return reply


MULTI_MODES = ("multi_report", "archive_wide")


def start_cap(llm: LLM, mode: str) -> int | None:
    """Primary calls on multi-report / archive-wide questions use LLM_MULTI_MAX_TOKENS (their answers list several
    records and were truncated at 400); single-report questions keep LLM_MAX_TOKENS."""
    return llm.cfg.multi_max_tokens if mode in MULTI_MODES else None


def _ask_with_retry(llm: LLM, ctx: Context, question: str, qid: str, model: str, role: str, run: str,
                    notes: list[str], label: str, cap: int | None = None):
    """Primary-model call; if the reply was truncated (finish_reason length) or is not valid JSON, retry the SAME
    model once with the larger LLM_RETRY_MAX_TOKENS cap before anything escalates. The retry is its own cache entry
    (the cap is part of the key). Returns (final reply, calls made, cost)."""
    reply = _ask(llm, ctx, question, qid, model, role, run=run, max_tokens=cap)
    calls, cost = 1, reply.cost_usd
    # no retry when the call already ran at the retry cap: the same request would give the same reply, so the
    # verifier (and then the escalation) handles it
    if reply.truncated_or_invalid and (cap or llm.cfg.max_tokens) < llm.cfg.retry_max_tokens:
        why = "truncated (finish_reason=length)" if reply.finish_reason in ("length", "max_tokens") else "not valid JSON"
        cap = llm.cfg.retry_max_tokens
        notes.append(f"{label} reply {why}; retried {model} once with max_tokens {cap}")
        reply = _ask(llm, ctx, question, qid, model, f"{role}_retry", run=run, max_tokens=cap)
        calls, cost = calls + 1, cost + reply.cost_usd
    return reply, calls, cost


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
    cap = start_cap(llm, route.mode)
    first, calls, cost = _ask_with_retry(llm, ctx, q_llm, question_id, primary, "primary", "", notes, "run 1", cap)
    # second independent run of the same request (own cache entry): disagreement flag, never the committed answer.
    # It gets the same truncation retry, and the flag compares the FINAL parsed runs, so a retry alone never fires it.
    second = None
    try:
        second, c2, k2 = _ask_with_retry(llm, ctx, q_llm, question_id, primary, "primary_run2", "2", notes, "run 2", cap)
        calls, cost = calls + c2, cost + k2
    except RuntimeError as e:
        if type(e).__name__ in ("CacheMiss", "BudgetExceeded"):
            raise
        notes.append(f"REVIEW: second run failed ({type(e).__name__}); disagreement not checked")

    reply, result = first, verify(first.parsed, ctx, records, question)
    escalated = False
    if result.needs_escalation:  # the ONLY escalation triggers: verifier failure, or abstain with a matching line
        why = "verifier failed" if result.failures else "abstained although a matching evidence line exists"
        notes.append(f"first answer: {why} ({primary}); escalated to {escalation}")
        esc = _ask(llm, ctx, q_llm, question_id, escalation, "escalation", feedback=result.message)
        escalated = True
        calls, cost = calls + 1, cost + esc.cost_usd
        esc_result = verify(esc.parsed, ctx, records, question)
        if esc_result.ok or not result.ok:       # use the escalated answer unless it is worse than the first one
            reply, result = esc, esc_result
        else:
            notes.append("REVIEW: escalated answer failed verification; kept the first run")
        if result.flags and result.ok:
            notes.append(f"abstention confirmed by the escalation model despite matching line(s) {result.flagged_ids}")

    # Disagreement between the two primary runs (question echoes excluded). When run 1 is clean, escalate ONCE to the
    # escalation model as arbiter: a verified arbiter answer is committed; otherwise run 1 is kept with a REVIEW note.
    # If run 1 already needed the escalation, that Sonnet call is the arbiter (never a second call).
    disagree = False
    big_used = escalated
    if second is not None and runs_differ(first.parsed, second.parsed, question):
        diff = disagreement_text(first.parsed, second.parsed, question)
        if escalated:
            if reply is not first and result.ok:
                notes.append(f"runs disagreed ({diff}); resolved by the escalation answer, which verified")
            else:
                disagree = True
                notes.append(f"REVIEW: runs disagree ({diff})")
        else:
            arb_fb = arbitration_feedback(first.parsed, second.parsed, question)
            arb = _ask(llm, ctx, q_llm, question_id, escalation, "escalation", feedback=arb_fb)
            big_used = True
            calls, cost = calls + 1, cost + arb.cost_usd
            arb_result = verify(arb.parsed, ctx, records, question)
            retried = False
            if not arb_result.ok:
                # one more Sonnet attempt, told what the verifier rejected, before falling back to run 1
                retried = True
                arb2 = _ask(llm, ctx, q_llm, question_id, escalation, "escalation",
                            feedback=arb_fb + "\n\nYour previous arbitration answer failed these checks (fix every point):\n"
                            + arb_result.message)
                calls, cost = calls + 1, cost + arb2.cost_usd
                arb2_result = verify(arb2.parsed, ctx, records, question)
                notes.append(f"arbiter answer failed verification ({'; '.join(arb_result.failures)[:160]}); "
                             f"retried {escalation} once with the verifier's message")
                arb, arb_result = arb2, arb2_result
            if arb_result.ok:
                reply, result = arb, arb_result
                notes.append(f"runs disagreed ({diff}); arbitrated by {escalation}"
                             f"{' (second attempt)' if retried else ''}: its verified answer is committed")
            else:
                disagree = True
                notes.append(f"REVIEW: runs disagree ({diff}); the arbiter answer ({escalation}) failed verification"
                             f"{' twice' if retried else ''} ({'; '.join(arb_result.failures)[:200]}), kept run 1")

    # Partial policy: a final partial answer is escalated ONCE (never when a big-model call was already made). The
    # escalated answer is kept if it verifies, whatever status it has; the status is never forced.
    if isinstance(reply.parsed, dict) and reply.parsed.get("status") == "partial" and not big_used:
        part = _ask(llm, ctx, q_llm, question_id, escalation, "escalation", feedback=partial_feedback(reply.parsed))
        calls, cost = calls + 1, cost + part.cost_usd
        part_result = verify(part.parsed, ctx, records, question)
        if part_result.ok:
            st = part.parsed.get("status") if isinstance(part.parsed, dict) else "?"
            notes.append(f"partial answer: escalated to {escalation}; its verified answer is committed (status {st})")
            reply, result = part, part_result
        else:
            notes.append(f"partial answer: escalated to {escalation} but its answer failed verification "
                         f"({'; '.join(part_result.failures)[:160]}); kept the partial answer")

    p = reply.parsed if isinstance(reply.parsed, dict) else {}
    status = p.get("status") if p.get("status") in STATUSES else "abstain"
    cited = [c for c in (p.get("cited_ids") or []) if isinstance(c, str)] if isinstance(p.get("cited_ids"), list) else []
    cited = [c for c in dict.fromkeys(cited)]
    rationale = str(p.get("rationale") or "")
    if status == "abstain":
        # In code, not via the prompt: an abstention on a topic the archive has no field for cites that ABSENT record,
        # so the evidence column says what was searched. The "Searched N report(s)..." text goes into the rationale.
        for rid, meta in ctx.absent.items():
            if rid not in cited:
                cited.append(rid)
            sentence = (f"Searched {meta['reports']} report(s) and {meta['records']} record(s): "
                        f"no {meta['kind'].replace('_', ' ')} field exists.")
            if sentence not in rationale:
                rationale = f"{rationale} {sentence}".strip()
    real = [c for c in cited if c in ctx.ids and c not in ctx.absent]
    absent_cited = [c for c in cited if c in ctx.absent]
    answer_text = p.get("answer") if isinstance(p.get("answer"), str) and p.get("answer").strip() else (
        abstain_text(str(p.get("rationale") or ""), {i: ctx.absent[i] for i in absent_cited}) if status == "abstain"
        else "(the model returned no usable answer)")
    if status in ("answered", "partial") and real:
        new_cited, repair_notes = repair_citations(cited, answer_text, rationale, ctx, records, mode=route.mode, status=status)
        if new_cited != cited:
            check = verify({**p, "cited_ids": new_cited}, ctx, records, question)
            if check.ok or not result.ok:         # never trade a verified answer for an unverified one
                cited, notes = new_cited, notes + repair_notes
                real = [c for c in cited if c in ctx.ids and c not in ctx.absent]
            else:
                notes.append("citation repair skipped: the repaired citations did not verify")
    conf = confidence(status, len(real), route.mode, result.ok, absent_cited=bool(absent_cited), truncated=ctx.truncated)
    if not result.ok:
        notes.append("VERIFIER FAILED: " + " | ".join(result.failures))
    if ctx.truncated:
        notes.append("context truncated (multi-report cap)")
    if "FALLBACK" in route.reason:
        notes.append("router used D+1 fallback")
    notes.append(f"model={reply.model}")
    return Answer(
        question_id, question, status, answer_text, [c for c in cited if c in ctx.ids], rationale,
        conf, notes, route.mode, list(route.candidate_files), reply.model, result.ok, result.failures, False,
        {i: ctx.absent[i] for i in absent_cited}, "", calls, cost, disagree)


def uncached_questions(questions: pd.DataFrame, records: pd.DataFrame, reports: list[Report], llm: LLM) -> list[str]:
    """Ids of the questions that CANNOT be answered from the cache (an offline replay raises CacheMiss). It runs the real
    pipeline, so it can never drift from how cache keys are built; early abstentions need no cache entry."""
    missing = []
    for q in questions.itertuples(index=False):
        try:
            answer_question(q.question_id, q.question_text, records, reports, llm, dump=False)
        except CacheMiss:
            missing.append(q.question_id)
    return missing


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
