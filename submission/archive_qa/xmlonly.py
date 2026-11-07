"""XML-only fields: values the XML carries that the PDF/HTML never print.

Evidence for such a field must not cite a PDF page (the page does not show the value). Two sources:

* field-style records (header / status / wellbore) that the locator found NO PDF label for (pdf_match == "not_printed"),
  or whose value it could not find next to its label (unlocated: NPD numbers, rig codes, a blank days-behind), or whose
  PDF value conflicts with the XML (pdf_match == "excluded": tightWell / HPHT, where the PDF prints "Y");
* attributes of rows that are printed but lack these columns, listed in XML_ONLY_ATTRS below. This list comes from
  comparing the XML with the PDF (see DATA_NOTES.md and tests/test_xmlonly.py, which re-checks it against the PDFs).

A record counts as "using" an XML-only attribute only when the question or the answer talks about it, so a row that is
cited for its printed remark still cites its PDF page.
"""

from __future__ import annotations

import json
import re

import pandas as pd

# (section, attrs-key regex, concept regex over question + answer, values that do not count as informative)
XML_ONLY_ATTRS: list[tuple[str, str, str, set[str]]] = [
    ("activity", r"stateDetailActivity", r"equipment failure|operation failed|mud loss|failed operation|\bfail(?:ure|ed|ures)\b", {"success"}),
    ("activity", r"phase", r"\bphase\b", set()),
    ("fluid", r"mudClass", r"mud class|water[- ]based|oil[- ]based", set()),
    ("fluid", r"presBopRating", r"bop (?:pressure )?rating|pressure rating", set()),
    ("gas", r"nbut", r"n-?butane|normal butane|\bnc4\b|\bnbut\b", set()),
    ("bit", r"condFinal\w+|nozzle/\w+(?:#\d+)?|comment", r"dull|grading|nozzle|bit condition|bit comment", set()),
    ("survey", r"dTim", r"time ?stamp|date and time|what time|when was the (?:survey|station)", set()),
    ("lithology", r"dTim", r"time ?stamp|date and time|what time", set()),
    ("strat", r"dTim", r"time ?stamp|date and time|what time", set()),
]


def xml_only_paths(row: pd.Series, question: str, answer: str) -> list[tuple[str, str]]:
    """[(field path, kind)] for the XML-only fields this cited record is used for. kind: "unprinted" | "conflict"."""
    match = row.get("pdf_match")
    if match == "not_printed":
        return [(str(row["field"]), "unprinted")]
    if row["section"] in ("status", "wellbore", "header") and pd.isna(match):
        # the PDF has a label for it but the locator found no such value there (NPD numbers, rig codes, a blank
        # days-behind): the value is not printed
        return [(str(row["field"]), "unprinted")]
    if match == "excluded":
        return [(str(row["field"]), "conflict")]
    attrs = json.loads(row["attrs"]) if isinstance(row.get("attrs"), str) else {}
    talk = f"{question} {answer}"
    out: list[tuple[str, str]] = []
    for section, key_rx, concept_rx, skip in XML_ONLY_ATTRS:
        if row["section"] != section or not re.search(concept_rx, talk, re.IGNORECASE):
            continue
        for key, entry in attrs.items():
            v = entry.get("value")
            if re.fullmatch(key_rx, key) and v is not None and str(v) not in skip:
                out.append((f"{section}/{key}", "unprinted"))
    return out


def xml_only_evidence(row: pd.Series, paths: list[tuple[str, str]]) -> list[str]:
    cite = f"{row['source_file']} {row['record_id']}"
    out = []
    for path, kind in paths:
        if kind == "conflict":
            out.append(f"XML only: {path}; the PDF prints a conflicting value ({cite})")
        else:
            out.append(f"XML only: {path}; not printed in the PDF ({cite})")
    return out
