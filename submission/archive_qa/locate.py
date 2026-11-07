"""Find the PDF page and section heading for each evidence record.

Method: render each PDF to text with PyMuPDF, delete ALL whitespace and lowercase it
(this removes the "Summar y" / "integrity tes\\nt" splitting), then search for a
distinctive "needle" built from the record's own raw XML values, e.g. for an activity
row: start time + end time + depth + activity code + state + start of the remark.

Needles come in a few strengths. `pdf_match` records which one hit:
  exact    full needle found
  partial  a shorter fallback needle found (still a specific hit)
  section  only the section heading was found (page of the table, not the row)
  excluded deliberately not located (tightWell/HPHT: the PDF prints Y but the XML says 0;
           XML is authoritative, so the PDF flag is never used as evidence)
  not_printed  the PDF has no label for this XML field at all (e.g. mdPlanned,
           wellheadElevation); evidence for it can only cite the XML
  None     nothing found
pdf_section is the nearest heading at or before the match in document order, so a table
that continues on page 2 still gets its heading.
"""

from __future__ import annotations

import bisect
import json
import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

import pandas as pd
import pymupdf

SENTINEL = "-999.99"

# Section headings as printed in these DDR PDFs (observed across all 32 files).
HEADINGS = [
    "Summary report",
    "Summary of activities (24 Hours)",
    "Summary of planned activities (24 Hours)",
    "Operations",
    "Drilling Fluid",
    "Pore Pressure",
    "Survey Station",
    "Stratigraphic Information",
    "Casing Liner Tubing",
    "Equipment Failure Information",
    "Log Information",
    "Gas Reading Information",
    "Lithology Information",
    "Bit Record",
]

SECTION_HEADING = {
    "status": "Summary report", "wellbore": "Summary report", "header": "Summary report",
    "summary_24h": "Summary of activities (24 Hours)",
    "forecast_24h": "Summary of planned activities (24 Hours)",
    "activity": "Operations", "fluid": "Drilling Fluid", "survey": "Survey Station",
    "casing": "Casing Liner Tubing", "bit": "Bit Record", "pore_pressure": "Pore Pressure",
    "gas": "Gas Reading Information", "lithology": "Lithology Information",
    "strat": "Stratigraphic Information", "log": "Log Information",
    "equip_failure": "Equipment Failure Information",
}

# XML field -> label printed in the PDF "Summary report" block.
STATUS_LABELS = {
    "reportNo": "Report number:", "md": "Depth mMd:", "tvd": "Depth mTVD:",
    "diaHole": "Hole Dia ():", "mdKickoff": "Depth at Kick Off mMD:",
    "tvdKickoff": "Depth at Kick Off mTVD:", "strengthForm": "Formation strength (g/cm3):",
    "mdStrengthForm": "Depth at formation strength mMD:",
    "tvdStrengthForm": "Depth At Formation Strength mTVD:",
    "mdCsgLast": "Depth At Last Casing mMD:", "tvdCsgLast": "Depth At Last Casing mTVD:",
    "presTestType": "Pressure Test Type:", "mdPlugTop": "Plug Back Depth mMD:",
    "distDrill": "Dist Drilled (m):", "ropCurrent": "Penetration rate (m/h):",
    "elevKelly": "Elevation RKB-MSL (m):", "waterDepth": "Water depth MSL (m):",
    "dTim": "Period:",
}
WELLBORE_LABELS = {
    "dTimSpud": "Spud Date:", "dateDrillComplete": "Date Well Complete:",
    "daysAhead": "Days Ahead/Behind (+/-):", "daysBehind": "Days Ahead/Behind (+/-):",
    "operator": "Operator:", "drillContractor": "Drilling contractor:",
    "rigAlias/name": "Rig Name:",
}
HEADER_LABELS = {
    "nameWell": "Wellbore:", "nameWellbore": "Wellbore:", "wellAlias": "Wellbore:",
    "wellboreAlias": "Wellbore:", "versionKind": "Status:",
    "createDate": "Report creation time:",
}
EXCLUDED_FIELDS = {"tightWell", "hpht"}


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s).lower()


# ------------------------------------------------------------------ PDF text


