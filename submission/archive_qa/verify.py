"""Verifier and rule-based confidence.

The model may only cite record IDs that were in its context, and every number it states must come from a
cited record. A derived number (sum, difference or mean) is accepted only when the answer says it is derived
AND both operands are cited records AND both operands are stated in the answer or rationale (benchmark finding:
without these conditions wrong derived answers were accepted by coincidence). Further rules: every part of a
multi-part question must be addressed, and an abstention is flagged when the context holds a line that matches
the question's well, date and field. All failures are collected and sent back to the model as feedback; they
are never silently fixed.

Dates and times are whole tokens, not digits: an ISO date, an ISO datetime or an HH:MM[:SS] time in the answer
passes only if the same token appears in a cited record (its line, its report date or report window) or in the
question; "24:00" is accepted when "00:00" is cited. List enumerators "(1)", "(2)", "1." at the start of an item are
ignored (only a run 1..k counts). Everything else numeric must appear in a cited record as before.

Confidence is computed here, by rules, never by the model.
"""

from __future__ import annotations

import itertools
import json
import math
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from .context import NARRATIVE, Context
from .match import match_score, norm_text, question_tokens
from .parse import ROW_SECTIONS
from .context import _words as content_words
from .route import find_dates, topic_sections
from .wells import find_wells

STATUSES = ("answered", "partial", "abstain")
_ID_RX = re.compile(r"\[?\b(?:[A-Z0-9]{2,6}-\d{8}-[A-Z0-9_]+(?:-\d+)?|ABSENT-[A-Za-z_]+)\b\]?")
_NUM_RX = re.compile(r"(?<![\w.])-?\d+(?:,\d+)*(?:\.\d+)?|(?<![\w.])-?\.\d+")
_LIST_MARKER = re.compile(r"(?:^|[\n;])\s*\(?(\d{1,2})[.)]\s")

# unit classes: a number followed by a unit is compared with the unit(s) of the record that holds it
_UNIT_CLASS = {
    "m": "m", "mmd": "m", "mtvd": "m", "mmd.": "m", "meter": "m", "meters": "m", "metre": "m", "metres": "m",
    "g/cm3": "density", "g/cm³": "density", "sg": "density", "g/cc": "density", "s.g.": "density",
    "in": "in", "inch": "in", "inches": "in", '"': "in", "''": "in",
    "dega": "deg", "deg": "deg", "degrees": "deg", "degree": "deg", "°": "deg",
    "bar": "bar", "h": "h", "hr": "h", "hrs": "h", "hours": "h", "hour": "h",
    "m/h": "m/h", "min": "min", "minutes": "min", "mpa.s": "mpa.s", "pa": "pa", "ppm": "ppm", "%": "%",
    "degc": "degc", "°c": "degc", "lbm/ft": "lbm/ft", "kg": "kg",
}
_UNIT_AFTER = re.compile(r"^\s*(m/h|g/cm3|g/cm³|mmd|mtvd|dega|degc|°c|lbm/ft|mpa\.s|[A-Za-z]{1,9}\.?|%|°|\"|'')", re.IGNORECASE)


# ------------------------------------------------------------------ dates, times and enumerators

_DATETIME_RX = re.compile(r"\d{4}-\d{2}-\d{2}(?:[T ]\d{1,2}:\d{2}(?::\d{2})?)?")
_TIME_RX = re.compile(r"(?<![\d:])\d{1,2}:\d{2}(?::\d{2})?(?![\d:])")
# an item start (text start, newline, ';', ':' or the end of a sentence) followed by "(1)", "1." / "1)", or the
# worded forms "Part (1):", "Part 1:", "Step 2:"
_ENUM_RX = re.compile(r"(?:^|[\n;:.])\s*(?:(?:part|step)\s+(?:\(\s*(\d{1,2})\s*\)|(\d{1,2}))(?=\s*:)"
                      r"|\(\s*(\d{1,2})\s*\)(?=\s)|(\d{1,2})[.)](?=\s))", re.IGNORECASE)


def mask_temporal(text: str) -> tuple[str, list[str]]:
    """Replace ISO dates / datetimes / HH:MM[:SS] times by spaces (same length, so positions survive) and return
    the masked text with the tokens found, in order."""
    tokens: list[str] = []

    def take(m: re.Match) -> str:
        tokens.append(m.group(0))
        return " " * len(m.group(0))

    return _TIME_RX.sub(take, _DATETIME_RX.sub(take, text)), tokens


