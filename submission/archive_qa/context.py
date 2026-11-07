"""Evidence context for the LLM: compact, deterministic lines the model may cite.

Line format:  [RECORD_ID] section | key fields with units | report date | event timestamp
Reports are introduced by a header line (well, report date, period). Nothing in the text depends on
time, machine or absolute paths, so the cache keys match on the reviewers' machine.

Selection
  single_report   the router's topic sections (+ the 24 h summary/forecast), whole sections
  multi/archive   narrative records (activities, summaries, forecasts, equipment failures) plus topic
                  sections from the candidate reports, ranked by keyword overlap with the question and
                  capped at ~12k tokens; truncation is recorded
Topics with no field in the archive (has_field is False) add a citeable [ABSENT-<kind>] pseudo-record.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import config
from .route import RouteResult
from .store import has_field

SECTION_ORDER = ["status", "wellbore", "summary_24h", "forecast_24h", "activity", "fluid", "survey",
                 "casing", "bit", "pore_pressure", "gas", "lithology", "strat", "log", "equip_failure"]
NARRATIVE = ["summary_24h", "forecast_24h", "activity", "equip_failure"]
ABSENT_KINDS = ("cost", "personnel", "supervisor", "weather")  # topics that may have no field (see has_field)
TOKEN_CAP = 12_000
CHARS_PER_TOKEN = 4
MAX_FIELD_CHARS = 1500
_STOP = set("the a an and or of on in at to for from was were is are what which who how many much did do does "
            "with by as that this these those it its be been during after before when where while than then "
            "well report reports day days daily drilling".split())


@dataclass
class Context:
    question_id: str
    text: str
    ids: frozenset[str]
    absent: dict[str, dict] = field(default_factory=dict)  # ABSENT id -> {kind, reports, records, files}
    truncated: bool = False
    notes: list[str] = field(default_factory=list)          # what was truncated, for the debug dump
    n_lines: int = 0

    @property
    def est_tokens(self) -> int:
        return math.ceil(len(self.text) / CHARS_PER_TOKEN)


# ------------------------------------------------------------------ line formatting


def _attrs(row) -> dict:
    a = row["attrs"]
    return json.loads(a) if isinstance(a, str) else {}


def _fmt_entry(key: str, entry: dict) -> str:
    v = entry.get("value")
    if v is None:
        return f"{key}=missing"
    s = entry.get("raw") or (v if isinstance(v, str) else json.dumps(v))
    unit = entry.get("unit")
    return f"{key}={s}{' ' + unit if unit else ''}"


def _clip(text: str, notes: list[str], rid: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > MAX_FIELD_CHARS:
        notes.append(f"{rid}: text clipped from {len(text)} to {MAX_FIELD_CHARS} chars")
        return text[:MAX_FIELD_CHARS] + " ...[clipped]"
    return text


def key_fields(row, notes: list[str]) -> str:
    """'density=1.03 g/cm3; type=NaCl brine; md=4094 m'. Missing values are shown as missing."""
    attrs = _attrs(row)
    skip = {"dTim", "dTimStart"} if isinstance(row["timestamp"], str) else set()
    parts = [_fmt_entry(k, e) for k, e in attrs.items() if k not in skip]
    if row["missing"]:
        main = f"{row['field']}=missing"
    else:
        unit = row["unit"] if isinstance(row["unit"], str) else ""
        val = _clip(str(row["value"]), notes, row["record_id"])
        text_valued = math.isnan(row["value_num"]) and len(val) > 25
        main = f'{row["field"]}="{val}"' if text_valued else f"{row['field']}={val}{' ' + unit if unit else ''}"
        if text_valued:
            return "; ".join(parts + [main])  # long remarks read best last
    return "; ".join([main] + parts)


def format_line(row, notes: list[str]) -> str:
    ts = row["timestamp"] if isinstance(row["timestamp"], str) else "-"
    return f"[{row['record_id']}] {row['section']} | {key_fields(row, notes)} | report {row['report_date']} | at {ts}"


def header_line(well: str, report_date: str, period_start, period_end, stem: str) -> str:
    return f"=== REPORT {well} | report date {report_date} | period {period_start} to {period_end} | file {stem} ==="


# ------------------------------------------------------------------ selection


def _survey_depth(row) -> float:
    md = _attrs(row).get("md", {}).get("value")
    return float(md) if isinstance(md, (int, float)) else float("inf")


def _sorted_section(df: pd.DataFrame, section: str) -> pd.DataFrame:
    """Deterministic order inside a section. Surveys: measured depth ascending (so 'deepest' = last)."""
    if section == "survey":
        d = df.assign(_k=[_survey_depth(r) for _, r in df.iterrows()])
        return d.sort_values(["_k", "record_id"]).drop(columns="_k")
    if section == "activity":
        return df.sort_values(["timestamp", "record_id"], na_position="last")
    return df.sort_values("record_id")


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+(?:/[a-z0-9]+)?", text.lower()) if len(w) > 1 and w not in _STOP}


def _score(q_words: set[str], line: str) -> int:
    return len(q_words & _words(line))


FIELD_STYLE = {"status", "wellbore"}


def rid_in_sections(pool: pd.DataFrame, rid: str, sections: set[str]) -> bool:
    return pool.loc[pool["record_id"] == rid, "section"].iloc[0] in sections


def real_topics(route: RouteResult, available: set[str]) -> list[str]:
    return [s for s in route.sections if s in available]


def absent_topics(route: RouteResult, cand: pd.DataFrame) -> list[str]:
    return [s for s in route.sections if s in ABSENT_KINDS and not has_field(cand, s)]


def _absent_record(kind: str, cand: pd.DataFrame) -> tuple[str, str, dict]:
    stems = sorted({f[:-4] for f in cand["source_file"].unique()})
    dates = sorted(cand["report_date"].unique())
    when = dates[0] if len(dates) == 1 else f"{len(dates)} reports"
    rid = f"ABSENT-{kind}"
    n_rep, n_rec = len(stems), len(cand)
    line = (f"[{rid}] absent | Searched {n_rep} report(s) and {n_rec} record(s): no {kind} field exists "
            f"in any of them | report {when} | at -")
    return rid, line, {"kind": kind, "reports": n_rep, "records": n_rec, "files": stems}


def build_context(question_id: str, question: str, route: RouteResult, records: pd.DataFrame,
                  token_cap: int = TOKEN_CAP) -> Context:
    stems = set(route.candidate_files)
    cand = records[records["source_file"].isin({s + ".xml" for s in stems})]
    notes: list[str] = []
    topics = real_topics(route, set(cand["section"].unique()))
    absent_kinds = absent_topics(route, cand)

    if route.mode == "single_report":
        wanted = set(topics) | {"summary_24h", "forecast_24h"}
        if absent_kinds:
            wanted.add("activity")  # let the model see what the narrative does and does not say
        if not topics and not absent_kinds:
            wanted.add("status")
    else:
        wanted = set(NARRATIVE) | set(topics)
    sections = [s for s in SECTION_ORDER if s in wanted]
    pool = cand[cand["section"].isin(sections)]

    # --- choose records (cap only matters for multi/archive_wide)
    chosen: set[str] = set(pool["record_id"])
    lines: dict[str, str] = {r["record_id"]: format_line(r, notes) for _, r in pool.iterrows()}
    # keyword scoring looks at the record's own fields only (not the report date / timestamp suffix)
    bodies = {rid: ln.split("] ", 1)[1].rsplit(" | report ", 1)[0] for rid, ln in lines.items()}
    if route.mode != "single_report":
        # many reports: bulky field-style sections only when they share a keyword with the question
        q_words0 = _words(question)
        lines = {rid: ln for rid, ln in lines.items()
                 if not rid_in_sections(pool, rid, FIELD_STYLE) or _score(q_words0, bodies[rid]) > 0}
        chosen = set(lines)
    truncated = False
    budget_chars = token_cap * CHARS_PER_TOKEN - 200 * cand["source_file"].nunique()  # room for headers
    if route.mode != "single_report" and sum(len(v) + 1 for v in lines.values()) > budget_chars:
        q_words = _words(question)
        order = {rid: i for i, rid in enumerate(pool.sort_values(["source_file", "record_id"])["record_id"])}  # row-order independent
        ranked = sorted(lines, key=lambda rid: (-_score(q_words, bodies[rid]), order[rid]))
        used, chosen = 0, set()
        for rid in ranked:
            cost = len(lines[rid]) + 1
            if used + cost > budget_chars:
                continue
            chosen.add(rid)
            used += cost
        dropped = len(lines) - len(chosen)
        truncated = True
        notes.append(f"TRUNCATED: kept {len(chosen)} of {len(lines)} candidate records "
                     f"(cap ~{token_cap} tokens), ranked by keyword overlap; dropped {dropped}")

    # --- render in a fixed order: report, section, record
    out: list[str] = []
    note = route.reason if ("FALLBACK" in route.reason or "UNMATCHED" in route.reason) else ""
    if note:
        out.append(f"ROUTING NOTE: {note}")
    ids: set[str] = set()
    for (well, rdate, src), grp in cand.groupby(["well", "report_date", "source_file"], sort=True):
        picked = grp[grp["record_id"].isin(chosen)]
        if picked.empty and route.mode != "single_report":
            continue
        first = grp.iloc[0]
        out.append(header_line(well, rdate, first["period_start"], first["period_end"], src[:-4]))
        for sec in sections:
            part = picked[picked["section"] == sec]
            if part.empty:
                continue
            for _, r in _sorted_section(part, sec).iterrows():
                out.append(lines[r["record_id"]])
                ids.add(r["record_id"])

    absent: dict[str, dict] = {}
    for kind in absent_kinds:
        rid, line, meta = _absent_record(kind, cand)
        out.append(line)
        ids.add(rid)
        absent[rid] = meta

    return Context(question_id, "\n".join(out), frozenset(ids), absent, truncated, notes, len(out))


def dump_context(ctx: Context, route: RouteResult, question: str, directory: Path | None = None) -> Path | None:
    """Debug dump (git-ignored). Never raises: a read-only checkout must still run."""
    d = Path(directory or config.CONTEXT_DUMP_DIR)
    try:
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{ctx.question_id}.txt"
        head = [f"QUESTION {ctx.question_id}: {question}", f"MODE: {route.mode}",
                f"CANDIDATES: {', '.join(route.candidate_files)}", f"SECTIONS: {', '.join(route.sections)}",
                f"LINES: {ctx.n_lines}  ~TOKENS: {ctx.est_tokens}  TRUNCATED: {ctx.truncated}"]
        head += [f"NOTE: {n}" for n in ctx.notes]
        p.write_text("\n".join(head) + "\n\n" + ctx.text + "\n", encoding="utf-8")
        return p
    except OSError:
        return None
