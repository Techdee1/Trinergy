"""Well-name canonicalisation and report discovery.

Canonical form is "15/9-F-1-C": field block, well, optional sidetrack suffix.
A name without a suffix ("15/9-F-1", or bare "F-1") means the MAIN wellbore only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

FIELD = "15/9"

# Sidetrack suffix: a single letter A-D or T<digit>. Case-sensitive on purpose so
# that "F-1 and ..." or "F-11 on ..." never reads "a"/"o" as a suffix.
_SUFFIX = r"(?:[-_ /]?(?P<sfx>T\d|[A-D]))?"
_PREFIX = r"(?:15[/_ \-]9[-_ /]+)"

# Wells like F-1, F-11, F-15 (platform slots) ...
_F_WELL = re.compile(
    rf"(?<![A-Za-z0-9]){_PREFIX}?F[-_ ]?(?P<num>\d{{1,2}})(?!\d){_SUFFIX}(?![A-Za-z0-9])"
)
# ... and plain-numbered exploration wells like 15/9-19-A (prefix required).
_NUM_WELL = re.compile(
    rf"(?<![A-Za-z0-9]){_PREFIX}(?P<num>\d{{1,3}})(?!\d){_SUFFIX}(?![A-Za-z0-9])"
)
_NO_PREFIX = re.compile(r"^\s*NO[\s_\-]+", re.IGNORECASE)


@dataclass(frozen=True)
class WellMention:
    well: str
    start: int
    end: int


def _build(prefix: str, num: str, sfx: str | None) -> str:
    base = f"{FIELD}-{prefix}{num}"
    return f"{base}-{sfx}" if sfx else base


def find_wells(text: str) -> list[WellMention]:
    """All well mentions in free text, in order of appearance, canonicalised."""
    hits: list[WellMention] = []
    for rx, prefix in ((_F_WELL, "F-"), (_NUM_WELL, "")):
        for m in rx.finditer(text):
            hits.append(WellMention(_build(prefix, m["num"], m["sfx"]), m.start(), m.end()))
    hits.sort(key=lambda h: h.start)
    # drop overlaps (e.g. the "15/9-F-1" prefix being re-read as a numbered well)
    clean: list[WellMention] = []
    for h in hits:
        if not clean or h.start >= clean[-1].end:
            clean.append(h)
    return clean


def canonical_well(text: str) -> str | None:
    """First well found in `text`, canonicalised; None if there is none.

    Handles "NO 15/9-F-1 C", "15_9_F_1_C", "15/9-F-11 B", "F-11-B", "F-1",
    "15/9-19-A", "15/9-F-11-T2", ...
    """
    hits = find_wells(_NO_PREFIX.sub("", text))
    return hits[0].well if hits else None


# ----------------------------------------------------------------- reports

_STEM = re.compile(r"^(?P<well>.+?)_(?P<y>\d{4})_(?P<m>\d{2})_(?P<d>\d{2})$")


@dataclass(frozen=True)
class Report:
    stem: str          # e.g. 15_9_F_1_C_2014_03_26
    well: str          # canonical
    report_date: date  # end of the 24 h window (file date)
    xml_path: Path

    @property
    def iso(self) -> str:
        return self.report_date.isoformat()


def parse_stem(stem: str) -> tuple[str, date]:
    m = _STEM.match(stem)
    if not m:
        raise ValueError(f"Unexpected report file name: {stem}")
    well = canonical_well(m["well"])
    if well is None:
        raise ValueError(f"No well found in file name: {stem}")
    return well, date(int(m["y"]), int(m["m"]), int(m["d"]))


def discover_reports(xml_dir: Path) -> list[Report]:
    """All reports in the archive, sorted by (well, date). Known wells come from here."""
    reports = []
    for p in sorted(Path(xml_dir).glob("*.xml")):
        well, d = parse_stem(p.stem)
        reports.append(Report(p.stem, well, d, p))
    return sorted(reports, key=lambda r: (r.well, r.report_date))


def known_wells(reports: list[Report]) -> list[str]:
    return sorted({r.well for r in reports})


def well_code(well: str) -> str:
    """Short id fragment: 15/9-F-1-C -> F1C, 15/9-19-A -> 19A."""
    return re.sub(r"[^A-Za-z0-9]", "", well.removeprefix(FIELD + "-"))
