"""Pure functions that turn what the pipeline did into trace objects. No I/O, no pipeline calls."""

from __future__ import annotations

import re
from datetime import date, timedelta

from submission.archive_qa.wells import Report

# ------------------------------------------------------------------ router

CHECK_LABELS = {
    "valid_json": "Reply is valid JSON with the required keys",
    "status_valid": "Status is answered, partial or abstain",
    "answer_nonempty": "Answer text is present",
    "citations_well_formed": "cited_ids is a list of strings",
    "citations_in_context": "Every cited id was in the evidence the model was given",
    "citation_required": "An answer cites at least one evidence record",
    "abstain_citations": "An abstention cites only ABSENT-* records",
    "numbers_supported": "Every number in the answer appears in a cited record",
    "units_match": "Units written next to numbers match the cited record",
    "dates_times_supported": "Every date and time appears in a cited record, its report window or the question",
    "no_false_not_found": "No 'nothing found' claim for a well whose context holds a matching record",
    "parts_addressed": "Every part of a multi-part question is addressed",
    "no_missed_evidence": "An abstention is not contradicted by a matching evidence line",
}
# the verifier returns messages, not a checklist: each message is classified by its own wording (verify.py)
_FAIL_MAP = [
    (r"^Response was not valid JSON", "valid_json"),
    (r"^status must be one of", "status_valid"),
    (r"^answer must be a non-empty string", "answer_nonempty"),
    (r"^cited_ids must be a list", "citations_well_formed"),
    (r"^cited_ids not present in the evidence", "citations_in_context"),
    (r"must cite at least one evidence record", "citation_required"),
    (r"^an abstention may cite only", "abstain_citations"),
    (r"^unit mismatch", "units_match"),
    (r"^dates/times in the answer not found", "dates_times_supported"),
    (r"^numbers in the answer not found", "numbers_supported"),
    (r"^you say nothing was found", "no_false_not_found"),
    (r"^the question has \d+ parts", "parts_addressed"),
]
_FLAG_MAP = [(r"^you abstained, but the evidence contains", "no_missed_evidence")]


def classify_checks(parsed, ctx_ids: frozenset[str], ctx_absent, ctx_agg, failures: list[str], flags: list[str]) -> list[dict]:
    """Every check with pass / fail / flag / not_applicable. A 'pass' means the check produced no message."""
    fails: dict[str, list[str]] = {}
    for msg in failures:
        name = next((n for rx, n in _FAIL_MAP if re.search(rx, msg)), "other")
        fails.setdefault(name, []).append(msg)
    flagged: dict[str, list[str]] = {}
    for msg in flags:
        name = next((n for rx, n in _FLAG_MAP if re.search(rx, msg)), "other")
        flagged.setdefault(name, []).append(msg)
    valid = isinstance(parsed, dict) and "__unparsed__" not in parsed
    status = parsed.get("status") if valid else None
    cited = [c for c in (parsed.get("cited_ids") or []) if isinstance(c, str)] if valid and isinstance(parsed.get("cited_ids"), list) else []
    has_real = any(c in ctx_ids and c not in ctx_absent for c in cited)
    ans_like = status in ("answered", "partial")
    applicable = {
        "valid_json": True, "status_valid": valid, "answer_nonempty": valid, "citations_well_formed": valid,
        "citations_in_context": valid, "citation_required": valid and ans_like,
        "abstain_citations": valid and status == "abstain",
        "numbers_supported": valid and ans_like and has_real, "units_match": valid and ans_like and has_real,
        "dates_times_supported": valid and ans_like and has_real, "no_false_not_found": valid and ans_like,
        "parts_addressed": valid and status == "answered", "no_missed_evidence": valid and status == "abstain",
    }
    out = []
    for name, label in CHECK_LABELS.items():
        if name in fails:
            out.append({"name": name, "label": label, "result": "fail", "detail": fails[name]})
        elif name in flagged:
            out.append({"name": name, "label": label, "result": "flag", "detail": flagged[name]})
        else:
            out.append({"name": name, "label": label, "result": "pass" if applicable[name] else "not_applicable", "detail": []})
    for n in ("other",):
        if n in fails:
            out.append({"name": n, "label": "Other verifier message", "result": "fail", "detail": fails[n]})
    return out


# ------------------------------------------------------------------ router / context

