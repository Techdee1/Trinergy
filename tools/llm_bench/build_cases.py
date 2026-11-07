"""Generate benchmark cases from the Volve WITSML daily drilling reports.

Expected values are computed from the XML by code. The 32 official questions are NOT used:
all question texts below are our own templates.

    python build_cases.py   ->  cases.json
"""
from __future__ import annotations

import json
import random
import re
import xml.etree.ElementTree as ET
from pathlib import Path

NS = "{http://www.witsml.org/schemas/1series}"
XML_DIR = (Path(__file__).resolve().parents[2] / "external/nape-aice-2026-hackathon/data/track_2/"
           "documents/daily_drilling_reports/Daily_Drilling_Report___XML_Version")
MISSING = "-999.99"


# ---------------------------------------------------------------- parsing
def txt(el: ET.Element | None, tag: str) -> str:
    c = el.find(NS + tag) if el is not None else None
    return (c.text or "").strip() if c is not None and c.text else ""


def deep(root: ET.Element, tag: str) -> str:
    """First descendant text for tag (operator/contractor live under wellboreInfo)."""
    e = root.find(f".//{NS}{tag}")
    return (e.text or "").strip() if e is not None and e.text else ""


def val(el: ET.Element, tag: str) -> str:
    """Value text with -999.99 treated as missing ('')."""
    v = txt(el, tag)
    return "" if v == MISSING else v


def day(ts: str) -> str:
    return ts[:10]


def hhmm(ts: str) -> str:
    return ts[11:16]


def one_line(s: str, n: int = 110) -> str:
    return re.sub(r"\s+", " ", s).strip()[:n]


def well_code(wellbore: str) -> str:
    """'NO 15/9-F-1 C' -> 'F1C'; 'NO 15/9-19 A' -> '19A'."""
    return re.sub(r"[^A-Za-z0-9]", "", wellbore.replace("NO 15/9-", ""))


def load_reports() -> list[dict]:
    reports = []
    for f in sorted(XML_DIR.glob("*.xml")):
        root = ET.fromstring(f.read_bytes())  # bytes: one file has no XML declaration
        dr = root.find(NS + "drillReport")
        si = dr.find(NS + "statusInfo")
        wellbore = txt(dr, "nameWellbore")
        date = day(txt(si, "dTim"))
        rid = f"{well_code(wellbore)}-{date.replace('-', '')}"
        lines: list[dict] = []
        counters: dict[str, int] = {}

        def add(kind: str, text: str, **vals) -> None:
            counters[kind] = counters.get(kind, 0) + 1
            lines.append({"id": f"{rid}-{kind}-{counters[kind]:02d}", "kind": kind, "text": text,
                          "report": rid, "date": date, "well": wellbore, **vals})

        add("STATUS", " | ".join(p for p in [
            "Report status", f"report no {txt(si, 'reportNo')}", f"date {date}",
            f"MD {val(si, 'md')} m" if val(si, "md") else "",
            f"TVD {val(si, 'tvd')} m" if val(si, "tvd") else "",
            f"water depth {val(si, 'waterDepth')} m" if val(si, "waterDepth") else "",
            f"operator {deep(dr, 'operator')}" if deep(dr, "operator") else "",
            f"drilling contractor {deep(dr, 'drillContractor')}" if deep(dr, "drillContractor") else ""] if p),
            water_depth=val(si, "waterDepth"), contractor=deep(dr, "drillContractor"),
            operator=deep(dr, "operator"))
        for a in dr.iter(NS + "activity"):
            s, e = txt(a, "dTimStart"), txt(a, "dTimEnd")
            md = val(a, "md")
            add("ACT", " | ".join(p for p in [
                "Activity", txt(a, "phase"), txt(a, "proprietaryCode"), txt(a, "state"),
                f"{day(s)} {hhmm(s)}-{hhmm(e)}" if day(s) == day(e) else f"{day(s)} {hhmm(s)} to {day(e)} {hhmm(e)}",
                f"end MD {md} m" if md else "", one_line(txt(a, "comments"))] if p),
                md=md, start=s, end=e, code=txt(a, "proprietaryCode"), comments=txt(a, "comments"))
        for fl in dr.iter(NS + "fluid"):
            ts = txt(fl, "dTim")
            d = val(fl, "density")
            add("FLUID", " | ".join(p for p in [
                "Drilling fluid", txt(fl, "type"), txt(fl, "locationSample"),
                f"density {d} g/cm3" if d else "",
                f"MD {val(fl, 'md')} m" if val(fl, "md") else "",
                f"funnel viscosity {val(fl, 'visFunnel')} s" if val(fl, "visFunnel") else "",
                f"PV {val(fl, 'pv')} mPa.s" if val(fl, "pv") else "",
                f"YP {val(fl, 'yp')} Pa" if val(fl, "yp") else "",
                f"sample {day(ts)} {hhmm(ts)}" if ts else ""] if p),
                density=d, ftype=txt(fl, "type"), loc=txt(fl, "locationSample"), sample=ts)
        for c in dr.iter(NS + "casing_liner_tubing"):
            run = c.find(NS + "casing_liner_tubing_run")
            add("CSG", " | ".join(p for p in [
                "Casing", txt(run, "casingType"),
                f"OD {val(c, 'od')} in" if val(c, "od") else "",
                f"ID {val(c, 'id')} in" if val(c, "id") else "",
                txt(c, "grade"),
                f"length {val(c, 'length')} m" if val(c, "length") else "",
                f"top {val(c, 'mdTop')} m" if val(c, "mdTop") else "",
                f"bottom {val(c, 'mdBottom')} m" if val(c, "mdBottom") else "",
                one_line(txt(run, "description"), 60)] if p),
                id_in=val(c, "id"), length=val(c, "length"), top=val(c, "mdTop"))
        for ef in dr.iter(NS + "equipFailureInfo"):
            add("FAIL", " | ".join(p for p in [
                "Equipment failure", day(txt(ef, "dTim")),
                f"MD {val(ef, 'md')} m" if val(ef, "md") else "",
                txt(ef, "equipClass"), one_line(txt(ef, "description"), 140)] if p),
                fdate=day(txt(ef, "dTim")), description=txt(ef, "description"), fclass=txt(ef, "equipClass"))
        reports.append({"id": rid, "date": date, "well": wellbore, "lines": lines, "file": f.name})
    return reports


