"""XML-vs-PDF discrepancy NOTE records, derived by code at index time.

For each report the XML value is compared with what the PDF prints, and a NOTE record is created for every
disagreement, e.g.   [NOTE-DISCREPANCY] tightWell: XML 0; PDF prints Y

Checked (all read from the PDF text, nothing typed per report):
  * tightWell / hpht        the Summary-report flags      (XML 0 vs a printed Y)
  * daysAhead / daysBehind  the "Days Ahead/Behind" field (XML value vs a blank or different number)
  * bit run start / end     the Bit Record row            (hours, start mMD, end mMD compared in header order)

The XML is authoritative. The context builder shows a NOTE only when the question mentions the field, so unrelated
questions never see it. NOTE records have section "note" and are never selected as ordinary evidence.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import pymupdf

from .locate import PdfText, raw_of
from .parse import RECORD_COLUMNS
from .wells import well_code

_DAYS = r"days (?:ahead|behind)|ahead of schedule|behind schedule|ahead/behind|schedule status"
_BIT = r"\bbit run\b|\bbit\b.{0,60}\b(?:start|end|stop|depth)|\bend mmd\b|\bhole (?:start|stop|end)\b"
# note field -> regex over a QUESTION that makes the note relevant
NOTE_CONCEPTS: dict[str, str] = {
    "tightWell": r"tight[- ]well", "hpht": r"\bhpht\b|high[- ]pressure[, ]+high[- ]temperature",
    "daysBehind": _DAYS, "daysAhead": _DAYS,
    "bitRun/eTimOpBit": _BIT, "bitRun/mdHoleStart": _BIT, "bitRun/mdHoleStop": _BIT,
}
_TRUE = {"y", "yes", "true", "1"}


def _note(first: pd.Series, field: str, xml_v: str, pdf_v: str, page: int | None, section: str) -> dict:
    well, day = first["well"], first["report_date"]
    rid = f"{well_code(well)}-{day.replace('-', '')}-NOTE-{re.sub(r'[^A-Z0-9]', '_', field.upper())}"
    shown = pdf_v if pdf_v else "(blank)"
    value = f"XML {xml_v}; PDF prints {shown}"
    return {
        "record_id": rid, "well": well, "report_date": day, "period_start": first["period_start"],
        "period_end": first["period_end"], "section": "note", "field": field, "value": value, "value_num": float("nan"),
        "unit": None, "missing": False, "timestamp": None,
        "text": f"{well} | report {day} | note | [NOTE-DISCREPANCY] {field}: {value} (the XML is authoritative)",
        "attrs": json.dumps({"xml": {"value": xml_v}, "pdf": {"value": shown}}, ensure_ascii=False),
        "source_file": first["source_file"], "pdf_file": first["pdf_file"], "pdf_page": page, "pdf_section": section,
        "pdf_match": "exact",
    }


def _flag_and_days_notes(grp: pd.DataFrame, pdf: PdfText) -> list[dict]:
    first, out = grp.iloc[0], []
    m = re.search(r"tightwell:(?P<tw>[^:]*?)hpht:(?P<hp>[^:]*?)temperature", pdf.text)
    for field, key in (("tightWell", "tw"), ("hpht", "hp")):
        rec = grp[(grp["section"] == "status") & (grp["field"] == field) & (~grp["missing"])]
        if rec.empty or m is None:
            continue
        xml_v, pdf_v = str(rec.iloc[0]["value"]), m.group(key)
        if (xml_v.lower() in _TRUE) != (pdf_v in _TRUE) or pdf_v == "":
            out.append(_note(first, field, xml_v, pdf_v.upper(), pdf.page_at(m.start()), "Summary report"))
    d = re.search(r"daysahead/behind\(\+/-\):(?P<v>[^:]*?)operator:", pdf.text)
    for field in ("daysAhead", "daysBehind"):
        rec = grp[(grp["section"] == "wellbore") & (grp["field"] == field) & (~grp["missing"])]
        if rec.empty or d is None:
            continue
        xml_v = str(rec.iloc[0]["value"])
        if d.group("v").lower() != xml_v.lower().replace(" ", ""):
            out.append(_note(first, field, xml_v, d.group("v"), pdf.page_at(d.start()), "Summary report"))
    return out


def _pdf_lines(path: Path) -> list[tuple[int, str]]:
    with pymupdf.open(path) as doc:
        return [(i, ln.strip()) for i, pg in enumerate(doc, 1) for ln in pg.get_text().splitlines() if ln.strip()]


def _is_num(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def _bit_notes(grp: pd.DataFrame, pdf_path: Path) -> list[dict]:
    """Compare hours / start / end of each bit run with the first numbers printed after the manufacturer cell.
    The Bit Record table drops empty cells, so only these first three (in header order) are compared."""
    bits = grp[grp["section"] == "bit"]
    if bits.empty:
        return []
    lines, out, first = _pdf_lines(pdf_path), [], grp.iloc[0]
    for _, b in bits.iterrows():
        attrs = json.loads(b["attrs"]) if isinstance(b["attrs"], str) else {}
        expected = [(k, raw_of(attrs[k])) for k in ("bitRun/eTimOpBit", "bitRun/mdHoleStart", "bitRun/mdHoleStop")
                    if k in attrs and attrs[k].get("value") is not None]
        iadc = attrs.get("codeIADC", {}).get("value")
        if not expected or iadc is None:
            continue
        idx = next((i for i, (_, t) in enumerate(lines) if t == str(iadc)), None)   # the IADC code cell of this row
        if idx is None:
            continue
        j = idx + 1
        while j < len(lines) and not _is_num(lines[j][1]):                           # manufacturer cell(s), possibly wrapped
            j += 1
        nums = []
        while j < len(lines) and _is_num(lines[j][1]):
            nums.append((lines[j][0], lines[j][1]))
            j += 1
        if len(nums) < len(expected):
            continue
        for (key, xml_v), (page, pdf_v) in zip(expected, nums):
            if float(xml_v) != float(pdf_v):
                out.append(_note(first, key, xml_v, pdf_v, page, "Bit Record"))
    return out


def discrepancy_notes(records: pd.DataFrame, pdf_dir: Path) -> pd.DataFrame:
    """NOTE records for every XML-vs-PDF disagreement found. Empty frame (same columns) when there are none."""
    rows: list[dict] = []
    for _, grp in records[records["section"] != "note"].groupby("source_file", sort=False):
        first = grp.iloc[0]
        pdf_path = Path(pdf_dir) / first["pdf_file"]
        rows += _flag_and_days_notes(grp, PdfText(pdf_path)) + _bit_notes(grp, pdf_path)
    return pd.DataFrame(rows, columns=RECORD_COLUMNS)


def note_line(row: pd.Series) -> str:
    """The context line for a NOTE record."""
    a = json.loads(row["attrs"])
    return (f"[{row['record_id']}] note | {row['field']}: the XML value is {a['xml']['value']} (authoritative); "
            f"the PDF prints {a['pdf']['value']} | report {row['report_date']} | at -")