def _periods(res) -> list[str]:
    return [d for d in res.dates if len(d) in (4, 7)]


def _select_reason(r: Report, res) -> str:
    days = [d for d in res.dates if len(d) == 10]
    if res.date_range and res.date_range[0] <= r.iso <= res.date_range[1]:
        return f"inside the date range {res.date_range[0]}..{res.date_range[1]}"
    if r.iso in days:
        return f"exact date {r.iso}"
    prev = (date.fromisoformat(r.iso) - timedelta(days=1)).isoformat()
    if prev in days:
        return (f"fallback D+1: no report dated {prev} for this well, so the report dated {r.iso} "
                f"(which covers {prev} to {r.iso}) is used")
    if r.well in res.wells:
        p = _periods(res)
        return f"report of the named well {r.well}" + (f" in {', '.join(p)}" if p else "")
    p = _periods(res)
    if p and any(r.iso.startswith(x) for x in p):
        return f"report dated in {', '.join(p)}"
    return "whole archive (no well or date named)"


def router_confidence(res, gate: str | None) -> dict:
    if gate:
        return {"level": "low", "basis": "no well, date or topic in the question could be mapped to the archive"}
    if res.early_abstain:
        return {"level": "high", "basis": "the named well/date targets do not exist in the archive"}
    if res.mode == "archive_wide":
        return {"level": "low", "basis": "no well or date named: the whole archive is the candidate set"}
    if "UNMATCHED" in res.reason or "FALLBACK" in res.reason:
        return {"level": "medium", "basis": "part of the question matched only through the D+1 fallback or some targets matched nothing"}
    if res.reason.startswith("exact") or "; exact" in res.reason or "range" in res.reason:
        return {"level": "high", "basis": "every named well/date resolved to a report by exact date or range"}
    return {"level": "medium", "basis": "reports chosen by well or period only (no exact date)"}


def router_trace(res, reports: list[Report], gate: str | None = None) -> dict:
    by_stem = {r.stem: r for r in reports}
    archive_wells = {r.well for r in reports}
    considered = [{"well": w, "in_archive": w in archive_wells, "reports_available": sum(1 for r in reports if r.well == w)}
                  for w in res.wells]
    if not res.wells and res.mode == "archive_wide":
        considered = [{"well": w, "in_archive": True, "reports_available": sum(1 for r in reports if r.well == w)}
                      for w in sorted(archive_wells)]
    selected = [{"report": s, "well": by_stem[s].well, "date": by_stem[s].iso, "reason": _select_reason(by_stem[s], res)}
                for s in res.candidate_files if s in by_stem]
    return {
        "mode": res.mode, "confidence": router_confidence(res, gate), "reason": res.reason,
        "wells_named": list(res.wells), "dates_named": list(res.dates),
        "date_range": list(res.date_range) if res.date_range else None, "topics": list(res.sections),
        "early_abstain": bool(res.early_abstain), "wells_considered": considered, "reports_selected": selected,
        "unmatched": [{"well": w, "date": d, "message": m} for w, d, m in res.unmatched], "gate": gate,
    }


def context_trace(ctx, pass_name: str, rec_index: dict[str, tuple[str, str]]) -> dict:
    """rec_index: record id -> (section, source xml file)."""
    recs = []
    for rid in sorted(ctx.ids):
        if rid in ctx.agg:
            recs.append({"id": rid, "type": "aggregate", "report": None})
        elif rid in ctx.absent:
            recs.append({"id": rid, "type": "absent", "report": None})
        elif rid in rec_index:
            sec, src = rec_index[rid]
            recs.append({"id": rid, "type": sec, "report": src[:-4] if src.endswith(".xml") else src})
        else:
            recs.append({"id": rid, "type": "unknown", "report": None})
    return {
        "pass_name": pass_name, "final": False, "est_tokens": int(ctx.est_tokens), "lines": int(ctx.n_lines),
        "truncated": bool(ctx.truncated), "notes": list(ctx.notes), "records": recs,
        "aggregates": [{"id": k, "text": v["text"], "sources": list(v["sources"])} for k, v in sorted(ctx.agg.items())],
        "absent": [{"id": k, "kind": v["kind"], "reports_searched": v["reports"], "records_searched": v["records"],
                    "considered_and_rejected": list(v.get("near") or [])} for k, v in sorted(ctx.absent.items())],
    }
