"""Build, save and load the evidence store, plus `has_field`."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from . import config
from .locate import locate_all, locate_stats
from .parse import RECORD_COLUMNS, ParseStats, parse_all, print_counts


def build_store(
    xml_dir: Path | None = None,
    pdf_dir: Path | None = None,
    out_path: Path | None = None,
    verbose: bool = True,
) -> pd.DataFrame:
    """Parse every XML report, locate each record in its PDF, save records.parquet."""
    xml_dir, pdf_dir = Path(xml_dir or config.XML_DIR), Path(pdf_dir or config.PDF_DIR)
    out_path = Path(out_path or config.RECORDS_PATH)
    df, stats = parse_all(xml_dir)
    if verbose:
        print_counts(df, stats)
    df = locate_all(df, pdf_dir)
    if verbose:
        print()
        locate_stats(df)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df[RECORD_COLUMNS].to_parquet(out_path, index=False)
    if verbose:
        print(f"\nSaved {len(df)} records -> {out_path}")
    return df


def load_store(path: Path | None = None) -> pd.DataFrame:
    return pd.read_parquet(path or config.RECORDS_PATH)


def get_store(rebuild: bool = False, verbose: bool = False) -> pd.DataFrame:
    """Load records.parquet if present, else build it."""
    if not rebuild and config.RECORDS_PATH.exists():
        return load_store()
    return build_store(verbose=verbose)


# ------------------------------------------------------------------ has_field

# kind -> (sections that hold it, regex over the record's field name / attrs keys).
# Kinds whose sections are () are looked for by field name only: these are things the
# WITSML drillReport profile used here has no element for (cost, personnel, ...).
KINDS: dict[str, tuple[tuple[str, ...], str | None]] = {
    "activity": (("activity",), None),
    "fluid": (("fluid",), None),
    "survey": (("survey",), None),
    "casing": (("casing",), None),
    "bit": (("bit",), None),
    "pore_pressure": (("pore_pressure",), None),
    "gas": (("gas",), None),
    "lithology": (("lithology",), None),
    "strat": (("strat",), None),
    "log": (("log",), None),
    "equip_failure": (("equip_failure",), None),
    "summary": (("summary_24h",), None),
    "forecast": (("forecast_24h",), None),
    "kickoff": ((), r"^mdKickoff$|^tvdKickoff$"),
    "rig": (("wellbore",), r"^rigAlias"),
    "operator": (("wellbore",), r"^operator$"),
    # not present in this archive's schema; has_field proves it rather than assuming it
    "cost": ((), r"cost|afe|spread|price|expens"),
    "personnel": ((), r"\bpob\b|personnel|crew|headcount|persons"),
    "supervisor": ((), r"supervisor|superintendent|toolpusher|\boim\b"),
    "weather": ((), r"weather|\bwind|wave|sea.?state|swell|visibility|baro"),
}


def has_field(
    records: pd.DataFrame,
    kind: str,
    well: str | None = None,
    report_date: str | None = None,
    require_value: bool = False,
) -> bool:
    """Does the report (or any report, if well/report_date are None) contain a record of `kind`?

    Structured fields only: it looks at sections and field names, not free text, so a
    remark that mentions "wind" does not count as a weather record. Use `text_mentions`
    for narrative. `require_value=True` ignores records whose value is missing (-999.99).
    A False answer is a field-level absence; a True answer with no matching retrieval
    is a retrieval miss.
    """
    if kind not in KINDS:
        raise ValueError(f"Unknown kind {kind!r}; known: {sorted(KINDS)}")
    sections, pattern = KINDS[kind]
    df = records
    if well:
        df = df[df["well"] == well]
    if report_date:
        df = df[df["report_date"] == report_date]
    if require_value:
        df = df[~df["missing"]]
    if sections and pattern is None:
        return bool(df["section"].isin(sections).any())
    rx = re.compile(pattern, re.IGNORECASE)
    if sections:
        df = df[df["section"].isin(sections)]
    if df["field"].map(lambda f: bool(rx.search(f))).any():
        return True
    # row records keep their other fields in attrs; check those keys too
    for a in df["attrs"].dropna():
        if any(rx.search(k) for k in _attr_keys(a)):
            return True
    return False


def _attr_keys(attrs_json: str) -> list[str]:
    import json

    return list(json.loads(attrs_json))


def text_mentions(records: pd.DataFrame, pattern: str, well: str | None = None,
                  report_date: str | None = None) -> pd.DataFrame:
    """Records whose compact `text` line matches `pattern` (narrative search)."""
    df = records
    if well:
        df = df[df["well"] == well]
    if report_date:
        df = df[df["report_date"] == report_date]
    return df[df["text"].str.contains(pattern, case=False, regex=True, na=False)]