def enumerator_spans(text: str) -> list[tuple[int, int]]:
    """Spans of list enumerators "(1)" / "1." at item starts. They count only as a run 1, 2, ..., k (a lone "(7)"
    is a number like any other), so a wrong value cannot hide as an enumerator."""
    found = []
    for m in _ENUM_RX.finditer(text):
        g = next(i for i in (1, 2, 3, 4) if m.group(i))
        found.append((int(m.group(g)), m.span(g)))
    nums = sorted(n for n, _ in found)
    if not found or nums != list(range(1, len(nums) + 1)):
        return []
    return [sp for _, sp in found]


def short_id_rx(ids) -> re.Pattern | None:
    """Short forms of the record ids in the context ("F1C-20161022-ACT-13" -> "ACT-13", "...-SUM-SUM24HR" ->
    "SUM-SUM24HR"). Models write these in prose; they are labels, not numbers. Only ids that exist in the context
    count, so "ACT-13" is NOT ignored when no such record is in the context."""
    shorts = sorted({m.group(1) for i in ids if (m := re.fullmatch(r"[A-Z0-9]+-\d{8}-([A-Za-z][A-Za-z0-9_-]*)", i))},
                    key=len, reverse=True)
    if not shorts:
        return None
    return re.compile(r"(?<![\w-])(?:" + "|".join(re.escape(x) for x in shorts) + r")(?![\w-])", re.IGNORECASE)


# generic short-id shape (section codes from parse.py), for comparing runs where there is no context at hand
_CODES = {c for _, c in ROW_SECTIONS.values()} | {"STATUS", "WELL", "HDR", "SUM", "FCST"}
GENERIC_SHORT_ID_RX = re.compile(r"(?<![\w-])(?:" + "|".join(sorted(_CODES)) + r")-[A-Z0-9_]+(?:-\d+)?(?![\w-])")


def _cited_blob(rows: pd.DataFrame, question: str, window: bool = True) -> str:
    """Everything the cited records state, plus (window=True) their report dates/windows and the question text, with
    datetimes written "YYYY-MM-DD HH:MM:SS" so that a token can be matched as a whole. window=False is the record's
    own line only (used for the "24:00" rule: every report window starts at 00:00, so it must not count)."""
    parts: list[str] = [question or ""] if window else []
    cols = ("text", "value", "report_date", "period_start", "period_end") if window else ("text", "value")
    for _, r in rows.iterrows():
        parts += [r.get(k) for k in cols if isinstance(r.get(k), str)]
        if isinstance(r.get("attrs"), str):
            for e in json.loads(r["attrs"]).values():
                parts += [str(e[k]) for k in ("value", "raw") if e.get(k) is not None]
    return re.sub(r"(\d{4}-\d{2}-\d{2})T(\d)", r"\1 \2", "\n".join(parts))


def temporal_supported(token: str, blob: str, midnight_blob: str | None = None) -> bool:
    """Is this date / datetime / time (whole token) in the blob? A time written without seconds matches the same
    time with seconds ("19:15" ~ "19:15:00"). "24:00" is accepted when "00:00" appears (in `midnight_blob`, the
    cited lines only, if given)."""
    t = token.replace("T", " ")
    if "-" not in t:                                              # a time
        h, rest = t.split(":", 1)
        t = h.zfill(2) + ":" + rest
        if re.fullmatch(r"24:00(?::00)?", t):
            return re.search(r"(?<![\d:])00:00(?!\d)", blob if midnight_blob is None else midnight_blob) is not None
        return re.search(r"(?<![\d:])" + re.escape(t) + r"(?!\d)", blob) is not None
    if " " in t:                                                  # a datetime: pad a one-digit hour
        d, tm = t.split(" ", 1)
        h, rest = tm.split(":", 1)
        t = f"{d} {h.zfill(2)}:{rest}"
        return re.search(r"(?<![\d-])" + re.escape(t) + r"(?!\d)", blob) is not None
    return re.search(r"(?<![\d-])" + re.escape(t) + r"(?!\d)", blob) is not None     # a date


