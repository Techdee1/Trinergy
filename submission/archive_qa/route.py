"""Question router: question text -> candidate reports (or an early abstain).

No LLM, no knowledge of any specific question. It only reads the well names and dates
in the text and matches them against the reports that exist in the archive.

Date rule: a report dated D covers D-1 to D. For a (well, D) target the report dated
exactly D is the match. D+1 is used ONLY when no report exists for that well on D, and
the fallback is written into `reason`. Wells are always filtered before dates (F-1-B
and F-1-C both have a 2014-02-22 report).

Pairing wells with dates: each date attaches to the nearest well mentioned BEFORE it
(else the nearest after). If the text has exactly one distinct date, it applies to
every well named.

early_abstain is set only when nothing in the archive matches the named well/date
targets. It never looks at the topic: field-level absence is decided later.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from . import config
from .wells import Report, discover_reports, find_wells, known_wells

# ------------------------------------------------------------------ topics

# topic regex -> record sections (see parse.py). "cost", "personnel", "supervisor" and
# "weather" are sections that do not exist in the store; has_field() reports that.
TOPICS: list[tuple[str, list[str]]] = [
    (r"\bfluid|\bmud\b(?! ?logg)(?<!equivalent mud)|(?<!equivalent )mud weight|density|brine|\bpit\b|viscos|enviromul|hpwbm|ultidrill|flowline", ["fluid"]),
    (r"pore pressure|equivalent mud weight|\bemw\b", ["pore_pressure"]),
    (r"survey|inclination|azimuth|deviation|gyro", ["survey"]),
    (r"casing|liner|\bshoe\b|inside diameter|outside diameter|\bn-80\b", ["casing"]),
    (r"\bbit\b|\brops?\b|rate of penetration|penetration rate", ["bit", "status"]),
    (r"\bgas\b|methane|trip gas|mud logging|mudlogging", ["gas", "log"]),
    (r"logging|log run|wireline|tractor|perforat", ["log", "activity"]),
    (r"lithology|\bshows?\b|claystone|sandstone", ["lithology"]),
    (r"formation top|stratigraph", ["strat"]),
    (r"formation strength|kick-?off|leak.?off|\blot\b|\bfit\b|pressure test", ["status", "activity"]),
    (r"\bdepth\b|\btd\b|spud|water depth|report number|\brig\b|operator|contractor", ["status", "wellbore"]),
    (r"failure|failed|breakdown|replacement part|repair|trouble|problem", ["equip_failure", "activity"]),
    (r"operation|activity|activities|\bbha\b|\bbop\b|riser|skid|slip|cut |laid down|lay down|run in hole|\brih\b|"
     r"pull|stuck|suspend|labour|strike|industrial action|tripp|ream|work(ed)? (the )?(string|pipe)|"
     r"connector|landed|moved|move between", ["activity"]),
    (r"summary|say about|what happened|reported", ["summary_24h", "activity"]),
    (r"forecast|planned", ["forecast_24h"]),
    (r"\bcosts?\b|\bafe\b|spread cost|price|expens", ["cost"]),
    (r"personnel|\bpob\b|people on board|headcount|crew (size|count|member|number)|number of crew|crew on board", ["personnel"]),
    (r"supervisor|superintendent|toolpusher|\boim\b|engineer on duty", ["supervisor"]),
    (r"weather|sea state|\bwaves?\b|\bwind\b|swell", ["weather"]),
]

# ------------------------------------------------------------------ dates

_MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
_MONTHS.update({name.lower(): i for i, name in enumerate(calendar.month_abbr) if name})
_MONTHS["sept"] = 9
_MON = "|".join(sorted(_MONTHS, key=len, reverse=True))
_ISO = re.compile(r"(?<![\d-])(\d{4})-(\d{2})-(\d{2})(?![\d-])")
_DMY = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MON})\.?,?\s+(\d{{4}})\b", re.IGNORECASE)
_MDY = re.compile(rf"\b({_MON})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b", re.IGNORECASE)
_MY = re.compile(rf"\b({_MON})\.?,?\s+(\d{{4}})\b", re.IGNORECASE)
# a 4-digit year, but not a depth such as "2000 mMD" or part of a decimal / range
_YEAR = re.compile(
    r"(?<![\d./-])(19[5-9]\d|20[0-4]\d)(?![\d-])(?!\s*(?:m\b|mmd|mtvd|bar\b|psi\b|ppm\b|ft\b|kg|g/cm|sg\b|m/h))",
    re.IGNORECASE,
)
_RANGE = re.compile(
    r"\bfrom\b[^.?]*?(\d{4}-\d{2}-\d{2})[^.?]*?\bto\b[^.?]*?(\d{4}-\d{2}-\d{2})"
    r"|\bbetween\b[^.?]*?(\d{4}-\d{2}-\d{2})[^.?]*?\band\b[^.?]*?(\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DateMention:
    kind: str   # "day" | "month" | "year"
    iso: str    # YYYY-MM-DD | YYYY-MM | YYYY
    start: int
    end: int


def _valid_day(y: int, m: int, d: int) -> str | None:
    try:
        return date(y, m, d).isoformat()
    except ValueError:
        return None


def find_dates(text: str) -> list[DateMention]:
    """Days, month-years and bare years in order of appearance (no overlaps)."""
    found: list[DateMention] = []

    def free(m: re.Match) -> bool:
        return all(m.end() <= f.start or m.start() >= f.end for f in found)

    def add(kind: str, iso: str | None, m: re.Match) -> None:
        if iso and free(m):
            found.append(DateMention(kind, iso, m.start(), m.end()))

    for m in _ISO.finditer(text):
        add("day", _valid_day(int(m[1]), int(m[2]), int(m[3])), m)
    for m in _DMY.finditer(text):
        add("day", _valid_day(int(m[3]), _MONTHS[m[2].lower()], int(m[1])), m)
    for m in _MDY.finditer(text):
        add("day", _valid_day(int(m[3]), _MONTHS[m[1].lower()], int(m[2])), m)
    for m in _MY.finditer(text):
        add("month", f"{int(m[2]):04d}-{_MONTHS[m[1].lower()]:02d}", m)
    for m in _YEAR.finditer(text):
        add("year", m[1], m)
    return sorted(found, key=lambda d: d.start)


# ------------------------------------------------------------------ result


@dataclass
class RouteResult:
    wells: list[str] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)       # days, months, years as written
    date_range: tuple[str, str] | None = None
    candidate_files: list[str] = field(default_factory=list)  # report stems (XML names without .xml)
    mode: str = "archive_wide"                            # single_report | multi_report | archive_wide
    sections: list[str] = field(default_factory=list)
    early_abstain: bool = False
    reason: str = ""
    # (well or None, day or None, message) for each named target with no matching report
    unmatched: list[tuple[str | None, str | None, str]] = field(default_factory=list)

    def as_row(self) -> dict:
        return {
            "wells": "; ".join(self.wells),
            "dates": "; ".join(self.dates + ([f"{self.date_range[0]}..{self.date_range[1]}"] if self.date_range else [])),
            "mode": self.mode,
            "candidate_files": "; ".join(self.candidate_files),
            "sections": "; ".join(self.sections),
            "early_abstain": self.early_abstain,
            "reason": self.reason,
        }


def topic_sections(text: str) -> list[str]:
    out: list[str] = []
    low = text.lower()
    for pattern, sections in TOPICS:
        if re.search(pattern, low):
            out += [s for s in sections if s not in out]
    return out


def _in_period(r: Report, period: str) -> bool:
    return r.iso.startswith(period)


def _nearby(reports: list[Report], well: str, limit: int = 6) -> str:
    dates = [r.iso for r in reports if r.well == well]
    if len(dates) > limit:
        dates = dates[:limit] + ["..."]
    return ", ".join(dates)


def route_question(question: str, reports: list[Report] | None = None) -> RouteResult:
    """Route one question. `reports` defaults to the archive on disk."""
    reports = reports if reports is not None else discover_reports(config.XML_DIR)
    by_key = {(r.well, r.iso): r for r in reports}
    archive_wells = set(known_wells(reports))

    wmentions = find_wells(question)
    wells = list(dict.fromkeys(m.well for m in wmentions))
    dmentions = find_dates(question)
    days = [d for d in dmentions if d.kind == "day"]
    periods = [d.iso for d in dmentions if d.kind in ("month", "year")]

    res = RouteResult(wells=wells, dates=[d.iso for d in dmentions], sections=topic_sections(question))
    selected: dict[str, str] = {}   # stem -> why
    notes: list[str] = []
    unmatched: list[str] = []
    unmatched_t: list[tuple[str | None, str | None, str]] = []
    targets = 0

    # --- date range ("from X to Y" / "between X and Y"), only with ISO dates
    range_dates: set[str] = set()
    rm = _RANGE.search(question)
    if rm:
        a, b = sorted([x for x in rm.groups() if x])
        res.date_range = (a, b)
        range_dates = {a, b}

    # --- pair each day with a well
    def well_for(d: DateMention) -> str | None:
        before = [m for m in wmentions if m.end <= d.start]
        if before:
            return before[-1].well
        after = [m for m in wmentions if m.start >= d.end]
        return after[0].well if after else None

    distinct_days = list(dict.fromkeys(d.iso for d in days))
    pairs: list[tuple[str | None, str]] = []  # (well or None, day)
    used_wells: set[str] = set()
    for d in days:
        if d.iso in range_dates and res.date_range:
            w = well_for(d)
            if w:
                used_wells.add(w)
            continue
        if len(distinct_days) == 1 and wells:
            for w in wells:
                pairs.append((w, d.iso))
                used_wells.add(w)
        else:
            w = well_for(d)
            pairs.append((w, d.iso))
            if w:
                used_wells.add(w)
    pairs = list(dict.fromkeys(pairs))

    # --- range target
    if res.date_range:
        a, b = res.date_range
        targets += 1
        scope = [wells[0]] if len(wells) == 1 else None
        hits = [r for r in reports if a <= r.iso <= b and (scope is None or r.well == scope[0])]
        where = f"well {scope[0]}" if scope else "all wells (range spans wells)"
        if hits:
            for r in hits:
                selected.setdefault(r.stem, f"range {a}..{b}")
            notes.append(f"range {a}..{b}: {len(hits)} report(s) for {where}")
        else:
            unmatched.append(f"no report in range {a}..{b} for {where}")
            unmatched_t.append((scope[0] if scope else None, None, unmatched[-1]))

    # --- (well, day) targets
    for w, day in pairs:
        targets += 1
        d1 = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
        cands = [r for r in reports if (w is None or r.well == w)]
        exact = [r for r in cands if r.iso == day]
        label = f"{w or 'any well'} on {day}"
        if exact:
            for r in exact:
                selected.setdefault(r.stem, f"exact date {day}")
            notes.append(f"exact: {label} -> {', '.join(r.stem for r in exact)}")
            continue
        nxt = [r for r in cands if r.iso == d1]
        if nxt:
            for r in nxt:
                selected.setdefault(r.stem, f"fallback D+1 {d1}")
            notes.append(f"FALLBACK D+1: no report for {label}; used report dated {d1} -> "
                         f"{', '.join(r.stem for r in nxt)}")
            continue
        if w is not None and w not in archive_wells:
            unmatched.append(f"well {w} is not in the archive (no report for {label})")
        elif w is not None:
            unmatched.append(f"no report for {label} or {d1}; reports for {w}: {_nearby(reports, w)}")
        else:
            unmatched.append(f"no report dated {day} or {d1} for any well")
        unmatched_t.append((w, day, unmatched[-1]))

    # --- wells without a date of their own: all their reports, narrowed by month/year if given
    for w in wells:
        if w in used_wells:
            continue
        targets += 1
        hits = [r for r in reports if r.well == w and (not periods or any(_in_period(r, p) for p in periods))]
        span = f" in {', '.join(periods)}" if periods else ""
        if hits:
            for r in hits:
                selected.setdefault(r.stem, f"well {w}{span}")
            notes.append(f"well {w}{span}: {len(hits)} report(s)")
        elif w not in archive_wells:
            unmatched.append(f"well {w} is not in the archive")
            unmatched_t.append((w, None, unmatched[-1]))
        else:
            unmatched.append(f"no report for well {w}{span}; reports: {_nearby(reports, w)}")
            unmatched_t.append((w, None, unmatched[-1]))

    # --- no well at all, no day, no range: periods (all wells) or the whole archive
    if not wells and not days and not res.date_range:
        if periods:
            targets += 1
            hits = [r for r in reports if any(_in_period(r, p) for p in periods)]
            if hits:
                for r in hits:
                    selected.setdefault(r.stem, f"period {', '.join(periods)}")
                notes.append(f"period {', '.join(periods)}: {len(hits)} report(s), all wells")
            else:
                unmatched.append(f"no report in {', '.join(periods)}")
                unmatched_t.append((None, None, unmatched[-1]))
        else:
            res.mode = "archive_wide"
            res.candidate_files = [r.stem for r in reports]
            res.reason = f"no well or date named: whole archive ({len(reports)} reports)"
            return res

    # --- assemble
    order = {r.stem: (r.well, r.report_date) for r in reports}
    res.candidate_files = sorted(selected, key=lambda s: order[s])
    res.unmatched = unmatched_t
    if not res.candidate_files:
        res.early_abstain = True
        res.mode = "single_report" if targets <= 1 else "multi_report"
        res.reason = "EARLY ABSTAIN: " + "; ".join(unmatched)
        return res
    res.mode = "single_report" if len(res.candidate_files) == 1 else "multi_report"
    parts = notes + [f"UNMATCHED (not abstaining, other targets matched): {u}" for u in unmatched]
    res.reason = "; ".join(parts)
    return res


# ------------------------------------------------------------------ batch


def load_questions(path: Path | None = None) -> pd.DataFrame:
    return pd.read_csv(path or config.QUESTIONS_CSV, encoding="utf-8-sig")


def route_all(questions: pd.DataFrame | None = None, reports: list[Report] | None = None) -> pd.DataFrame:
    """Route every question; returns the routing report."""
    questions = questions if questions is not None else load_questions()
    reports = reports if reports is not None else discover_reports(config.XML_DIR)
    rows = []
    for q in questions.itertuples(index=False):
        rows.append({"question_id": q.question_id, **route_question(q.question_text, reports).as_row()})
    return pd.DataFrame(rows)


def save_routing_report(report: pd.DataFrame, path: Path | None = None) -> Path:
    path = Path(path or config.ROUTING_REPORT_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(path, index=False)
    return path
