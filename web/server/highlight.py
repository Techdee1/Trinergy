"""BUILD-TIME ONLY (needs the organiser PDFs): compute the highlight rectangles of every record. The server never imports
this at run time; `build_data.py` runs it once and stores the result in data/boxes.json. Serving lives in pages.py.

Highlight method: the locator (submission/archive_qa/locate.py) found each record by searching the PDF text with
whitespace removed. We do the same on the record's own page, but keep the character boxes, so a match maps back to
rectangles. Needles use the locator's own helpers and the same strength order (full row first, then shorter fallbacks).
`match` in the result says what was highlighted: row | label | value | heading | none.
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path

import pandas as pd
import pymupdf

from submission.archive_qa import locate as L


class PageError(Exception):
    def __init__(self, status: int, code: str, message: str, **extra):
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra


_PYMU = threading.Lock()      # PyMuPDF documents are not thread-safe


class _PageText:
    """One page as whitespace-free lowercase text with a bounding box per character."""

    def __init__(self, page: "pymupdf.Page"):
        chars: list[str] = []
        self.boxes: list[tuple] = []
        self.line: list[int] = []
        ln = 0
        for b in page.get_text("rawdict")["blocks"]:
            if b.get("type") != 0:
                continue
            for line in b["lines"]:
                ln += 1
                for sp in line["spans"]:
                    for ch in sp["chars"]:
                        if ch["c"].isspace():
                            continue
                        for c in ch["c"].lower():
                            chars.append(c)
                            self.boxes.append(tuple(ch["bbox"]))
                            self.line.append(ln)
        self.text = "".join(chars)

    def find(self, needle: str, rx: bool = False) -> tuple[int, int] | None:
        if not needle:
            return None
        if rx:
            m = re.search(needle, self.text)
            return (m.start(), m.end()) if m else None
        i = self.text.find(needle)
        return (i, i + len(needle)) if i != -1 else None

    def rects(self, start: int, end: int) -> list[tuple[float, float, float, float]]:
        out: list[list[float]] = []
        cur = None
        for i in range(start, end):
            x0, y0, x1, y1 = self.boxes[i]
            if cur is not None and self.line[i] == cur[0]:
                r = out[-1]
                r[0], r[1], r[2], r[3] = min(r[0], x0), min(r[1], y0), max(r[2], x1), max(r[3], y1)
            else:
                out.append([x0, y0, x1, y1])
            cur = (self.line[i],)
        merged: list[list[float]] = []       # table cells of one row are separate text lines: join boxes on the same baseline
        for r in out:
            m = merged[-1] if merged else None
            if m is not None:
                overlap = min(m[3], r[3]) - max(m[1], r[1])
                if overlap >= 0.6 * min(m[3] - m[1], r[3] - r[1]):
                    m[0], m[1], m[2], m[3] = min(m[0], r[0]), min(m[1], r[1]), max(m[2], r[2]), max(m[3], r[3])
                    continue
            merged.append(list(r))
        return [tuple(r) for r in merged]


def _n(s) -> str:
    return L.norm(str(s)) if s is not None else ""


def _label_rx(label: str) -> str:
    parts = re.split(r"(\([^)]*\))", L.norm(label))
    return "".join(r"\([^)]*\)" if p.startswith("(") else re.escape(p) for p in parts if p)


def _columnar(pt: _PageText, label: str, raws: list[str], i: int) -> tuple[int, int] | None:
    lab = L.norm(label)
    for n in range(len(raws), i, -1):
        chain = lab + "".join(L.norm(r) for r in raws[:n])
        pos = pt.text.find(chain)
        if pos != -1:
            s = pos + len(lab) + sum(len(L.norm(r)) for r in raws[:i])
            return s, s + len(L.norm(raws[i]))
    return None


def _first(pt: _PageText, needles: list[str]) -> tuple[int, int] | None:
    for nd in needles:
        hit = pt.find(nd)
        if hit:
            return hit
    return None


def find_evidence(pt: _PageText, row: pd.Series, report: pd.DataFrame) -> tuple[tuple[int, int] | None, str]:
    """(character range, kind) of the record's own text on the page, using the locator's needle recipes."""
    sec, fld = row["section"], row["field"]
    val = row["value"] if isinstance(row["value"], str) else None
    a = json.loads(row["attrs"]) if isinstance(row["attrs"], str) else {}
    raw = L.raw_of
    if sec in ("status", "wellbore", "header"):
        label = {"status": L.STATUS_LABELS, "wellbore": L.WELLBORE_LABELS, "header": L.HEADER_LABELS}[sec].get(fld)
        if not label:
            return None, "none"
        rends = L._value_renderings(fld, val)
        if val is None or fld == "dTim":
            rends.append("")
        for i, v in enumerate(rends):
            hit = pt.find(_label_rx(label) + re.escape(L.norm(v)), rx=True)
            if hit:
                return hit, ("row" if v else "label")
        return None, "none"
    if sec in ("summary_24h", "forecast_24h"):
        c = L.norm(val or "")
        hit = _first(pt, [c, c[:80], c[:40]])
        return (hit, "value") if hit else (None, "none")
    if sec == "activity":
        base = L._chain(L.hhmm(a.get("dTimStart", {}).get("value")), L.hhmm(a.get("dTimEnd", {}).get("value")),
                        raw(a.get("md")), raw(a.get("proprietaryCode")), raw(a.get("state")))
        c = L.norm(val or "")
        hit = _first(pt, [base + c, base + c[:60], base + c[:30], base, c[:40]])
        return (hit, "row") if hit else (None, "none")
    if sec in ("fluid", "casing"):
        idx = [i for i, s in enumerate(report["section"]) if s == sec]
        rids = list(report["record_id"])
        k = idx.index(rids.index(row["record_id"]))
        if sec == "fluid":
            times = [L.hhmm(report.iloc[i]["timestamp"]) for i in idx]
            order = sorted(range(len(times)), key=lambda j: times[j])
            hit = _columnar(pt, "Sample Time", [times[j] for j in order], order.index(k))
        else:
            attrs = [json.loads(report.iloc[i]["attrs"]) if isinstance(report.iloc[i]["attrs"], str) else {} for i in idx]
            hit = _columnar(pt, "Length (m)", [raw(x.get("length")) for x in attrs], k) or \
                _columnar(pt, "Top mMD", [raw(x.get("mdTop")) for x in attrs], k)
        return (hit, "value") if hit else (None, "none")
    needles: list[str] = []
    if sec == "survey":
        needles = [L._chain(raw(a.get("md")), raw(a.get("tvd")), val or "", raw(a.get("azi"))), L._chain(raw(a.get("md")), raw(a.get("tvd")))]
    elif sec == "pore_pressure":
        t, md = L.hhmm(row["timestamp"]), raw(a.get("md"))
        tvd = raw(a["tvd"]) if "tvd" in a else ""
        needles = [L._chain(t, md, tvd, val or "", raw(a.get("readingKind"))), L._chain(md, tvd, val or "")]
    elif sec == "gas":
        r = [L.hhmm(row["timestamp"]), raw(a.get("readingType")), raw(a.get("mdTop")), raw(a.get("tvdTop")), val or L.SENTINEL,
             raw(a.get("meth")), raw(a.get("eth")), raw(a.get("prop")), raw(a.get("ibut")), raw(a.get("ipent"))]
        needles = [L._chain(*r), L._chain(*r[:4])]
    elif sec == "lithology":
        r = [raw(a.get("mdTop")), raw(a.get("mdBottom"))]
        needles = [L._chain(*r) + L.norm(val or "")[:20], L._chain(*r)]
    elif sec == "strat":
        r = [raw(a.get("mdTop")), raw(a.get("tvdTop"))]
        needles = [L._chain(*r) + L.norm(val or "")[:20], L._chain(*r)]
    elif sec == "log":
        r = [raw(a.get("runNumber")), raw(a.get("serviceCompany")), raw(a.get("mdTop")), raw(a.get("mdBottom"))]
        needles = [L._chain(*r) + L.norm(val or "")[:12], L._chain(*r[:2])]
    elif sec == "equip_failure":
        r = [L.hhmm(row["timestamp"]), raw(a.get("md")), raw(a.get("equipClass")), raw(a.get("eTimMissProduction")),
             L.hhmm(a.get("dTimRepair", {}).get("value"))]
        needles = [L._chain(*r) + L.norm(val or "")[:20], L._chain(*r[:3]), L.norm(val or "")[:30]]
    elif sec == "bit":
        r = [raw(a.get("numBit")), val or "", "in", raw(a.get("codeMfg")), raw(a.get("codeIADC"))]
        needles = [L._chain(*r), L._chain(raw(a.get("numBit")), val or "")]
    elif val:
        needles = [L.norm(val)[:60], L.norm(val)[:30]]
    hit = _first(pt, [x for x in needles if x])
    return (hit, "row") if hit else (None, "none")


class HighlightBuilder:
    def __init__(self, records: pd.DataFrame, pdf_dir: Path):
        self.records = records.set_index("record_id", drop=False)
        self.all = records
        self.pdf_dir = Path(pdf_dir)
        self._boxes: dict[str, dict] = {}
        self._texts: dict[tuple, tuple] = {}
        self._lock = threading.Lock()

    # -- which page
    def locate(self, rid: str) -> dict:
        if rid not in self.records.index:
            raise PageError(404, "unknown_record", f"No record with id {rid!r} in the evidence store.", record_id=rid)
        r = self.records.loc[rid]
        match = r.get("pdf_match")
        if match in ("not_printed", "excluded") or pd.isna(r.get("pdf_page")) or not isinstance(r.get("pdf_file"), str):
            why = {"not_printed": "the PDF has no label for this XML field",
                   "excluded": "the PDF prints a value that conflicts with the XML (the XML is authoritative)"}.get(
                match, "no PDF page was located for this record")
            raise PageError(404, "xml_only", f"XML-only evidence: {why}, so there is no PDF page to show.",
                            record_id=rid, xml_file=r["source_file"], pdf_match=None if pd.isna(match) else match)
        return {"record_id": rid, "pdf_file": r["pdf_file"], "page": int(r["pdf_page"]),
                "section": r["pdf_section"] if isinstance(r["pdf_section"], str) else None,
                "locator_match": None if pd.isna(match) else match, "xml_file": r["source_file"]}

    def _open(self, info: dict):
        path = self.pdf_dir / info["pdf_file"]
        if not path.is_file():
            raise PageError(404, "pdf_unavailable", f"The PDF {info['pdf_file']} is not available on this server.", record_id=info["record_id"])
        return pymupdf.open(path)

    def _page_text(self, info: dict):
        key = (info["pdf_file"], info["page"])
        with self._lock:
            if key in self._texts:
                return self._texts[key]
        with _PYMU:
            doc = self._open(info)
            try:
                page = doc[info["page"] - 1]
                val = (_PageText(page), float(page.rect.width), float(page.rect.height))
            finally:
                doc.close()
        with self._lock:
            if len(self._texts) > 64:
                self._texts.pop(next(iter(self._texts)))
            self._texts[key] = val
        return val

    # -- boxes
    def boxes(self, rid: str) -> dict:
        with self._lock:
            if rid in self._boxes:
                return self._boxes[rid]
        info = self.locate(rid)
        row = self.records.loc[rid]
        report = self.all[self.all["source_file"] == row["source_file"]].reset_index(drop=True)
        pt, w, h = self._page_text(info)
        if info["locator_match"] == "section":
            hit, kind = None, "none"
        else:
            hit, kind = find_evidence(pt, row, report)
        if hit is None and info["section"]:
            hit = pt.find(L.norm(info["section"]))
            kind = "heading" if hit else "none"
        rects = pt.rects(*hit) if hit else []
        out = {**info, "page_width": w, "page_height": h, "match": kind,
               "boxes": [{"x0": round(x0, 2), "y0": round(y0, 2), "x1": round(x1, 2), "y1": round(y1, 2),
                          "nx0": round(x0 / w, 5), "ny0": round(y0 / h, 5), "nx1": round(x1 / w, 5), "ny1": round(y1 / h, 5)}
                         for x0, y0, x1, y1 in rects],
               "note": ("coordinates are PDF points from the top-left of the page; nx/ny are the same boxes as fractions of the page size"
                        + ("; only the section heading could be highlighted" if kind == "heading" else
                           "; the evidence text could not be found on the page, so nothing is highlighted" if kind == "none" else ""))}
        with self._lock:
            self._boxes[rid] = out
        return out