@dataclass
class VerifyResult:
    ok: bool                                                   # no hard failure
    failures: list[str] = field(default_factory=list)          # hard: wrong IDs, numbers, units, structure, parts
    flags: list[str] = field(default_factory=list)             # soft: abstained although a matching line exists
    flagged_ids: list[str] = field(default_factory=list)       # the matching evidence lines behind that flag

    @property
    def needs_escalation(self) -> bool:
        return bool(self.failures or self.flags)

    @property
    def message(self) -> str:
        return "\n".join(f"- {f}" for f in self.failures + self.flags)


# ------------------------------------------------------------------ numbers


def _candidates(token: str) -> list[float]:
    """Numeric readings of a token, strictly:
      "144,3" / "0,05" / "1234,567"  decimal comma only -> 144.3 / 0.05 / 1234.567 (never 1443)
      "1,420" / "12,345"             ambiguous: either 1.420 or 1420 (thousands) is accepted
      "1,234,567" / "1,234.5"        thousands separators only
    """
    t = token.strip().rstrip(",")
    out: list[float] = []

    def add(s: str) -> None:
        try:
            out.append(float(s))
        except ValueError:
            pass

    if re.fullmatch(r"-?\d{1,3}(,\d{3}){2,}(\.\d+)?", t) or re.fullmatch(r"-?\d{1,3},\d{3}\.\d+", t):
        add(t.replace(",", ""))                       # thousands separators
    elif re.fullmatch(r"-?\d{1,3},\d{3}", t):
        add(t.replace(",", ""))                       # 1,420 -> 1420 ...
        add(t.replace(",", "."))                      # ... or 1.420
    elif re.fullmatch(r"-?\d*,\d+", t):
        add(t.replace(",", "."))                      # decimal comma only
    else:
        add(t.replace(",", ""))
    return out


def _decimals(token: str) -> int:
    m = re.search(r"[.,](\d+)$", token.strip())
    return len(m.group(1)) if m else 0


def numbers_in(text: str) -> list[tuple[str, list[float]]]:
    return [(m.group(0), _candidates(m.group(0))) for m in _NUM_RX.finditer(text)]


def _row_numbers(row: pd.Series) -> set[float]:
    """Every number a cited record states (text, value, attrs incl. raw strings)."""
    blob = " ".join(str(x) for x in (row.get("text"), row.get("value")) if isinstance(x, str))
    attrs = row.get("attrs")
    if isinstance(attrs, str):
        for e in json.loads(attrs).values():
            for k in ("value", "raw"):
                v = e.get(k)
                if v is not None:
                    blob += f" {v}"
    vals: set[float] = set()
    for _tok, cands in numbers_in(blob):
        vals.update(round(c, 6) for c in cands)
    if isinstance(row.get("value_num"), float) and not math.isnan(row["value_num"]):
        vals.add(round(row["value_num"], 6))
    return vals


def _row_units(row: pd.Series) -> dict[float, set[str]]:
    """value -> unit classes for the record's measurements."""
    out: dict[float, set[str]] = {}

    def put(v, unit):
        if v is None or not unit:
            return
        cls = _UNIT_CLASS.get(str(unit).lower())
        try:
            out.setdefault(round(float(v), 6), set()).add(cls or str(unit).lower())
        except (TypeError, ValueError):
            pass

    put(row.get("value_num") if isinstance(row.get("value_num"), float) and not math.isnan(row["value_num"]) else None,
        row.get("unit") if isinstance(row.get("unit"), str) else None)
    attrs = row.get("attrs")
    if isinstance(attrs, str):
        for e in json.loads(attrs).values():
            put(e.get("value"), e.get("unit"))
    return out


_DERIVED_CUE = re.compile(
    r"\b(?:differ\w*|sum|total|combined|adding|added|mean|average|increas\w*|decreas\w*|deeper|shallower|"
    r"calculated|computed|derived|subtract\w*|minus|plus)\b|\d\s*[+\u2212\u00d7]\s*\d|\d\s+[-\u2013]\s+\d", re.IGNORECASE)


def says_derived(text: str) -> bool:
    """Does the text say a number was computed (sum, difference, mean ...)? IDs and dates are removed first."""
    return bool(_DERIVED_CUE.search(_ID_RX.sub(" ", text)))