class PdfText:
    """One PDF as whitespace-free text with page offsets and heading offsets."""

    def __init__(self, path: Path):
        self.path = Path(path)
        parts: list[str] = []
        self.page_starts: list[int] = []
        self.headings: list[tuple[int, str]] = []  # (offset, canonical heading)
        heading_norm = {norm(h): h for h in HEADINGS}
        offset = 0
        with pymupdf.open(self.path) as doc:
            for page in doc:
                self.page_starts.append(offset)
                for line in page.get_text().splitlines():
                    n = norm(line)
                    if not n:
                        continue
                    if n in heading_norm:
                        self.headings.append((offset, heading_norm[n]))
                    parts.append(n)
                    offset += len(n)
        self.text = "".join(parts)
        self._heading_offsets = [o for o, _ in self.headings]
        self.used: set[int] = set()

    def page_at(self, offset: int) -> int:
        return bisect.bisect_right(self.page_starts, offset)  # 1-based

    def heading_at(self, offset: int) -> str | None:
        i = bisect.bisect_right(self._heading_offsets, offset) - 1
        return self.headings[i][1] if i >= 0 else None

    def find(self, needle: str, after: int = 0) -> int | None:
        """First occurrence not already claimed by another record (repeated rows)."""
        if not needle:
            return None
        pos = self.text.find(needle, after)
        while pos != -1:
            if pos not in self.used:
                self.used.add(pos)
                return pos
            pos = self.text.find(needle, pos + 1)
        return None

    def find_label(self, label: str, value: str) -> int | None:
        """Label + value, where the "(unit)" part of the label may vary. Not claimed:
        several XML fields can legitimately share one printed line."""
        parts = re.split(r"(\([^)]*\))", norm(label))
        rx = "".join(r"\([^)]*\)" if p.startswith("(") else re.escape(p) for p in parts if p)
        m = re.search(rx + re.escape(norm(value)), self.text)
        return m.start() if m else None

    def find_heading(self, heading: str) -> int | None:
        for off, h in self.headings:
            if h == heading:
                return off
        return None


# ------------------------------------------------------------------ needles


def raw_of(entry: dict | None) -> str:
    """The XML text of an attrs entry (inverse of how parse.py stored it)."""
    if entry is None:
        return ""
    if "raw" in entry:
        return entry["raw"]
    v = entry.get("value")
    if v is None:
        return SENTINEL  # the PDF prints missing numerics as -999.99
    return v if isinstance(v, str) else json.dumps(v)


def hhmm(ts) -> str:
    return ts[11:16] if isinstance(ts, str) and len(ts) >= 16 else ""


def _value_renderings(field: str, value: str | None) -> list[str]:
    """Ways the PDF may print a header/status value."""
    if value is None:
        return [SENTINEL, ""]
    out = [value]
    if re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d", value):
        out.insert(0, value[:10] + " " + value[11:16])  # 2014-03-26 00:00
        if field == "dTim":
            out.insert(0, "")  # "Period: a - b": matched on label only
    if field == "daysBehind":
        out.insert(0, "-" + value)
    if field in ("nameWell", "nameWellbore"):
        out = [re.sub(r"^NO\s+", "", value)]
    return out


def _chain(*parts: str) -> str:
    return "".join(norm(p) for p in parts)


def _first_hit(pdf: PdfText, needles: list[tuple[str, str]]) -> tuple[int, str] | None:
    """needles: [(needle, kind)] strongest first. Returns (offset, 'exact'|'partial')."""
    for i, (needle, _) in enumerate(needles):
        pos = pdf.find(needle)
        if pos is not None:
            return pos, "exact" if i == 0 else "partial"
    return None


def _columnar(pdf: PdfText, label: str, raws: list[str], i: int) -> int | None:
    """Tables printed as one column of values per record (fluid samples, casing joints).
    Find 'Label v0 v1 ... vn'; offset of the i-th value. Falls back to shorter prefixes."""
    lab = norm(label)
    for n in range(len(raws), i, -1):
        chain = lab + "".join(norm(r) for r in raws[:n])
        pos = pdf.text.find(chain)
        if pos != -1:
            return pos + len(lab) + sum(len(norm(r)) for r in raws[:i])
    return None


