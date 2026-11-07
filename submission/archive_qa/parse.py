"""WITSML 1.4 drillReport XML -> evidence records.

One record per fact (header / status / wellbore fields) or per table row
(activity, fluid sample, survey station, casing joint, bit, ...).

Conventions
- `value` is the raw XML text (None when the XML says -999.99); `value_num` is its
  numeric parse (NaN if not numeric). -999.99 is never written as a value.
- `attrs` is a JSON string of the row's other fields: {"md": {"value": 4094, "unit": "m"}, ...}.
  A "raw" key appears only when the XML text differs from the JSON number (".21" -> 0.21).
- Timestamps are local wall-clock ISO strings (the +01:00/+02:00 offset is dropped).
- report_date is the FILE date = END of the 24 h window; period_start/period_end
  make that window explicit (a report dated D covers D-1 to D).
"""

from __future__ import annotations

import json
import math
import re
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .wells import Report, canonical_well, discover_reports, well_code

NS = "{http://www.witsml.org/schemas/1series}"
SENTINEL = "-999.99"  # WITSML "no value"
NONE_STRING_FIELDS = {"sum24Hr", "forecast24Hr"}  # the literal text "None" means missing

# XML child of <drillReport> -> (section, id code). Unknown tags get a generic row section.
ROW_SECTIONS = {
    "activity": ("activity", "ACT"),
    "fluid": ("fluid", "FLUID"),
    "surveyStation": ("survey", "SURVEY"),
    "casing_liner_tubing": ("casing", "CASING"),
    "bitRecord": ("bit", "BIT"),
    "porePressure": ("pore_pressure", "PORE"),
    "gasReadingInfo": ("gas", "GAS"),
    "lithShowInfo": ("lithology", "LITH"),
    "stratInfo": ("strat", "STRAT"),
    "logInfo": ("log", "LOG"),
    "equipFailureInfo": ("equip_failure", "FAIL"),
}
# The field that represents the row in `field`/`value`/`unit`; everything else -> attrs.
ROW_MAIN_FIELD = {
    "activity": "comments",
    "fluid": "density",
    "surveyStation": "incl",
    "casing_liner_tubing": "od",
    "bitRecord": "diaBit",
    "porePressure": "equivalentMudWeight",
    "gasReadingInfo": "gasHigh",
    "lithShowInfo": "lithology",
    "stratInfo": "description",
    "logInfo": "tool",
    "equipFailureInfo": "description",
}
ROW_TIME_FIELDS = ("dTim", "dTimStart", "casing_liner_tubing_run/dTimStart")

HEADER_TAGS = {"nameWell", "nameWellbore", "createDate", "versionKind", "wellAlias", "wellboreAlias"}
SKIP_TAGS = {"name", "dTimStart", "dTimEnd"}  # dTimStart/End become period_* columns; <name> is a placeholder

RECORD_COLUMNS = [
    "record_id", "well", "report_date", "period_start", "period_end", "section", "field",
    "value", "value_num", "unit", "missing", "timestamp", "text", "attrs",
    "source_file", "pdf_file", "pdf_page", "pdf_section", "pdf_match",
]

_TZ = re.compile(r"(?<=T\d\d:\d\d:\d\d)(?:Z|[+-]\d\d:\d\d)$")
_WS = re.compile(r"\s+")


@dataclass
class ParseStats:
    reports: int = 0
    sentinels_dropped: int = 0
    none_strings_converted: int = 0
    date_mismatches: list[str] = field(default_factory=list)
    well_mismatches: list[str] = field(default_factory=list)

    def merge(self, other: "ParseStats") -> None:
        self.reports += other.reports
        self.sentinels_dropped += other.sentinels_dropped
        self.none_strings_converted += other.none_strings_converted
        self.date_mismatches += other.date_mismatches
        self.well_mismatches += other.well_mismatches


# ------------------------------------------------------------------ helpers


def local_time(text: str | None) -> str | None:
    """'2014-03-25T21:00:00+01:00' -> '2014-03-25T21:00:00' (wall-clock)."""
    return _TZ.sub("", text) if text else text


def to_number(text: str) -> int | float | None:
    try:
        x = float(text)
    except ValueError:
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return int(x) if re.fullmatch(r"-?\d+", text.strip()) else x