# ---------------------------------------------------------------- case helpers
def nice(s: str) -> str:
    """Well name for questions: 'NO 15/9-F-1 C' -> 'F-1 C'."""
    return wellbore_pretty(s)


def wellbore_pretty(s: str) -> str:
    return s.replace("NO 15/9-", "15/9-")


def build_context(targets: list[dict], pool: list[dict], n_total: int, rng: random.Random,
                  exclude_kinds: tuple[str, ...] = (), extra: list[str] | None = None) -> tuple[str, list[str]]:
    """Targets + random fillers from the pool (never the same ids), sorted by id."""
    chosen = {t["id"]: t for t in targets}
    cands = [l for l in pool if l["id"] not in chosen and l["kind"] not in exclude_kinds]
    rng.shuffle(cands)
    for l in cands:
        if len(chosen) >= n_total:
            break
        chosen[l["id"]] = l
    ordered = sorted(chosen.values(), key=lambda l: l["id"])
    rows = [f"[{l['id']}] {l['text']}" for l in ordered] + (extra or [])
    return "\n".join(rows), [l["id"] for l in ordered] + [x[1:x.index("]")] for x in (extra or [])]


def num(value: float | str, name: str, unit: str | None, tol: float = 0.01) -> dict:
    return {"name": name, "kind": "num", "value": float(value), "tol": tol, "unit": unit}


def words(s: str, stop: set[str]) -> list[str]:
    ws = [w for w in re.findall(r"[A-Za-z]{4,}", s) if w.lower() not in stop]
    return sorted(set(ws), key=lambda w: -len(w))[:3]


UNIT_M = r"\bm\b|\bmetres?\b|\bmeters?\b|\bmetre"
UNIT_DENS = r"g\s*/\s*cm|g/cc|sg|specific gravity"
UNIT_IN = r"\bin\b|\binch|\""