def locate_report(records: pd.DataFrame, pdf: PdfText) -> pd.DataFrame:
    """Fill pdf_page / pdf_section / pdf_match for one report's records."""
    rec = records.copy()
    attrs_list = [json.loads(a) if isinstance(a, str) else {} for a in rec["attrs"]]

    # per-report column lists for columnar tables
    fluid_idx = [i for i, s in enumerate(rec["section"]) if s == "fluid"]
    casing_idx = [i for i, s in enumerate(rec["section"]) if s == "casing"]
    fluid_times = [hhmm(rec.iloc[i]["timestamp"]) for i in fluid_idx]
    casing_len = [raw_of(attrs_list[i].get("length")) for i in casing_idx]
    casing_top = [raw_of(attrs_list[i].get("mdTop")) for i in casing_idx]

    pages, sections, matches = [], [], []
    for pos_i, (_, r) in enumerate(rec.iterrows()):
        a = attrs_list[pos_i]
        sec, fld, val = r["section"], r["field"], r["value"]
        val = val if isinstance(val, str) else None  # pandas turns None into NaN
        offset, kind = None, None

        if fld in EXCLUDED_FIELDS:
            pages.append(None); sections.append(None); matches.append("excluded")
            continue

        if sec in ("status", "wellbore", "header"):
            labels = {"status": STATUS_LABELS, "wellbore": WELLBORE_LABELS, "header": HEADER_LABELS}[sec]
            label = labels.get(fld)
            if not label:
                pages.append(None); sections.append(None); matches.append("not_printed")
                continue
            if label:
                renderings = _value_renderings(fld, val)
                if val is None or fld == "dTim":  # label alone is enough only when no value is printed
                    renderings.append("")
                for i, v in enumerate(renderings):
                    offset = pdf.find_label(label, v)
                    if offset is not None:
                        kind = "exact" if i == 0 else "partial"
                        break
        elif sec in ("summary_24h", "forecast_24h"):
            heading = SECTION_HEADING[sec]
            h_off = pdf.find_heading(heading)
            if val and h_off is not None:
                pos = pdf.text.find(norm(val)[:60], h_off)
                if pos != -1:
                    offset, kind = pos, "exact"
        elif sec == "activity":
            md = raw_of(a.get("md"))
            base = _chain(hhmm(a.get("dTimStart", {}).get("value")), hhmm(a.get("dTimEnd", {}).get("value")),
                          md, raw_of(a.get("proprietaryCode")), raw_of(a.get("state")))
            c = norm(val or "")
            hit = _first_hit(pdf, [(base + c[:30], "x"), (base, "x"), (c[:40], "x")])
            if hit:
                offset, kind = hit
        elif sec == "fluid":
            k = fluid_idx.index(pos_i)
            order = sorted(range(len(fluid_times)), key=lambda j: fluid_times[j])  # PDF sorts by HH:MM
            offset = _columnar(pdf, "Sample Time", [fluid_times[j] for j in order], order.index(k))
            kind = "exact" if offset is not None else None
        elif sec == "casing":
            k = casing_idx.index(pos_i)
            offset = _columnar(pdf, "Length (m)", casing_len, k)
            if offset is None:
                offset = _columnar(pdf, "Top mMD", casing_top, k)
            kind = "exact" if offset is not None else None
        elif sec == "survey":
            full = _chain(raw_of(a.get("md")), raw_of(a.get("tvd")), val or "", raw_of(a.get("azi")))
            hit = _first_hit(pdf, [(full, "x"), (_chain(raw_of(a.get("md")), raw_of(a.get("tvd"))), "x")])
            if hit:
                offset, kind = hit
        elif sec == "pore_pressure":
            t, md = hhmm(r["timestamp"]), raw_of(a.get("md"))
            tvd = raw_of(a["tvd"]) if "tvd" in a else ""
            rk = raw_of(a.get("readingKind"))
            hit = _first_hit(pdf, [(_chain(t, md, tvd, val or "", rk), "x"), (_chain(md, tvd, val or ""), "x")])
            if hit:
                offset, kind = hit
        elif sec == "gas":
            t = hhmm(r["timestamp"])
            row = [t, raw_of(a.get("readingType")), raw_of(a.get("mdTop")), raw_of(a.get("tvdTop")),
                   val or SENTINEL, raw_of(a.get("meth")), raw_of(a.get("eth")), raw_of(a.get("prop")),
                   raw_of(a.get("ibut")), raw_of(a.get("ipent"))]
            hit = _first_hit(pdf, [(_chain(*row), "x"), (_chain(*row[:4]), "x")])
            if hit:
                offset, kind = hit
        elif sec == "lithology":
            row = [raw_of(a.get("mdTop")), raw_of(a.get("mdBottom"))]
            hit = _first_hit(pdf, [(_chain(*row) + norm(val or "")[:20], "x"), (_chain(*row), "x")])
            if hit:
                offset, kind = hit
        elif sec == "strat":
            row = [raw_of(a.get("mdTop")), raw_of(a.get("tvdTop"))]
            hit = _first_hit(pdf, [(_chain(*row) + norm(val or "")[:20], "x"), (_chain(*row), "x")])
            if hit:
                offset, kind = hit
        elif sec == "log":
            row = [raw_of(a.get("runNumber")), raw_of(a.get("serviceCompany")),
                   raw_of(a.get("mdTop")), raw_of(a.get("mdBottom"))]
            hit = _first_hit(pdf, [(_chain(*row) + norm(val or "")[:12], "x"), (_chain(*row[:2]), "x")])
            if hit:
                offset, kind = hit
        elif sec == "equip_failure":
            t, rep = hhmm(r["timestamp"]), hhmm(a.get("dTimRepair", {}).get("value"))
            row = [t, raw_of(a.get("md")), raw_of(a.get("equipClass")), raw_of(a.get("eTimMissProduction")), rep]
            hit = _first_hit(pdf, [(_chain(*row) + norm(val or "")[:20], "x"), (_chain(*row[:3]), "x"),
                                   (norm(val or "")[:30], "x")])
            if hit:
                offset, kind = hit
        elif sec == "bit":
            row = [raw_of(a.get("numBit")), val or "", "in", raw_of(a.get("codeMfg")), raw_of(a.get("codeIADC"))]
            hit = _first_hit(pdf, [(_chain(*row), "x"), (_chain(raw_of(a.get("numBit")), val or ""), "x")])
            if hit:
                offset, kind = hit

        if offset is None:
            # last resort: the table's heading, so the section is still citable
            h_off = pdf.find_heading(SECTION_HEADING.get(sec, ""))
            if h_off is not None and sec not in ("status", "wellbore", "header"):
                offset, kind = h_off, "section"

        if offset is None:
            pages.append(None); sections.append(None); matches.append(None)
        else:
            pages.append(pdf.page_at(offset)); sections.append(pdf.heading_at(offset)); matches.append(kind)

    rec["pdf_page"] = pd.array(pages, dtype="Int64")
    rec["pdf_section"] = sections
    rec["pdf_match"] = matches
    return rec