def _supported(value: float, decimals: int, allowed: set[float], derived_ok: bool = False,
               stated: set[float] | None = None) -> bool:
    """Direct match against the cited numbers; or, only when `derived_ok` (the answer says it is derived), the
    sum, difference or mean of two cited operands that are both stated in the answer/rationale (`stated`)."""
    if round(value, 6) in allowed:
        return True
    tol = 0.5 * 10 ** (-decimals) + 1e-9
    nums = sorted(allowed)
    if any(abs(value - a) <= 1e-9 for a in nums):
        return True
    if not derived_ok:
        return False
    stated = stated or set()

    def is_stated(x: float) -> bool:
        return any(abs(x - t) <= 1e-9 for t in stated)

    for a, b in itertools.combinations(nums, 2):
        if not (is_stated(a) and is_stated(b)):
            continue
        for d in (a + b, abs(a - b), (a + b) / 2):
            if abs(value - d) <= tol:
                return True
    return False


# ------------------------------------------------------------------ multi-part questions

_Q_WORD = r"(?:what|which|who|whom|when|where|why|how|did|does|do|was|were|is|are|list|give|state|name)"
_PART_AND = re.compile(rf",?\s+\b(?:and also|as well as|and)\b\s+(?={_Q_WORD}\b)", re.IGNORECASE)
_PART_NUM = re.compile(r"\(\s*(?:\d{1,2}|[a-h])\s*\)\s*|(?<![\w.-])\d{1,2}\)\s+")
_PART_QMARK = re.compile(r"\?\s+(?=[A-Z])")


def split_parts(question: str) -> list[str]:
    """Parts of a multi-part question: numbered parts "(1) ... (2) ...", several sentences ending in '?', or a
    clause joined by "and" / "and also" / "as well as" that starts a new question ("... and what activity ...").
    "casing and liner" is not a split: the word after "and" must open a clause."""
    q = question.strip()
    numbered = [p.strip(" ;,.") for p in _PART_NUM.split(q)]
    if len([p for p in numbered if p]) >= 3 and len(_PART_NUM.findall(q)) >= 2:   # lead-in + at least two parts
        return [p for p in numbered[1:] if p]
    parts: list[str] = []
    for sent in _PART_QMARK.split(q):
        parts += [p.strip(" ?;,.") for p in _PART_AND.split(sent) if p.strip(" ?;,.")]
    return parts if len(parts) >= 2 else [q]


def _stem(w: str) -> str:
    return w[:5]


def unaddressed_parts(question: str, answer: str, rationale: str = "") -> tuple[list[str], list[str]]:
    """(all parts, parts whose distinctive words appear nowhere in the answer or rationale)."""
    parts = split_parts(question)
    if len(parts) < 2:
        return parts, []
    drop = set()
    for m in find_wells(question):
        drop |= content_words(m.well)
    words = [{_stem(w) for w in content_words(p) - drop if not w.isdigit()} for p in parts]
    have = {_stem(w) for w in re.findall(r"[a-z0-9]+", (answer + " " + rationale).lower())}
    missing = []
    for i, part in enumerate(parts):
        others = set().union(*(w for j, w in enumerate(words) if j != i))
        unique = words[i] - others
        if unique and not (unique & have):
            missing.append(part)
    return parts, missing


# ------------------------------------------------------------------ abstain although the evidence is there


def matching_evidence(parsed: dict, context: Context, records: pd.DataFrame, question: str) -> list[str]:
    """IDs of context lines that match the question's well, date and field, for an abstain answer.

    Well and report date (D, or D+1 when the router fell back) must match; the record's section must be one of
    the question's topics, and the question's content words must overlap the record (>= 1 word, >= 2 for
    narrative sections). If the question's topic is one the archive has no field for (an ABSENT-* record is in
    the context), the abstention is legitimate and nothing is flagged."""
    if not isinstance(parsed, dict) or parsed.get("status") != "abstain":
        return []
    wells = {m.well for m in find_wells(question)}
    days = {d.iso for d in find_dates(question) if d.kind == "day"}
    if not wells or not days:
        return []
    topics = set(topic_sections(question))
    if topics & {meta.get("kind") for meta in context.absent.values()}:
        return []
    ok_days = days | {(date.fromisoformat(d) + timedelta(days=1)).isoformat() for d in days}
    drop = set()
    for w in wells:
        drop |= content_words(w)
    q_words = {w for w in content_words(question) if not w.isdigit()} - drop
    real = [i for i in context.ids if i not in context.absent]
    rows = records[records["record_id"].isin(real) & records["well"].isin(wells)
                   & records["report_date"].isin(ok_days) & records["section"].isin(topics)]
    hits = []
    for _, r in rows.iterrows():
        need = 2 if r["section"] in NARRATIVE else 1
        body = " ".join(str(x) for x in (r["field"], r["value"], r["text"]) if isinstance(x, str))
        if len(q_words & content_words(body)) >= need:
            hits.append(r["record_id"])
    return sorted(hits)