def _leaves(elem: ET.Element, prefix: str = "", seen: Counter | None = None) -> list[tuple[str, str, str | None, str | None]]:
    """Flatten an element to (path, text, uom, datum). Repeated paths get #2, #3 ...

    With `seen` (a Counter) the count is shared with nested blocks, so two sibling blocks such as <nozzle> ... <nozzle>
    keep both ("nozzle/numNozzle", "nozzle/numNozzle#2") instead of the second overwriting the first. Table rows use
    this. Without it (header / status / wellbore fields, where every leaf becomes its own record and make_id numbers the
    duplicates) the counting stays per block, which keeps those record ids unchanged."""
    out: list[tuple[str, str, str | None, str | None]] = []
    local = Counter() if seen is None else seen
    for child in elem:
        tag = child.tag.replace(NS, "")
        path = prefix + tag
        if len(child):
            out.extend(_leaves(child, path + "/", seen))
            continue
        local[path] += 1
        key = path if local[path] == 1 else f"{path}#{local[path]}"
        out.append((key, (child.text or "").strip(), child.get("uom"), child.get("datum")))
    return out


class _Ctx:
    """Per-report state: ids, counters, stats."""

    def __init__(self, report: Report, period: tuple[str | None, str | None], stats: ParseStats):
        self.report = report
        self.period = period
        self.stats = stats
        self.counters: Counter = Counter()
        self.rows: list[dict] = []

    def clean(self, name: str, text: str) -> tuple[str | None, bool]:
        """Return (value, missing). Applies the -999.99 and "None" rules."""
        base = name.split("/")[-1].split("#")[0]
        if text == SENTINEL:
            self.stats.sentinels_dropped += 1
            return None, True
        if text == "" or (base in NONE_STRING_FIELDS and text == "None"):
            if text == "None":
                self.stats.none_strings_converted += 1
            return None, True
        return local_time(text), False

    def make_id(self, code: str, key: str | None) -> str:
        r = self.report
        stem = f"{well_code(r.well)}-{r.iso.replace('-', '')}-{code}"
        if key is None:  # table row: running index
            self.counters[stem] += 1
            return f"{stem}-{self.counters[stem]:02d}"
        base = f"{stem}-{key.upper().replace('/', '_').replace('#', '_')}"
        self.counters[base] += 1
        return base if self.counters[base] == 1 else f"{base}-{self.counters[base]:02d}"

    def add(self, *, record_id, section, field_name, value, unit, missing, timestamp, text, attrs):
        r = self.report
        num = to_number(value) if value is not None else None
        self.rows.append({
            "record_id": record_id, "well": r.well, "report_date": r.iso,
            "period_start": self.period[0], "period_end": self.period[1],
            "section": section, "field": field_name, "value": value,
            "value_num": float(num) if num is not None else float("nan"),
            "unit": unit, "missing": missing, "timestamp": timestamp, "text": text,
            "attrs": json.dumps(attrs, ensure_ascii=False) if attrs is not None else None,
            "source_file": r.xml_path.name, "pdf_file": r.stem + ".pdf",
            "pdf_page": None, "pdf_section": None, "pdf_match": None,
        })


def _fmt(value, unit) -> str:
    s = str(value)
    return f"{s} {unit}" if unit else s


def _line(r: Report, where: str, body: str) -> str:
    return _WS.sub(" ", f"{r.well} | report {r.iso} | {where} | {body}").strip()


# ------------------------------------------------------------------ parsing


def _field_records(ctx: _Ctx, elem: ET.Element, section_for) -> None:
    """Header/status/wellbore: one record per leaf field."""
    for path, text, uom, _datum in _leaves(elem):
        name = path.split("#")[0]
        section, code = section_for(name)
        value, missing = ctx.clean(path, text)
        # rigAlias/name + rigAlias/namingSystem etc. stay separate, simple leaf records
        body = f"{name} = {_fmt(value, uom)}" if not missing else f"{name} = (no value reported)"
        ctx.add(record_id=ctx.make_id(code, path), section=section, field_name=name,
                value=value, unit=uom, missing=missing, timestamp=None,
                text=_line(ctx.report, section, body), attrs=None)


def _alias_record(ctx: _Ctx, elem: ET.Element, tag: str) -> None:
    """wellAlias / wellboreAlias: name + namingSystem."""
    kids = {c.tag.replace(NS, ""): (c.text or "").strip() for c in elem}
    name, system = kids.get("name", ""), kids.get("namingSystem", "")
    ctx.add(record_id=ctx.make_id("HDR", tag), section="header", field_name=tag,
            value=name or None, unit=None, missing=not name, timestamp=None,
            text=_line(ctx.report, "header", f"{tag} = {name} ({system})"),
            attrs={"namingSystem": {"value": system}})