def make_cases(reports: list[dict], seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    by_id = {r["id"]: r for r in reports}
    all_lines = [l for r in reports for l in r["lines"]]
    n_records = len(all_lines)
    cases: list[dict] = []

    def get(rid: str) -> dict:
        return by_id[rid]

    def pool_for(rep: dict) -> list[dict]:
        others = [l for r in reports if r["id"] != rep["id"] for l in r["lines"]]
        rng.shuffle(others)
        return rep["lines"] + others[:150]

    def add(cid, ctype, question, targets, pool, n, expected_status, parts, exclude=(), forbidden=None,
            extra=None, **flags):
        ctx, ids = build_context(targets, pool, n, rng, exclude, extra)
        cases.append({"id": cid, "type": ctype, "question": question, "context": ctx, "context_ids": ids,
                      "n_lines": len(ids), "expected_status": expected_status,
                      "gold_ids": [t["id"] for t in targets], "parts": parts,
                      "forbidden": forbidden or [], **flags})

    # ---- A1 direct lookup: fluid density for a named sample
    rep = get("19A-19971110")
    fl = next(l for l in rep["lines"] if l["kind"] == "FLUID" and l["density"])
    add("A1_fluid_density", "A_lookup",
        f"What was the density of the {fl['ftype']} sampled from the {fl['loc']} at {hhmm(fl['sample'])} on "
        f"{day(fl['sample'])} (well {nice(rep['well'])}, report {rep['date']})?",
        [fl], pool_for(rep), 6, "answered", [num(fl["density"], "density", UNIT_DENS)], exclude=("FLUID",))

    # ---- A2 direct lookup: water depth
    rep = get("F1B-20130830")
    st = next(l for l in rep["lines"] if l["kind"] == "STATUS" and l["water_depth"])
    add("A2_water_depth", "A_lookup", f"What water depth was reported for well {nice(rep['well'])} in the report dated {rep['date']}?",
        [st], pool_for(rep), 12, "answered", [num(st["water_depth"], "water_depth", UNIT_M)], exclude=("STATUS",))

    # ---- A3 direct lookup: casing inner diameter
    rep = get("F1-20130812")
    cs = [l for l in rep["lines"] if l["kind"] == "CSG" and l["id_in"]]
    tgt = cs[2]
    add("A3_casing_id", "A_lookup",
        f"What is the inner diameter of the casing joint whose top is at {tgt['top']} m (well {nice(rep['well'])}, report {rep['date']})?",
        [tgt], pool_for(rep), 15, "answered", [num(tgt["id_in"], "casing_id", UNIT_IN, 0.001)])
    # keep other joints in context: add them all
    cases[-1]["context"], cases[-1]["context_ids"] = build_context(cs[:6], pool_for(rep), 15, rng)
    cases[-1]["n_lines"] = len(cases[-1]["context_ids"])

    # ---- A4 direct lookup: end depth of an activity row (large context)
    rep = get("F1-20130824")
    acts = [l for l in rep["lines"] if l["kind"] == "ACT" and l["md"]]
    keyc = {}
    for a in acts:
        keyc.setdefault((day(a["end"]), hhmm(a["end"])), []).append(a)
    tgt = next(v[0] for k, v in keyc.items() if len(v) == 1 and float(v[0]["md"]) > 0 and k[1] not in ("00:00",))
    add("A4_activity_end_depth", "A_lookup",
        f"At what measured depth did the activity that ended at {hhmm(tgt['end'])} on {day(tgt['end'])} end (well {nice(rep['well'])}, report {rep['date']})?",
        [tgt], pool_for(rep), 40, "answered", [num(tgt["md"], "end_md", UNIT_M)])

    # ---- B1 unsupported: daily cost, with ABSENT pseudo-record
    rep = get("F11T2-20130515")
    absent = f"[ABSENT-cost] Searched 32 reports and {n_records:,} records: no cost field exists."
    add("B1_cost_absent_record", "B_unsupported", f"What was the total daily cost of operations for well {nice(rep['well'])} on {rep['date']}?",
        [], pool_for(rep), 9, "abstain", [], extra=[absent], forbidden=[r"\$\s*\d", r"\bUSD\b", r"\bNOK\b"],
        allowed_extra_ids=["ABSENT-cost"])

    # ---- B2 unsupported: drilling supervisor
    rep = get("F12-20080115")
    st = rep["lines"][0]
    add("B2_supervisor", "B_unsupported", f"Who was the drilling supervisor on well {nice(rep['well'])} in the report dated {rep['date']}?",
        [st], pool_for(rep), 10, "abstain", [],
        forbidden=[re.escape(x) for x in (st["contractor"], st["operator"]) if x])

    # ---- B3 unsupported: personnel on board
    rep = get("F15D-20131214")
    add("B3_pob", "B_unsupported", f"How many personnel were on board for well {nice(rep['well'])} on {rep['date']}?",
        [rep["lines"][0]], pool_for(rep), 8, "abstain", [], forbidden=[r"\b\d+\s+(people|persons|personnel|POB)"])

    # ---- C1 partial: failure description + cost
    rep = get("F1-20130824")
    ef = next(l for l in rep["lines"] if l["kind"] == "FAIL" and "Sonic" in l["description"])
    stop = {"failure", "stopped", "repaired", "fault", "tool", "equipment"}
    pats = [re.escape(w) for w in words(ef["description"], stop)] or ["failure"]
    add("C1_failure_cost_partial", "C_partial",
        f"What equipment failure was reported on {ef['fdate']} for well {nice(rep['well'])} (report {rep['date']}), and what was the cost of repairing it?",
        [ef], pool_for(rep), 8, "partial", [{"name": "failure_description", "kind": "text", "patterns": pats}],
        forbidden=[r"\$\s*\d", r"\bUSD\b", r"\bNOK\b"])

    # ---- D1 multi-record: which of two fluid densities is higher
    fa = next(l for l in get("F11B-20130529")["lines"] if l["kind"] == "FLUID" and l["density"])
    fb = next(l for l in get("F1B-20130830")["lines"] if l["kind"] == "FLUID" and l["density"]
              and float(l["density"]) != float(fa["density"]))
    hi, lo = (fa, fb) if float(fa["density"]) > float(fb["density"]) else (fb, fa)
    add("D1_compare_density", "D_multi",
        f"Which was higher: the density of the fluid sampled {day(fa['sample'])} {hhmm(fa['sample'])} (report {fa['date']}, well {nice(fa['well'])}) or the one sampled "
        f"{day(fb['sample'])} {hhmm(fb['sample'])} (report {fb['date']}, well {nice(fb['well'])})? Give the higher value.",
        [fa, fb], pool_for(get(fa["report"])), 20, "answered",
        [num(hi["density"], "higher_density", UNIT_DENS),
         {"name": "which", "kind": "text", "patterns": [re.escape(day(hi["sample"])), re.escape(hi["date"].replace("-", "")), re.escape(hi["id"]),
                                                          re.escape(nice(hi["well"]))]}])

    # ---- D2 multi-record derived: depth difference between two activities
    rep = get("F1-20130824")
    acts = [l for l in rep["lines"] if l["kind"] == "ACT" and l["md"] and day(l["end"]) == "2013-08-23"]
    a1 = next(a for a in acts if float(a["md"]) > 0)
    a2 = next(a for a in acts[acts.index(a1) + 1:] if float(a["md"]) - float(a1["md"]) >= 10)
    diff = float(a2["md"]) - float(a1["md"])
    add("D2_depth_difference", "D_multi_derived",
        f"By how many metres did the measured depth increase between the end of the activity ending {hhmm(a1['end'])} and the end of the activity ending {hhmm(a2['end'])} on {day(a1['end'])} (well {nice(rep['well'])}, report {rep['date']})?",
        [a1, a2], pool_for(rep), 28, "answered", [num(diff, "md_difference", UNIT_M)], derived=True)

    # ---- E1 distractor: same fluid type/location/hour in two wells, different density
    fl_all = [l for l in all_lines if l["kind"] == "FLUID" and l["density"]]
    pair = None
    for i, x in enumerate(fl_all):
        for y in fl_all[i + 1:]:
            if (x["well"] != y["well"] and x["ftype"] == y["ftype"] and x["loc"] == y["loc"]
                    and hhmm(x["sample"]) == hhmm(y["sample"]) and x["density"] != y["density"]):
                pair = (x, y)
                break
        if pair:
            break
    if pair is None:  # relax the hour
        pair = next((x, y) for i, x in enumerate(fl_all) for y in fl_all[i + 1:]
                    if x["well"] != y["well"] and x["ftype"] == y["ftype"] and x["loc"] == y["loc"] and x["density"] != y["density"])
    x, y = pair
    add("E1_distractor_fluid", "E_distractor",
        f"What was the density of the {x['ftype']} in the {x['loc']} for well {nice(x['well'])} in the report dated {x['date']}?",
        [x, y], pool_for(get(x["report"])), 14, "answered", [num(x["density"], "density", UNIT_DENS)],
        exclude=("FLUID",), distractor_ids=[y["id"]])

    # ---- E2 distractor: same activity code and start time in two reports, different depth
    acts_all = [l for l in all_lines if l["kind"] == "ACT" and l["md"] and float(l["md"]) > 0]
    pair = None
    for i, p in enumerate(acts_all):
        for q in acts_all[i + 1:]:
            if (p["report"] != q["report"] and p["code"] == q["code"] and hhmm(p["start"]) == hhmm(q["start"])
                    and p["md"] != q["md"] and p["code"]):
                pair = (p, q)
                break
        if pair:
            break
    p, q = pair
    add("E2_distractor_activity", "E_distractor",
        f"At what measured depth did the '{p['code']}' activity that started at {hhmm(p['start'])} on {day(p['start'])} end (well {nice(p['well'])}, report {p['date']})?",
        [p, q], pool_for(get(p["report"])), 30, "answered", [num(p["md"], "end_md", UNIT_M)], distractor_ids=[q["id"]])

    # ---- F date-window: sample timestamp is D-1 while report date is D
    f_dw = None
    for l in all_lines:
        if l["kind"] == "FLUID" and l["density"] and l["sample"] and day(l["sample"]) < l["date"]:
            rep_lines = [m for m in by_id[l["report"]]["lines"] if m["kind"] == "FLUID"]
            if len(rep_lines) == 1:
                f_dw = l
                break
    rep = by_id[f_dw["report"]]
    pats = [re.escape(day(f_dw["sample"])), re.escape(day(f_dw["sample"])[8:] + r"\b") if False else re.escape(day(f_dw["sample"])[5:])]
    add("F_date_window", "F_datewindow",
        f"What was the density of the drilling fluid in the {f_dw['loc']} at {hhmm(f_dw['sample'])} on {rep['date']} (well {nice(rep['well'])})?",
        [f_dw], pool_for(rep), 6, "answered",
        [num(f_dw["density"], "density", UNIT_DENS), {"name": "mentions_timestamp", "kind": "text", "patterns": pats, "in_rationale": True}],
        exclude=("FLUID",))

    # ---- G multi-part: end depth AND activity
    rep = get("F1C-20140326")
    acts = [l for l in rep["lines"] if l["kind"] == "ACT" and l["md"] and day(l["end"]) == "2014-03-25" and len(l["comments"]) > 15]
    tgt = acts[0]
    toks = [t for t in re.findall(r"[A-Za-z]{4,}", tgt["code"])] + words(tgt["comments"], {"with", "from", "continued"})
    add("G_multipart", "G_multipart",
        f"For well {nice(rep['well'])}, report {rep['date']}: what was the end depth, and what activity was being performed, for the row ending at {hhmm(tgt['end'])} on {day(tgt['end'])}?",
        [tgt], pool_for(rep), 18, "answered",
        [num(tgt["md"], "end_depth", UNIT_M), {"name": "activity", "kind": "text", "patterns": [re.escape(t) for t in toks]}])

    # ---- H wrong-substitute trap: mud logging company vs drilling contractor
    rep = get("F1-20130824")
    st = rep["lines"][0]
    assert st["contractor"], "trap needs a drilling contractor line"
    add("H_wrong_substitute", "H_trap",
        f"Which mud logging company served well {nice(rep['well'])} in the report dated {rep['date']}?",
        [st], pool_for(rep), 10, "abstain", [], forbidden=[re.escape(st["contractor"])], accept_nonabstain_if_clean=True)

    # ---- I derived number: combined length of two casing joints
    rep = get("F1-20130812")
    cs = [l for l in rep["lines"] if l["kind"] == "CSG" and l["length"]]
    c1, c2 = cs[0], cs[1]
    total = float(c1["length"]) + float(c2["length"])
    add("I_derived_sum", "I_derived",
        f"What is the combined length of the two casing joints with tops at {c1['top']} m and {c2['top']} m (well {nice(rep['well'])}, report {rep['date']})?",
        [c1, c2], pool_for(rep), 12, "answered", [num(total, "combined_length", UNIT_M)], derived=True)

    return cases


def main() -> None:
    reports = load_reports()
    cases = make_cases(reports)
    out = Path(__file__).parent / "cases.json"
    out.write_text(json.dumps(cases, indent=1, ensure_ascii=False))
    print(f"{len(reports)} reports, {sum(len(r['lines']) for r in reports)} records -> {len(cases)} cases")
    for c in cases:
        print(f"{c['id']:28s} {c['expected_status']:9s} lines={c['n_lines']:3d}  parts={[p['name'] for p in c['parts']]}")


if __name__ == "__main__":
    main()