# ------------------------------------------------------------------ verification


def verify(parsed: dict, context: Context, records: pd.DataFrame, question: str = "") -> VerifyResult:
    f: list[str] = []
    if not isinstance(parsed, dict) or "__unparsed__" in parsed:
        return VerifyResult(False, ["Response was not valid JSON with keys status, answer, cited_ids, rationale."])
    status = parsed.get("status")
    if status not in STATUSES:
        f.append(f"status must be one of {list(STATUSES)}, got {status!r}.")
    answer = parsed.get("answer")
    if not isinstance(answer, str) or (not answer.strip() and status != "abstain"):   # the prompt asks for "" on abstain
        f.append("answer must be a non-empty string.")
    if not isinstance(answer, str):
        answer = ""
    cited = parsed.get("cited_ids")
    if not isinstance(cited, list) or not all(isinstance(c, str) for c in cited):
        f.append("cited_ids must be a list of strings.")
        cited = []

    unknown = [c for c in cited if c not in context.ids]
    if unknown:
        f.append(f"cited_ids not present in the evidence you were given (never invent IDs): {unknown}")
    real = [c for c in cited if c in context.ids and c not in context.absent]
    absent = [c for c in cited if c in context.absent]
    if status in ("answered", "partial") and not real:
        f.append(f"status '{status}' must cite at least one evidence record ID (ABSENT-* does not support an answer).")
    if status == "abstain" and real:
        f.append(f"an abstention may cite only ABSENT-* records, but cited {real}.")

    if status in ("answered", "partial") and real:
        rows = records[records["record_id"].isin(real)]
        allowed: set[float] = set()
        units: dict[float, set[str]] = {}
        for _, r in rows.iterrows():
            allowed |= _row_numbers(r)
            for v, u in _row_units(r).items():
                units.setdefault(v, set()).update(u)
        allowed |= {round(c, 6) for _t, cs in numbers_in(question) for c in cs}  # numbers echoed from the question
        stripped = _ID_RX.sub(" ", answer)
        sid = short_id_rx(context.ids)
        if sid:
            stripped = sid.sub(lambda m: " " * len(m.group(0)), stripped)   # "ACT-13" is a label, not the number 13
        stripped, temporal = mask_temporal(stripped)                       # dates/times are checked as whole tokens below
        blob = _cited_blob(rows, question)
        line_blob = _cited_blob(rows, question, window=False)
        bad_temporal = sorted({tok for tok in temporal if not temporal_supported(tok, blob, line_blob)})
        enum_spans = enumerator_spans(stripped)
        rationale = parsed.get("rationale") if isinstance(parsed.get("rationale"), str) else ""
        derived_ok = says_derived(answer)       # the ANSWER must say it is derived (a rationale cue is not enough)
        stated = {round(c, 6) for _t, cs in numbers_in(_ID_RX.sub(" ", answer + " " + rationale)) for c in cs}
        markers = {m.group(1) for m in _LIST_MARKER.finditer(stripped)}
        bad: list[str] = []
        for m in _NUM_RX.finditer(stripped):
            tok = m.group(0)
            cands = _candidates(tok)
            if not cands or tok in markers or any(a <= m.start() and m.end() <= b for a, b in enum_spans):
                continue
            if not any(_supported(c, _decimals(tok), allowed, derived_ok, stated) for c in cands):
                bad.append(tok)
                continue
            # unit check: the unit written after the number vs the unit of the record holding that number
            u = _UNIT_AFTER.match(stripped[m.end():])
            cls = _UNIT_CLASS.get(u.group(1).lower().rstrip(".")) if u else None
            held = {x for c in cands for x in units.get(round(c, 6), set())}
            if cls and held and cls not in held and not (cls == "m" and "m/h" in held):
                f.append(f"unit mismatch for {tok}: answer says '{u.group(1)}' but the cited record gives {sorted(held)}.")
        if bad_temporal:
            f.append(f"dates/times in the answer not found in the cited records: {bad_temporal}. A date or time must appear "
                     "exactly (as the same date or time) in a cited record, in its report window, or in the question.")
        if bad:
            f.append("numbers in the answer not found in the cited records: "
                     f"{sorted(set(bad))}. A sum, difference or mean is accepted only if the answer says it is "
                     "derived and both operands are cited records and are stated in the answer or rationale.")
    if status in ("answered", "partial"):
        for well, ids in claimed_missing_but_present(answer, question, context, records):
            f.append(f"you say nothing was found for {well}, but evidence line(s) {ids[:4]} for that well match the "
                     "question's numbers/terms. Re-read them and answer from them.")
    if status == "answered":
        parts, missing = unaddressed_parts(question, answer, parsed.get("rationale") if isinstance(parsed.get("rationale"), str) else "")
        if missing:
            f.append(f"the question has {len(parts)} parts ({'; '.join(f'({i}) {p}' for i, p in enumerate(parts, 1))}) "
                     f"but these are not addressed: {missing}. Answer every part, or use status 'partial'.")
    flagged = matching_evidence(parsed, context, records, question)
    flags = [f"you abstained, but the evidence contains line(s) matching the question's well, date and field: "
             f"{flagged}. Re-read them and answer from them if they contain the requested value."] if flagged else []
    return VerifyResult(not f, f, flags, flagged)


