"""Computed evidence for questions the per-report context cannot answer by itself: counts, extrema, comparisons.

Everything here is computed in code from the evidence store (never by the model) and presented as ordinary evidence
lines: real records with their real ids, plus a few aggregate lines (ids `AGG-00000000-<FIELD>` and `IDX-00000000-<NAME>`,
same shape as record ids) that state count / min / max and name the records they come from. When the model cites an
aggregate line, the evidence column cites those source records instead.

Nothing here knows about any particular question: fields are matched to the question's words through the field
names themselves (camelCase parts plus a small vocabulary of standard abbreviations).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import pandas as pd

from .match import _stem
from .wells import find_wells

AGG_DATE = "00000000"
COUNT_RX = re.compile(r"\bhow many\b|\bnumber of\b|\bcount\b|\btotal number\b", re.I)
EXTREMUM_RX = re.compile(r"\b(?:deepest|shallowest|largest|smallest|highest|lowest|maximum|minimum|max|min|greatest|least|most|"
                         r"longest|shortest|biggest|top|bottom|first|last|earliest|latest|oldest|newest)\b", re.I)
COMPARE_RX = re.compile(r"\bcompar\w*|\bversus\b|\bvs\.?\b|\bdifference\b|\bdiffer\w*|\b(?:deeper|higher|lower|larger|smaller|"
                        r"greater|shallower|longer|shorter|bigger|more|less)\b", re.I)

# standard abbreviations in WITSML field names -> the words a question uses for them
ABBREV = {"md": "measured depth", "tvd": "true vertical depth", "csg": "casing", "dtim": "date time", "tim": "time",
          "pres": "pressure", "dia": "diameter", "elev": "elevation", "form": "formation", "vis": "viscosity",
          "pv": "plastic viscosity", "yp": "yield point", "rop": "rate penetration", "incl": "inclination",
          "azi": "azimuth", "od": "outer diameter", "id": "inner diameter", "temp": "temperature", "num": "number",
          "cond": "condition", "mfg": "manufacturer", "strat": "stratigraphy", "lith": "lithology", "eq": "equivalent",
          "hrs": "hours", "tot": "total", "av": "average", "sum": "summary", "meth": "methane", "eth": "ethane",
          "prop": "propane", "ibut": "isobutane", "nbut": "butane", "ipent": "isopentane", "bht": "bottom hole temperature",
          "bst": "static temperature", "e": "elapsed", "d": "", "dist": "distance", "kickoff": "kick off"}
SKIP_FIELDS = {"name", "type", "id", "comment", "comments", "description", "state", "phase", "dTim", "dTimStart", "dTimEnd",
               "value", "namingSystem", "versionKind", "createDate", "documentName", "owner"}
SCAFFOLD = set("""what which when where who whom whose how many much were was does did there their across during between from with
that this these those have been being into onto than then also only each every both after before while report reports dated
date daily well wells archive drilling record records following listed state states stated give list name anywhere archive
which all any are the and for not has had its can made make state recorded recorded value values number numbers total
by how much compare comparison difference higher lower deeper deepest largest smallest highest lowest maximum minimum
hold holds held kept keep contain contains contained include includes included show shows shown say says said mention mentions
mentioned exist exists existed different distinct various several about around over under used use using take taken took
carried out done performed observed reported reading readings noted note notes during while rig made make come came put
get got got given tell describe describes described provide provides provided identify identified appear appears appeared
amount level levels size sizes kind kinds sort type types item items thing things part parts instance
january february march april june july august september october november december sept monday tuesday wednesday thursday
friday saturday sunday""".split())


def intents(question: str) -> set[str]:
    out = set()
    if COUNT_RX.search(question):
        out.add("count")
    if EXTREMUM_RX.search(question):
        out.add("extremum")
    if COMPARE_RX.search(question):
        out.add("compare")
    return out


def _clean(question: str) -> str:
    text = question
    for m in sorted(find_wells(text), key=lambda m: -m.start):
        text = text[:m.start] + " " + text[m.end:]
    text = re.sub(r"\d{4}-\d{2}-\d{2}(?:[T ]\d{1,2}:\d{2}(?::\d{2})?)?|(?<![\d:])\d{1,2}:\d{2}(?![\d:])", " ", text)
    return text.lower()


def content_terms(question: str) -> list[str]:
    """Distinctive words of the question (stems): no scaffolding, wells, dates, times or numbers."""
    words = re.findall(r"[a-z][a-z]{3,}", _clean(question))
    return list(dict.fromkeys(_stem(w) for w in words if w not in SCAFFOLD and _stem(w) not in SCAFFOLD))


def field_parts(name: str) -> list[str]:
    parts = [p.lower() for seg in name.split("/") for p in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", seg)]
    return [p for p in parts if len(p) > 1]


def field_matches(name: str, question: str) -> bool:
    """True when every part of the field's name (or its standard expansion) is covered by the question's words."""
    if name in SKIP_FIELDS:
        return False
    parts = field_parts(name)
    if not parts:
        return False
    text = _clean(question)
    squashed = re.sub(r"[^a-z]", "", text)
    stems = {_stem(w) for w in re.findall(r"[a-z]+", text)}
    covered = 0
    for p in parts:
        exp = ABBREV.get(p, "")
        ok = (len(p) >= 4 and p in squashed) or _stem(p) in stems
        if not ok and exp:
            words = {_stem(w) for w in exp.split()}
            ok = (p in ("md", "tvd") and "depth" in stems) or (words and words <= stems) or (len(words) == 1 and words <= stems)
        if not ok:
            return False
        covered += 1
    return covered >= 2 or (len(parts) == 1 and len(parts[0]) >= 4 and parts[0] in squashed)


_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass
class Entry:
    record_id: str
    well: str
    report_date: str
    value: object          # float or ISO date string
    unit: str


def field_entries(cand: pd.DataFrame, name: str, text: bool = False) -> list[Entry]:
    """(record, value) pairs of a field over the candidate records: the record's own field or a sub-field in its attrs.
    Numeric and date values; with text=True also short text values (for counting distinct values)."""
    out: list[Entry] = []
    short = lambda x: isinstance(x, str) and 0 < len(x) <= 60
    for _, r in cand[cand["section"] != "note"].iterrows():
        if r["field"] == name and not r["missing"]:
            v = r["value_num"] if pd.notna(r["value_num"]) else (str(r["value"]) if (_DATE.fullmatch(str(r["value"])) or (text and short(r["value"]))) else None)
            if v is not None:
                out.append(Entry(r["record_id"], r["well"], r["report_date"], v, r["unit"] if isinstance(r["unit"], str) else ""))
        a = json.loads(r["attrs"]) if isinstance(r["attrs"], str) else {}
        e = a.get(name)
        if isinstance(e, dict) and e.get("value") is not None:
            v = e["value"]
            if isinstance(v, (int, float)) or (isinstance(v, str) and (_DATE.fullmatch(v) or (text and short(v)))):
                out.append(Entry(r["record_id"], r["well"], r["report_date"], v, e.get("unit") or ""))
    return out


def _fmt(v) -> str:
    return v if isinstance(v, str) else (str(int(v)) if float(v) == int(v) else repr(round(float(v), 6)))


@dataclass
class Aggregates:
    lines: list[str] = field(default_factory=list)
    agg: dict[str, dict] = field(default_factory=dict)     # agg id -> {"text", "sources"}
    record_ids: list[str] = field(default_factory=list)    # real records whose lines must be shown (the table)
    notes: list[str] = field(default_factory=list)


def field_table(question: str, cand: pd.DataFrame, max_fields: int = 3, max_rows: int = 60) -> Aggregates:
    """For numeric / date fields whose name matches the question: one aggregate line (count, min, max, with the records
    they come from) and the per-report values as real records."""
    res = Aggregates()
    names = set()
    for _, r in cand[cand["section"] != "note"].iterrows():
        names.add(r["field"])
        if isinstance(r["attrs"], str):
            names |= set(json.loads(r["attrs"]))
    matched = sorted((n for n in names if field_matches(n, question)), key=lambda n: (-len(field_parts(n)), n))[:max_fields]
    for name in matched:
        ents = field_entries(cand, name)
        if not ents:
            ents = field_entries(cand, name, text=True)
            if ents and all(isinstance(e.value, str) for e in ents):
                counts: dict[str, list[Entry]] = {}
                for e in ents:
                    counts.setdefault(e.value, []).append(e)
                agg_id = f"AGG-{AGG_DATE}-{re.sub('[^A-Z0-9]', '', name.upper())}"
                top = sorted(counts.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:8]
                text = (f"computed over {len({(e.well, e.report_date) for e in ents})} routed report(s) from {len(ents)} record(s): "
                        f"field={name}; count={len(ents)}; distinct_values={len(counts)}; "
                        + "; ".join(f"'{v}' in {len(es)} record(s)" for v, es in top))
                res.lines.append(f"[{agg_id}] aggregate | {text} | report - | at -")
                res.agg[agg_id] = {"text": text, "sources": list(dict.fromkeys(e.record_id for e in ents))[:40]}
                res.record_ids += [e.record_id for e in ents[:max_rows]]
            continue
        vals = [e.value for e in ents]
        kind = "date" if isinstance(vals[0], str) else "num"
        if any(isinstance(v, str) != (kind == "date") for v in vals):
            continue
        lo, hi = min(vals), max(vals)
        at = lambda x: [e for e in ents if e.value == x]
        unit = next((e.unit for e in ents if e.unit), "")
        reports = len({(e.well, e.report_date) for e in ents})
        agg_id = f"AGG-{AGG_DATE}-{re.sub('[^A-Z0-9]', '', name.upper())}"
        lo_e, hi_e = at(lo), at(hi)
        who = lambda es: ", ".join(f"{e.well} {e.report_date}" for e in es[:6]) + (f" (+{len(es) - 6} more)" if len(es) > 6 else "")
        text = (f"computed over {reports} routed report(s) from {len(ents)} record(s): field={name}; count={len(ents)}; "
                f"min={_fmt(lo)}{' ' + unit if unit else ''} in {len(lo_e)} record(s) [{who(lo_e)}]; "
                f"max={_fmt(hi)}{' ' + unit if unit else ''} in {len(hi_e)} record(s) [{who(hi_e)}]; "
                f"distinct_values={len(set(vals))}")
        res.lines.append(f"[{agg_id}] aggregate | {text} | report - | at -")
        res.agg[agg_id] = {"text": text, "sources": list(dict.fromkeys(e.record_id for e in lo_e + hi_e))}
        res.record_ids += [e.record_id for e in ents[:max_rows]]
        if len(ents) > max_rows:
            res.notes.append(f"field table {name}: first {max_rows} of {len(ents)} records listed")
    return res


def archive_index(records: pd.DataFrame, named_wells: list[str]) -> Aggregates:
    """Wellbores, reports per wellbore and date range per wellbore, from the whole store. The cited sources are the
    reportNo record of each report (or the report's first record when it has none)."""
    res = Aggregates()
    rep = records[records["section"] != "note"]
    per = rep.groupby(["well", "report_date", "source_file"], sort=True).size().reset_index()
    wells = sorted(per["well"].unique())
    parts, sources = [], []
    for w in wells:
        g = per[per["well"] == w]
        dates = list(g["report_date"])
        txt = f"{w}: {len(dates)} report(s), {dates[0]}..{dates[-1]}"
        if w in named_wells:
            txt += " (dates " + ", ".join(dates) + ")"
        parts.append(txt)
        for _, r in g.iterrows():
            sub = rep[rep["source_file"] == r["source_file"]]
            pick = sub[sub["field"] == "reportNo"]
            sources.append((pick if len(pick) else sub).sort_values("record_id").iloc[0]["record_id"])
    text = f"computed from the whole archive: wellbores={len(wells)}; reports={len(per)}; " + "; ".join(parts)
    rid = f"IDX-{AGG_DATE}-WELLBORES"
    res.lines.append(f"[{rid}] index | {text} | report - | at -")
    res.agg[rid] = {"text": text, "sources": sources}
    return res


def sections_of_matching_fields(question: str, cand: pd.DataFrame) -> set[str]:
    """Record types (sections) holding a field, or sub-field, whose name matches the question."""
    out: set[str] = set()
    for sec, g in cand[cand["section"] != "note"].groupby("section"):
        names = set(g["field"])
        for a in g["attrs"]:
            if isinstance(a, str):
                names |= set(json.loads(a))
        if any(field_matches(n, question) for n in names):
            out.add(sec)
    return out


def field_catalogue(cand: pd.DataFrame) -> str:
    """Names of the fields that exist in the candidate records, per record type (section)."""
    rows = []
    for sec, g in cand[cand["section"] != "note"].groupby("section", sort=True):
        names = set(g["field"])
        for a in g["attrs"]:
            if isinstance(a, str):
                names |= set(json.loads(a))
        rows.append(f"{sec}: " + ", ".join(sorted(names)))
    return "FIELD CATALOGUE (fields that exist, per record type): " + " | ".join(rows)


def unmatched_terms(question: str, cand: pd.DataFrame) -> tuple[list[str], list[str]]:
    """(terms found, terms not found) among the question's content words, searching the field names (and their
    abbreviation expansions) and the normalised text of every candidate record."""
    terms = content_terms(question)
    if not terms:
        return [], []
    names = set()
    for _, r in cand.iterrows():
        names.add(r["field"])
        if isinstance(r["attrs"], str):
            names |= set(json.loads(r["attrs"]))
    vocab = set()
    for n in names:
        for p in field_parts(n):
            vocab.add(_stem(p))
            vocab |= {_stem(w) for w in ABBREV.get(p, "").split()}
    blob = " ".join(str(x) for x in cand["text"].dropna().tolist()).lower()
    blob = re.sub(r"\s+", " ", blob)
    squash = re.sub(r"[^a-z]", "", blob)
    found, missing = [], []
    for t in terms:
        near = any(len(v) >= 4 and (t.startswith(v) or v.startswith(t)) for v in vocab)     # spudded~spud, completed~complete
        words_ = set(re.findall(r"[a-z]{4,}", blob))
        near = near or any(w.startswith(t[:max(4, len(t) - 3)]) for w in words_)         # drilled~drilling
        (found if (t in vocab or near or re.search(rf"\b{re.escape(t)}", blob) or (len(t) >= 6 and t in squash)) else missing).append(t)
    return found, missing


def absent_search(question: str, cand: pd.DataFrame) -> tuple[str, str, dict] | None:
    """An ABSENT-search record when NONE of the question's content terms occurs in the candidate records' field names
    or text. It names what was searched; the existing field-kind ABSENT records are not touched."""
    found, missing = unmatched_terms(question, cand)
    if found or not missing:
        return None
    stems = sorted({f[:-4] for f in cand["source_file"].unique()})
    rid = "ABSENT-search"
    searched = ", ".join(missing)
    line = (f"[{rid}] absent | Searched field names and normalised text of {len(stems)} report(s) and {len(cand)} record(s) for "
            f"the question's terms ({searched}): none occurs in any of them. | report - | at -")
    return rid, line, {"kind": searched, "reports": len(stems), "records": len(cand), "files": stems}
