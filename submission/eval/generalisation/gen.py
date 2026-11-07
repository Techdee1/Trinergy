"""Generate challenge-style questions for the generalisation baseline, with expected answers computed by reading the
WITSML XML DIRECTLY (xml.etree only: nothing from archive_qa is imported, so the key is independent of the pipeline).

    python submission/eval/generalisation/gen.py            -> questions.csv, expected.json

Question templates are generic (one per field kind); which report and field each uses is sampled with a fixed seed.
Expected answers never come from the model or from the pipeline's evidence store.
"""

from __future__ import annotations

import csv
import glob
import json
import random
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
MISSING = {"-999.99", "None", ""}
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November",
          "December"]


def data_xml_dir() -> Path:
    for p in [Path("external/nape-aice-2026-hackathon/data/track_2"), Path(__file__).resolve().parents[3] / "external/nape-aice-2026-hackathon/data/track_2"]:
        d = p / "documents/daily_drilling_reports/Daily_Drilling_Report___XML_Version"
        if d.is_dir():
            return d
    raise FileNotFoundError("organiser XML directory not found")


def tag(e): return e.tag.split("}")[-1]


class Rep:
    """One XML report read straight from disk."""

    def __init__(self, path: Path):
        self.path, self.stem = path, path.stem
        self.root = ET.parse(path).getroot()
        m = re.match(r"(.*)_(\d{4})_(\d{2})_(\d{2})$", self.stem)
        self.date = f"{m[2]}-{m[3]}-{m[4]}"
        self.y, self.mo, self.d = int(m[2]), int(m[3]), int(m[4])
        self.wellbore = self.first("nameWellbore")                        # e.g. "NO 15/9-F-11 B"

    def all(self, name): return [e for e in self.root.iter() if tag(e) == name]

    def vals(self, name): return [(e.text or "").strip() for e in self.all(name) if (e.text or "").strip() not in MISSING]

    def first(self, name):
        v = self.vals(name)
        return v[0] if v else None

    def has_tag(self, name): return bool(self.all(name))

    def fluids(self):
        out = []
        for f in self.all("fluid"):
            out.append({tag(c): (c.text or "").strip() for c in f if len(c) == 0})
        return out


def num(s: str) -> str:
    x = float(s)
    return str(int(x)) if x == int(x) else repr(x)


def well_variants(wb: str) -> list[str]:
    """Different ways a person writes the wellbore name: from the XML name 'NO 15/9-F-11 B'."""
    core = re.sub(r"^NO\s+", "", wb)                                       # 15/9-F-11 B
    m = re.match(r"15/9-(F-\d+|19)(?:[ -]([A-Z]\d?))?$", core)
    base, sfx = (m[1], m[2]) if m else (core, None)
    sep = lambda s: f"{base}{s}{sfx}" if sfx else base
    v = [core, f"NO {core}", f"15/9-{sep('-')}", f"15/9-{sep(' ')}"]
    if base.startswith("F-"):
        v += [sep("-"), sep(" ") if sfx else base]
        if sfx and len(sfx) == 1:
            v.append(sep(""))                                              # F-11B
    return list(dict.fromkeys(v))


def date_variants(r: Rep) -> list[str]:
    mon = MONTHS[r.mo - 1]
    suf = "th" if 10 <= r.d % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(r.d % 10, "th")
    return [r.date, f"{r.d} {mon} {r.y}", f"{mon} {r.d}{suf}, {r.y}", f"{r.d:02d}/{r.mo:02d}/{r.y}", f"{r.d} {mon[:3]} {r.y}"]


