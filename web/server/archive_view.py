"""Read-only views of the archive: /archive and /trajectories. Everything is derived from the report files and the
evidence store (no well list, no hard-coded values)."""

from __future__ import annotations

import json
import math
import re

import pandas as pd

_PARENT = re.compile(r"^(?P<parent>15/9-(?:F-)?\d+)(?:-(?:[A-D]|T\d))?$")


def parent_well(wellbore: str) -> str:
    m = _PARENT.match(wellbore)
    return m["parent"] if m else wellbore


def archive_summary(reports, records: pd.DataFrame, page_count) -> dict:
    per_src = records.groupby("source_file").size().to_dict()
    per_period = records.groupby("source_file")[["period_start", "period_end"]].first().to_dict("index")
    rep_rows = []
    for r in reports:
        pdf = r.stem + ".pdf"
        pr = per_period.get(r.stem + ".xml", {})
        rep_rows.append({"file": r.stem + ".xml", "pdf_file": pdf, "well": parent_well(r.well), "wellbore": r.well, "date": r.iso,
                         "period_start": pr.get("period_start"), "period_end": pr.get("period_end"),
                         "pages": page_count(pdf), "records": int(per_src.get(r.stem + ".xml", 0))})
    wellbores: dict[str, dict] = {}
    for row in rep_rows:
        wb = wellbores.setdefault(row["wellbore"], {"wellbore": row["wellbore"], "well": row["well"], "reports": 0,
                                                    "first_report": row["date"], "last_report": row["date"]})
        wb["reports"] += 1
        wb["first_report"], wb["last_report"] = min(wb["first_report"], row["date"]), max(wb["last_report"], row["date"])
    wells: dict[str, dict] = {}
    for wb in wellbores.values():
        w = wells.setdefault(wb["well"], {"well": wb["well"], "wellbores": [], "reports": 0})
        w["wellbores"].append(wb["wellbore"])
        w["reports"] += wb["reports"]
    counts = records["section"].value_counts().to_dict()
    notes = int(counts.pop("note", 0))
    return {
        "wells": sorted(wells.values(), key=lambda x: x["well"]),
        "wellbores": sorted(wellbores.values(), key=lambda x: x["wellbore"]),
        "reports": rep_rows,
        "record_counts": {"by_type": {k: int(v) for k, v in sorted(counts.items())}, "total": int(sum(counts.values())),
                          "derived_notes": notes,
                          "note": "derived_notes are XML-vs-PDF discrepancy records computed at build time; they are not archive records"},
        "naming": "wellbore = the canonical name used in the reports (e.g. 15/9-F-1-C); well = the parent slot (15/9-F-1)",
    }


# ------------------------------------------------------------------ trajectories


def _val(attrs: dict, key: str):
    e = attrs.get(key)
    return None if e is None else e.get("value")


def min_curvature(stations: list[dict], tvd_origin: float) -> list[dict]:
    """Minimum-curvature positions for stations sorted by md (md m, incl deg, azi deg). x = east, y = north, relative to the
    first station; tvd_origin is the TVD of the first station."""
    out = []
    n = e = 0.0
    tvd = tvd_origin
    prev = None
    for s in stations:
        if prev is not None:
            i1, i2 = math.radians(prev["incl"]), math.radians(s["incl"])
            a1, a2 = math.radians(prev["azi"]), math.radians(s["azi"])
            dmd = s["md"] - prev["md"]
            cosdl = math.cos(i2 - i1) - math.sin(i1) * math.sin(i2) * (1 - math.cos(a2 - a1))
            dl = math.acos(max(-1.0, min(1.0, cosdl)))
            rf = 1.0 if dl < 1e-9 else 2.0 / dl * math.tan(dl / 2.0)
            n += dmd / 2 * (math.sin(i1) * math.cos(a1) + math.sin(i2) * math.cos(a2)) * rf
            e += dmd / 2 * (math.sin(i1) * math.sin(a1) + math.sin(i2) * math.sin(a2)) * rf
            tvd += dmd / 2 * (math.cos(i1) + math.cos(i2)) * rf
        out.append({"x": round(e, 2), "y": round(n, 2), "tvd": round(tvd, 2)})
        prev = s
    return out


def trajectories(records: pd.DataFrame, min_stations: int = 3) -> dict:
    surv = records[records["section"] == "survey"]
    wells = []
    for wb, grp in surv.groupby("well", sort=True):
        picked: dict[float, dict] = {}
        dropped = dup = 0
        why: dict[str, int] = {}
        for _, r in grp.sort_values(["report_date", "record_id"]).iterrows():
            a = json.loads(r["attrs"]) if isinstance(r["attrs"], str) else {}
            md, azi = _val(a, "md"), _val(a, "azi")
            incl = None if r["missing"] else r["value_num"]
            gaps = [n for n, x in (("md", md), ("incl", incl), ("azi", azi))
                    if not (isinstance(x, (int, float)) and not (isinstance(x, float) and math.isnan(x)))]
            if gaps:
                dropped += 1          # a missing (-999.99) md / inclination / azimuth is never a value
                for g in gaps:
                    why[g] = why.get(g, 0) + 1
                continue
            if md in picked:
                dup += 1              # the same station printed in several reports: first report wins
                continue
            tvd = _val(a, "tvd")
            picked[md] = {"record_id": r["record_id"], "report_date": r["report_date"], "md": float(md), "incl": float(incl),
                          "azi": float(azi), "tvd_reported": float(tvd) if isinstance(tvd, (int, float)) else None}
        stations = [picked[k] for k in sorted(picked)]
        entry = {"wellbore": wb, "approximate": True, "stations_used": len(stations), "stations_dropped": dropped,
                 "duplicate_stations_ignored": dup, "missing_values": why, "stations": [], "status": "ok", "reason": None}
        if len(stations) < min_stations:
            gap = (f" {dropped} station(s) were dropped because of missing values (" + ", ".join(f"{k}: {v}" for k, v in why.items())
                   + "; -999.99 is missing, never a value).") if dropped else ""
            entry.update(status="skipped", reason=f"only {len(stations)} usable survey station(s); at least {min_stations} are needed "
                                                  f"for a meaningful minimum-curvature path.{gap}")
            wells.append(entry)
            continue
        tvd0 = stations[0]["tvd_reported"]
        entry["tvd_origin"] = "reported tvd of the first station" if tvd0 is not None else "assumed vertical to the first station (md used as tvd)"
        pos = min_curvature(stations, tvd0 if tvd0 is not None else stations[0]["md"])
        diffs = []
        for s, p in zip(stations, pos):
            if s["tvd_reported"] is not None:
                diffs.append(abs(p["tvd"] - s["tvd_reported"]))
            entry["stations"].append({**s, **p})
        entry["max_tvd_difference_m"] = round(max(diffs), 2) if diffs else None
        wells.append(entry)
    return {
        "method": "minimum curvature from measured depth, inclination and azimuth; x = east, y = north (m) relative to the first "
                  "station; tvd in m",
        "approximate": True,
        "caveats": ["Only the stations printed in the daily reports are available (sparse), so the path between them is interpolated.",
                    "The first station's absolute position is unknown: x and y start at 0, tvd starts at its reported value.",
                    "tvd_reported is the archive's own TVD; max_tvd_difference_m compares it with the computed value.",
                    "Azimuth is used as printed (no grid/true-north correction)."],
        "wellbores": wells,
    }