# ------------------------------------------------------------------ "not found" for a well that has a match

_NEGATIVE = re.compile(
    r"\b(?:no\b[^.;:]{0,60}?\b(?:found|confirm\w*|record\w*|report\w*|evidence|mention\w*|line|lines|entry|entries|data|information)"
    r"|not (?:found|confirmed|reported|recorded|stated|mentioned|present|available|given|identified)"
    r"|none\b|nothing\b|no (?:such )?record|could not find|cannot find|unable to find|not in the evidence)", re.IGNORECASE)


def claimed_missing_but_present(answer: str, question: str, context: Context, records: pd.DataFrame) -> list[tuple[str, list[str]]]:
    """For each well the question names: if the answer says nothing was found for it, but a record of that well in the
    context matches the question's distinctive tokens, return (well, matching ids). Such an answer should be re-read."""
    qt = question_tokens(question)
    named = {m.well for m in find_wells(question)}
    if not qt or not named:
        return []
    mentions = [m for m in find_wells(answer) if m.well in named]
    hits: list[tuple[str, list[str]]] = []
    for i, m in enumerate(mentions):
        end = mentions[i + 1].start if i + 1 < len(mentions) else len(answer)
        stop = re.search(r"[.;]\s", answer[m.end:end])
        segment = answer[m.end:m.end + stop.start()] if stop else answer[m.end:end]
        if not _NEGATIVE.search(segment) or any(h[0] == m.well for h in hits):
            continue
        sub = records[(records["well"] == m.well) & records["record_id"].isin(context.ids)]
        ids = [r["record_id"] for _, r in sub.sort_values("record_id").iterrows()
               if match_score(r["text"].split(" | ", 3)[-1] if isinstance(r["text"], str) else "", qt) > 0]
        if ids:
            hits.append((m.well, ids))
    return hits


# ------------------------------------------------------------------ confidence


def confidence(status: str, n_cited: int, mode: str, verified: bool, *, early_abstain: bool = False,
               absent_cited: bool = False, truncated: bool = False) -> float:
    """Rule-based. Verified single record 0.9-0.95; several 0.7-0.8; partial 0.4-0.6; abstention because no
    report exists 0.9; field absent from an existing report 0.75-0.85; verifier failed 0.2."""
    if early_abstain:
        return 0.9
    if not verified:
        return 0.2
    if status == "abstain":
        return 0.85 if absent_cited else 0.75
    if status == "partial":
        return round(0.4 + 0.1 * min(2, max(0, n_cited - 1)), 2)
    if n_cited <= 1:
        base = 0.95 if mode == "single_report" else 0.9
    elif n_cited <= 3:
        base = 0.8
    else:
        base = 0.7
    return round(base - (0.05 if truncated else 0.0), 2)