def main() -> None:
    global HERE
    seed = int(sys.argv[sys.argv.index("--seed") + 1]) if "--seed" in sys.argv else 20260507
    if "--out" in sys.argv:
        HERE = Path(sys.argv[sys.argv.index("--out") + 1]).resolve()
        HERE.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    reps = [Rep(Path(p)) for p in sorted(glob.glob(str(data_xml_dir() / "*.xml")))]
    by_stem = {r.stem: r for r in reps}
    ph = lambda r, i: (f"{rng.choice(well_variants(r.wellbore))}", rng.choice(date_variants(r)))
    qs: list[dict] = []

    def add(cat, text, kind, expected, files, extra=None):
        qs.append({"category": cat, "text": text, "kind": kind, "expected": expected, "files": files, **(extra or {})})

    def pick(pred, n):
        pool = [r for r in reps if pred(r)]
        rng.shuffle(pool)
        return pool[:n]

    # ---- single-report lookups -------------------------------------------------------------------------------
    fields = [
        ("waterDepth", "What was the water depth for well {w} in the report dated {d}?", lambda r: r.first("waterDepth"), 2),
        ("elevKelly", "In the {d} report for well {w}, what was the Kelly bushing elevation?", lambda r: r.first("elevKelly"), 1),
        ("drillContractor", "Which drilling contractor is named in the daily report for {w} on {d}?", lambda r: r.first("drillContractor"), 1),
        ("operator", "Who is listed as the operator in the report of {d} for well {w}?", lambda r: r.first("operator"), 1),
        ("reportNo", "What was the report number of the {d} daily drilling report for {w}?", lambda r: r.first("reportNo"), 2),
        ("mdCsgLast", "On well {w}, what measured depth was the last casing set at, as stated in the report for {d}?", lambda r: r.first("mdCsgLast"), 2),
        ("strengthForm", "In the report for {w} dated {d}, what formation strength (leak-off or test density) was recorded?", lambda r: r.first("strengthForm") if r.first("strengthForm") not in (None, "0") else None, 1),
        ("presTestType", "What kind of formation pressure test was reported for {w} on {d}?", lambda r: r.first("presTestType"), 1),
        ("dTimSpud", "On what date was well {w} spudded, according to the {d} report?", lambda r: (r.first("dTimSpud") or "")[:10] or None, 2),
        ("dateDrillComplete", "According to the report of {d} for well {w}, what was the date drilling was completed?", lambda r: r.first("dateDrillComplete"), 1),
        ("mdKickoff", "What was the kick-off depth recorded for {w} in the report dated {d}?", lambda r: r.first("mdKickoff"), 1),
    ]
    for name, tmpl, getter, n in fields:
        for r in pick(lambda r: getter(r) is not None, n):
            w, d = ph(r, 0)
            v = getter(r)
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
                exp = "date:" + v
            elif re.fullmatch(r"-?\d+(\.\d+)?", v):
                exp = "num:" + num(v)
            else:
                exp = "txt:" + v.lower()
            add("single", tmpl.format(w=w, d=d), "value", {"all": [exp]}, [r.stem], {"field": name})
    # fluid property of a sample identified by type + location (unique within the report)
    for prop, label, n in [("density", "density", 2), ("pv", "plastic viscosity", 1), ("yp", "yield point", 1), ("visFunnel", "funnel viscosity", 1)]:
        cands = []
        for r in reps:
            fl = r.fluids()
            for f in fl:
                same = [g for g in fl if g.get("type") == f.get("type") and g.get("locationSample") == f.get("locationSample")]
                if f.get(prop) not in MISSING and len({g.get(prop) for g in same}) == 1 and len(same) == 1:
                    cands.append((r, f))
        rng.shuffle(cands)
        for r, f in cands[:n]:
            w, d = ph(r, 0)
            add("single", f"What was the {label} of the {f['type']} sampled from the {f['locationSample'].lower()} on {w}, report of {d}?",
                "value", {"all": ["num:" + num(f[prop])]}, [r.stem], {"field": prop})
    # equipment failure class, gas reading, bit manufacturer
    for r in pick(lambda r: len(r.all("equipFailureInfo")) == 1, 1):
        w, d = ph(r, 0)
        add("single", f"What equipment class was affected by the equipment failure logged for {w} in the {d} report?", "value",
            {"all": ["txt:" + r.first("equipClass").split(" -- ")[0].lower()]}, [r.stem], {"field": "equipClass"})
    for r in pick(lambda r: len(r.vals("gasHigh")) >= 1 and len(r.all("gasReadingInfo")) == 1, 1):
        w, d = ph(r, 0)
        add("single", f"What was the highest gas reading (in %) for well {w} in the report for {d}?", "value", {"all": ["num:" + num(r.first("gasHigh"))]}, [r.stem], {"field": "gasHigh"})
    for r in pick(lambda r: len(r.all("bitRecord")) == 1 and r.first("manufacturer"), 1):
        w, d = ph(r, 0)
        add("single", f"Which manufacturer made the bit recorded on {w} on {d}?", "value", {"all": ["txt:" + r.first("manufacturer").lower()]}, [r.stem], {"field": "manufacturer"})
    for r in pick(lambda r: len(r.all("surveyStation")) > 0, 1):
        stations = r.all("surveyStation")
        inc = [(float(s.find(".//{*}incl").text), s) for s in stations if s.find(".//{*}incl") is not None]
        best = max(inc, key=lambda t: t[0])
        w, d = ph(r, 0)
        add("single", f"What is the largest inclination among the survey stations in the {d} report for well {w}?", "value",
            {"all": ["num:" + num(str(best[0]))]}, [r.stem], {"field": "incl"})

    # ---- cross-report comparisons -----------------------------------------------------------------------------
    def comp(prop_name, getter, text, higher=True):
        pool = [r for r in reps if getter(r) is not None]
        rng.shuffle(pool)
        a = pool[0]
        b = next(x for x in pool[1:] if x.wellbore != a.wellbore and float(getter(x)) != float(getter(a)))
        win = a if (float(getter(a)) > float(getter(b))) == higher else b
        wa, da = ph(a, 0)
        wb, db = ph(b, 0)
        add("compare", text.format(wa=wa, da=da, wb=wb, db=db), "value",
            {"all": ["num:" + num(getter(a)), "num:" + num(getter(b)), "well:" + re.sub(r"^NO\s+15/9-", "", win.wellbore).replace(" ", "-").lower()]},
            [a.stem, b.stem], {"field": prop_name})

    comp("waterDepth", lambda r: r.first("waterDepth"), "Which was in deeper water: well {wa} (report {da}) or well {wb} (report {db})? Give both water depths.")
    comp("mdCsgLast", lambda r: r.first("mdCsgLast"), "Compare the last casing depth in the {da} report for {wa} with that in the {db} report for {wb}: which was deeper, and by how much?")
    # the difference is also required for the second comparison
    last = qs[-1]
    a, b = (by_stem[s] for s in last["files"])
    last["expected"]["all"] = [x for x in last["expected"]["all"] if x.startswith(("num:", "well:"))] + ["num:" + num(str(round(abs(float(a.first("mdCsgLast")) - float(b.first("mdCsgLast"))), 4)))]
    comp("elevKelly", lambda r: r.first("elevKelly"), "Was the Kelly elevation higher in the {da} report for {wa} or the {db} report for {wb}? State both values.")
    comp("strengthForm", lambda r: r.first("strengthForm") if r.first("strengthForm") not in (None, "0") else None, "Which had the higher formation strength, {wa} in the report of {da} or {wb} in the report of {db}? Give both values.")

    # ---- archive-wide counts / maxima -------------------------------------------------------------------------
    wellbores = sorted({r.wellbore for r in reps})
    wb = rng.choice([w for w in wellbores if sum(r.wellbore == w for r in reps) >= 3])
    n = sum(r.wellbore == wb for r in reps)
    add("archive", f"How many daily drilling reports does the archive hold for well {rng.choice(well_variants(wb))}?", "value", {"all": ["num:" + str(n)]},
        [r.stem for r in reps if r.wellbore == wb], {"field": "count_by_well"})
    add("archive", "How many different wellbores have daily drilling reports in the archive?", "value", {"all": ["num:" + str(len(wellbores))]}, [], {"field": "count_wellbores"})
    deepest = max((r for r in reps if r.first("mdCsgLast")), key=lambda r: float(r.first("mdCsgLast")))
    add("archive", "Across all reports in the archive, what is the deepest last-casing measured depth, and for which well and date?", "value",
        {"all": ["num:" + num(deepest.first("mdCsgLast")), "date:" + deepest.date]}, [deepest.stem], {"field": "max_mdCsgLast"})
    shallow = min((r for r in reps if r.first("waterDepth")), key=lambda r: float(r.first("waterDepth")))
    tie = [r for r in reps if r.first("waterDepth") and float(r.first("waterDepth")) == float(shallow.first("waterDepth"))]
    add("archive", "What is the smallest water depth recorded anywhere in the archive, and how many reports state that depth?", "value",
        {"all": ["num:" + num(shallow.first("waterDepth")), "num:" + str(len(tie))]}, [r.stem for r in tie], {"field": "min_waterDepth"})
    nlot = sum(1 for r in reps if r.first("presTestType") and "leak" in r.first("presTestType").lower())
    add("archive", "In how many reports of the archive is a leak-off test given as the formation pressure test type?", "value", {"all": ["num:" + str(nlot)]},
        [r.stem for r in reps if r.first("presTestType") and "leak" in r.first("presTestType").lower()], {"field": "count_lot"})

    # ---- fields the archive does not hold (verified absent in every XML: no tag and no word in any text) -------
    text_all = " ".join(ET.tostring(r.root, encoding="unicode").lower() for r in reps)
    absent_topics = [
        ("helicopter", "How many helicopter flights were made to the rig for well {w} on {d}?"),
        ("diesel", "How much diesel fuel was consumed on well {w} in the report of {d}?"),
        ("barite", "What was the barite stock on board for well {w} on {d}?"),
        ("day rate", "What was the rig day rate for well {w} in the report dated {d}?"),
        ("injur", "How many lost-time injuries were recorded for well {w} on {d}?"),
        ("pit volume", "What was the total mud pit volume for well {w} in the {d} report?"),
        ("visibility", "What was the visibility and wind speed at the rig for well {w} on {d}?"),
        ("salinity", "What was the salinity of the drilling fluid on well {w} on {d}?"),
    ]
    for term, tmpl in absent_topics:
        assert term not in text_all, f"{term} is present in the archive; not an absence question"
    for term, tmpl in absent_topics[:6]:
        r = rng.choice(reps)
        w, d = ph(r, 0)
        add("absent", tmpl.format(w=w, d=d), "abstain", {"absent_term": term}, [r.stem], {"field": term})
    # a report that does not exist: right well, a date with no report
    existing = {(r.wellbore, r.date) for r in reps}
    for r in rng.sample(reps, 1):
        for off in (3, 5, 9):
            y, mo, dd = r.y, r.mo, r.d + off
            if dd <= 28 and (r.wellbore, f"{y}-{mo:02d}-{dd:02d}") not in existing and all(x.date != f"{y}-{mo:02d}-{dd:02d}" or x.wellbore != r.wellbore for x in reps):
                add("absent", f"What was the water depth for well {rng.choice(well_variants(r.wellbore))} in the report dated {dd} {MONTHS[mo-1]} {y}?", "abstain",
                    {"absent_term": "no such report"}, [], {"field": "no_report"})
                break

    # ---- number and write ------------------------------------------------------------------------------------
    rng.shuffle(qs)
    for i, q in enumerate(qs, 1):
        q["id"] = f"G-{i:03d}"
    with (HERE / "questions.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["question_id", "question_text"])
        for q in qs:
            w.writerow([q["id"], q["text"]])
    (HERE / "expected.json").write_text(json.dumps({q["id"]: {k: q[k] for k in ("category", "kind", "expected", "files", "field")} for q in qs},
                                                   indent=1, ensure_ascii=False), encoding="utf-8")
    from collections import Counter
    print(len(qs), "questions", dict(Counter(q["category"] for q in qs)))


if __name__ == "__main__":
    sys.exit(main())