def _row_record(ctx: _Ctx, elem: ET.Element, tag: str) -> None:
    section, code = ROW_SECTIONS.get(tag, (tag.lower(), tag.upper()[:6]))
    leaves = _leaves(elem, seen=Counter())
    main = ROW_MAIN_FIELD.get(tag) or (leaves[0][0] if leaves else "")
    attrs: dict[str, dict] = {}
    main_value, main_unit, main_missing = None, None, True
    parts: list[str] = []
    timestamp = None
    for path, text, uom, datum in leaves:
        value, missing = ctx.clean(path, text)
        if path in ROW_TIME_FIELDS and timestamp is None and value:
            timestamp = value
        if path == main:
            main_value, main_unit, main_missing = value, uom, missing
            continue
        entry: dict = {"value": None}
        if value is not None:
            num = to_number(value)
            entry["value"] = num if num is not None else value
            if num is not None and json.dumps(num) != value:
                entry["raw"] = value
        if uom:
            entry["unit"] = uom
        if datum:
            entry["datum"] = datum
        attrs[path] = entry
        if value is not None:
            parts.append(f"{path}={_fmt(value, uom)}")
    body = f"{main}={_fmt(main_value, main_unit)}" if not main_missing else f"{main}=(no value reported)"
    when = f" @{timestamp}" if timestamp else ""
    ctx.add(record_id=ctx.make_id(code, None), section=section, field_name=main,
            value=main_value, unit=main_unit, missing=main_missing, timestamp=timestamp,
            text=_line(ctx.report, section + when, "; ".join([body] + parts)), attrs=attrs)


def parse_report(report: Report) -> tuple[list[dict], ParseStats]:
    """Parse one XML file. ElementTree honours the encoding declared in the file
    (ISO-8859-1 for most; the four 15/9-19-A files declare none and are plain ASCII)."""
    stats = ParseStats(reports=1)
    root = ET.parse(report.xml_path).getroot()
    dr = root.find(NS + "drillReport")
    if dr is None:
        raise ValueError(f"{report.xml_path.name}: no drillReport element")

    start = local_time(dr.findtext(NS + "dTimStart"))
    end = local_time(dr.findtext(NS + "dTimEnd"))
    if not end or end[:10] != report.iso:
        stats.date_mismatches.append(f"{report.stem}: file date {report.iso} vs dTimEnd {end}")
    xml_well = canonical_well(dr.findtext(NS + "nameWellbore") or "")
    if xml_well != report.well:
        stats.well_mismatches.append(f"{report.stem}: file well {report.well} vs XML {xml_well}")

    ctx = _Ctx(report, (start, end), stats)

    def status_section(name: str) -> tuple[str, str]:
        if name == "sum24Hr":
            return "summary_24h", "SUM"
        if name == "forecast24Hr":
            return "forecast_24h", "FCST"
        return "status", "STATUS"

    for child in dr:
        tag = child.tag.replace(NS, "")
        if tag in SKIP_TAGS:
            continue
        if tag in ("wellAlias", "wellboreAlias"):
            _alias_record(ctx, child, tag)
        elif tag in HEADER_TAGS:
            _field_records(ctx, _wrap(child), lambda n: ("header", "HDR"))
        elif tag == "wellboreInfo":
            _field_records(ctx, child, lambda n: ("wellbore", "WELL"))
        elif tag == "statusInfo":
            _field_records(ctx, child, status_section)
        else:
            _row_record(ctx, child, tag)
    return ctx.rows, stats


def _wrap(leaf: ET.Element) -> ET.Element:
    """Treat a direct leaf child of drillReport as a one-field container."""
    holder = ET.Element("holder")
    holder.append(leaf)
    return holder


def parse_all(xml_dir: Path, reports: list[Report] | None = None) -> tuple[pd.DataFrame, ParseStats]:
    reports = reports or discover_reports(xml_dir)
    rows: list[dict] = []
    stats = ParseStats()
    for rep in reports:
        r, s = parse_report(rep)
        rows += r
        stats.merge(s)
    df = pd.DataFrame(rows, columns=RECORD_COLUMNS)
    dupes = df["record_id"].duplicated().sum()
    if dupes:
        raise ValueError(f"{dupes} duplicate record_ids")
    return df, stats


def print_counts(df: pd.DataFrame, stats: ParseStats | None = None) -> None:
    per_section = df.groupby("section").size().sort_values(ascending=False)
    per_report = df.groupby(["well", "report_date"]).size()
    print(f"{len(df)} records from {df['source_file'].nunique()} reports\n")
    print("Records per section:\n" + per_section.to_string() + "\n")
    print("Records per report:\n" + per_report.to_string() + "\n")
    if stats:
        print(f"-999.99 sentinels converted to missing: {stats.sentinels_dropped}")
        print(f'Literal "None" summary/forecast strings converted to missing: {stats.none_strings_converted}')
        print(f"File-date vs dTimEnd mismatches: {len(stats.date_mismatches)}; "
              f"file-well vs XML-well mismatches: {len(stats.well_mismatches)}")
