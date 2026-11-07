"""Score results.json against expected.json (computed independently from the XML by gen.py). No archive_qa imports.

A question scores 1 when: expected a value and the answer contains every expected item AND the evidence cites every
expected report (archive-wide questions: at least one); or expected an absence and the pipeline abstained.
Failures are grouped by cause. Matching is lenient on purpose (numbers compared numerically, dates in any common format).
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else Path(__file__).resolve().parent
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
MON = "|".join(MONTHS + [m[:3] for m in MONTHS])
DATE_RX = [re.compile(p, re.I) for p in (r"\d{4}-\d{2}-\d{2}(?:[t ]\d{2}:\d{2}(?::\d{2})?)?", r"\d{1,2}[/.]\d{1,2}[/.]\d{4}",
                                         rf"\d{{1,2}}(?:st|nd|rd|th)?\s+(?:of\s+)?(?:{MON})\.?,?\s+\d{{4}}",
                                         rf"(?:{MON})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}",
                                         r"15[/_]9[-_ ](?:f[-_ ]?\d+|19)(?:[-_ ]?[a-d]|[-_ ]?t\d)?", r"\d{1,2}:\d{2}")]


def strip_noise(text: str) -> str:
    for rx in DATE_RX:
        text = rx.sub(" ", text)
    return text


def numbers(text: str) -> list[float]:
    t = re.sub(r"(?<=\d),(?=\d{3}\b)", "", strip_noise(text))
    return [float(x) for x in re.findall(r"(?<![\w.])-?\d+(?:\.\d+)?", t)]


def has_date(text: str, iso: str) -> bool:
    y, m, d = (int(x) for x in iso.split("-"))
    mon = MONTHS[m - 1]
    pats = [iso, f"{d:02d}/{m:02d}/{y}", f"{d}/{m}/{y}", f"{d:02d}.{m:02d}.{y}"]
    low = text.lower()
    if any(p in low for p in pats):
        return True
    return bool(re.search(rf"\b{d}(?:st|nd|rd|th)?\s+(?:of\s+)?(?:{mon}|{mon[:3]})\.?,?\s+{y}\b", low)
                or re.search(rf"\b(?:{mon}|{mon[:3]})\.?\s+{d}(?:st|nd|rd|th)?,?\s+{y}\b", low))


def has_well(text: str, token: str) -> bool:
    m = re.fullmatch(r"(f-\d+|19)(?:-([a-d]|t\d))?", token)
    base, sfx = m[1], m[2]
    sep = r"[-\s_]?"
    pat = re.escape(base).replace("\\-", sep) + (sep + sfx + r"(?![a-z0-9])" if sfx else r"(?![a-z0-9]|[-\s_]?[a-d]\b|[-\s]?t\d)")
    return bool(re.search(r"(?<![a-z0-9])" + pat, text.lower()))


def item_ok(item: str, answer: str) -> bool:
    kind, _, val = item.partition(":")
    if kind == "num":
        return any(abs(n - float(val)) < 1e-6 for n in numbers(answer))
    if kind == "date":
        return has_date(answer, val)
    if kind == "well":
        return has_well(answer, val)
    return val in re.sub(r"\s+", " ", answer.lower())


def main() -> None:
    exp = json.loads((HERE / "expected.json").read_text())
    res = json.loads((HERE / "results.json").read_text())
    rows, causes = [], defaultdict(list)
    for qid, e in exp.items():
        r = res.get(qid)
        if r is None:
            causes["no result"].append(qid); rows.append((qid, 0)); continue
        ok, cause = False, ""
        stem_hit = lambda: [f for f in e["files"] if f in r["evidence"]]
        if r["status"] == "not_evaluated":
            cause = "not evaluated (no key / model failure)"
        elif e["kind"] == "abstain":
            if r["status"] == "abstain":
                ok = True
            else:
                cause = "invented an answer for a field the archive does not hold"
        elif r["status"] != "answered" and r["status"] != "partial":
            if r["early_abstain"]:
                cause = "router early-abstained although the report exists"
            elif e["files"] and not set(e["files"]) & set(r["candidates"]):
                cause = "abstained: routed to the wrong or no report"
            else:
                cause = "abstained although the evidence was in the candidate report(s)"
        else:
            missing = [i for i in e["expected"]["all"] if not item_ok(i, r["answer"])]
            if missing:
                routed = (not e["files"]) or (set(e["files"]) <= set(r["candidates"]))
                cause = ("wrong value: report(s) were routed correctly" if routed else "wrong value: wrong or incomplete routing") \
                    + " | missing " + ", ".join(missing)
            elif ((e["files"] and not stem_hit()) if e["category"] == "archive" else len(stem_hit()) < len(e["files"])):
                cause = "right answer, evidence does not cite the expected report(s)"
            else:
                ok = True
        rows.append((qid, int(ok)))
        if not ok:
            causes[cause.split(" | ")[0]].append((qid, cause.split(" | ")[1] if " | " in cause else ""))
    total = sum(s for _, s in rows)
    print(f"SCORE {total}/{len(rows)} = {100 * total / len(rows):.1f}%")
    by_cat = defaultdict(lambda: [0, 0])
    for qid, s in rows:
        c = exp[qid]["category"]; by_cat[c][0] += s; by_cat[c][1] += 1
    print("by category:", {c: f"{a}/{b}" for c, (a, b) in by_cat.items()})
    for cause, items in sorted(causes.items(), key=lambda kv: -len(kv[1])):
        print(f"\n[{len(items)}] {cause}")
        for it in items:
            qid, extra = it if isinstance(it, tuple) else (it, "")
            print(f"   {qid} {exp[qid]['field']:<18} mode={res[qid]['mode']:<13} {extra}")
    costs = [r["cost_usd"] for r in res.values()]
    print(f"\ncost per question (this cache's recorded usage): mean ${sum(costs) / len(costs):.4f}, max ${max(costs):.4f}, total ${sum(costs):.4f}")
    json.dump({qid: s for qid, s in rows}, open(HERE / "scores.json", "w"))


if __name__ == "__main__":
    sys.exit(main())