@lru_cache(maxsize=None)
def _load_pdf(path: str) -> PdfText:
    return PdfText(Path(path))


def locate_all(records: pd.DataFrame, pdf_dir: Path) -> pd.DataFrame:
    """Locate every record. Records stay in their original order."""
    out = []
    for source_file, grp in records.groupby("source_file", sort=False):
        pdf = PdfText(Path(pdf_dir) / grp["pdf_file"].iloc[0])  # fresh `used` set per report
        out.append(locate_report(grp, pdf))
    return pd.concat(out).loc[records.index]


def locate_stats(records: pd.DataFrame, show_unlocated: bool = True) -> dict:
    """Print/return the located share and the unlocated records grouped by section."""
    m = records["pdf_match"].fillna("none")
    total = len(records)
    located = int(m.isin(["exact", "partial"]).sum())
    n_excl, n_np = int((m == "excluded").sum()), int((m == "not_printed").sum())
    printable = total - n_excl - n_np
    header_like = records["section"].isin(["status", "wellbore", "header"])
    rows = ~header_like
    stats = {
        "records": total, "exact": int((m == "exact").sum()), "partial": int((m == "partial").sum()),
        "section_only": int((m == "section").sum()), "excluded": n_excl, "not_printed": n_np,
        "unlocated": int((m == "none").sum()),
        "share_all": located / total if total else 0.0,
        "share_printable": located / printable if printable else 0.0,
        "share_table_rows": float(m[rows].isin(["exact", "partial"]).mean()) if rows.any() else 0.0,
    }
    print(f"Records: {total}. Located to the row/field: {located} "
          f"(exact {stats['exact']}, partial {stats['partial']}); section heading only: {stats['section_only']}; "
          f"unlocated: {stats['unlocated']}")
    print(f"  not printed in the PDF at all (no label): {n_np}; excluded by design (tightWell/HPHT): {n_excl}")
    print(f"  located share: all records {stats['share_all']:.1%} | "
          f"records the PDF prints {stats['share_printable']:.1%} | "
          f"table-row and narrative sections {stats['share_table_rows']:.1%}")
    if show_unlocated:
        bad = records[~m.isin(["exact", "partial", "excluded", "not_printed"])]
        if len(bad):
            print("\nPrinted-or-narrative records not located to the row/field, by section (field: count):")
            for sec, g in bad.groupby("section"):
                print(f"  {sec:14s} {len(g):4d}  " + ", ".join(f"{k}: {v}" for k, v in g["field"].value_counts().items()))
        np_ = records[m == "not_printed"]
        if len(np_):
            print("\nNot printed in the PDF (XML only), by field: "
                  + ", ".join(f"{k}: {v}" for k, v in np_["field"].value_counts().items()))
    return stats
