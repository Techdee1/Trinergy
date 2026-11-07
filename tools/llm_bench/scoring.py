"""Automatic scoring of one model response against a generated case."""
from __future__ import annotations

import itertools
import re
from typing import Any

DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?)?|\b\d{1,2}:\d{2}\b")
WELL_RE = re.compile(r"\d+/\d+-[A-Z]?-?\d+(?:\s?[A-Z]\d?)?")
ID_RE = re.compile(r"\b[A-Z0-9]+-\d{8}-[A-Z]+-\d+\b")
NUM_RE = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?")


def numbers(text: str) -> list[float]:
    """Numbers in text, ignoring dates, times, well names and record IDs."""
    t = ID_RE.sub(" ", text)
    t = DATE_RE.sub(" ", t)
    t = WELL_RE.sub(" ", t)
    out = []
    for m in NUM_RE.findall(t):
        try:
            out.append(float(m.replace(",", "")))
        except ValueError:
            pass
    return out


def verifier_ok(answer: str, cited_text: str, tol: float = 0.011) -> tuple[bool, list[float]]:
    """Verifier rule: each number in the answer appears in a cited line, or is the sum,
    difference or mean of two cited numbers. Returns (ok, unsupported_numbers)."""
    src = numbers(cited_text)
    derived = list(src)
    for a, b in itertools.combinations(src, 2):
        derived += [a + b, abs(a - b), (a + b) / 2]
    bad = [n for n in numbers(answer) if not any(abs(n - d) <= tol for d in derived)]
    return (not bad), bad


def _ids(raw: Any) -> list[str]:
    out = []
    for x in raw if isinstance(raw, list) else []:
        s = str(x).strip().strip("[]").strip()
        if s and s not in out:
            out.append(s)
    return out


def score(case: dict, parsed: dict | None, finish_reason: str, raw_text: str, error: str) -> dict:
    s: dict[str, Any] = {"json_valid": parsed is not None, "empty": error == "empty" or not raw_text.strip(),
                         "truncated": finish_reason == "length"}
    blank = {"status": "", "status_ok": False, "answer_correct": False, "cited_exist": False, "invented_ids": 0,
             "cite_has_value": False, "gold_cited": False, "verifier_ok": False, "unit_ok": False,
             "forbidden_hit": False, "parts_ok": "", "n_cited": 0}
    if parsed is None:
        return {**s, **blank}
    status = parsed["status"]
    answer = parsed["answer"]
    cited = _ids(parsed["cited_ids"])
    allowed = set(case["context_ids"])
    invented = [c for c in cited if c not in allowed]
    ctx_lines = {l[1:l.index("]")]: l for l in case["context"].split("\n") if l.startswith("[")}
    cited_text = " ".join(ctx_lines[c] for c in cited if c in ctx_lines)
    exp = case["expected_status"]
    forbidden = any(re.search(p, answer, re.I) for p in case["forbidden"])

    # per-part check
    ans_nums = numbers(answer)
    parts = {}
    unit_ok = True
    for p in case["parts"]:
        if p["kind"] == "num":
            ok = any(abs(n - p["value"]) <= p["tol"] for n in ans_nums)
            parts[p["name"]] = ok
            if ok and p.get("unit") and not re.search(p["unit"], answer, re.I):
                unit_ok = False
        else:
            hay = answer + " " + parsed.get("rationale", "") if p.get("in_rationale") else answer
            parts[p["name"]] = any(re.search(x, hay, re.I) for x in p["patterns"])

    status_ok = status == exp
    if case.get("accept_nonabstain_if_clean"):  # trap: abstain, or any answer that avoids the wrong substitute
        status_ok = not forbidden
    if exp == "abstain":
        correct = status_ok and not forbidden
    elif exp == "partial":
        correct = status == "partial" and all(parts.values()) and not forbidden
    else:
        correct = status == "answered" and all(parts.values()) and not forbidden

    # does a cited line contain each answered numeric value? (derived cases use the verifier rule)
    num_parts = [p for p in case["parts"] if p["kind"] == "num"]
    cited_nums = numbers(cited_text)
    if exp == "abstain" or not num_parts:
        has_val = True
    elif case.get("derived"):
        has_val = verifier_ok(answer, cited_text)[0]
    else:
        has_val = all(any(abs(n - p["value"]) <= p["tol"] for n in cited_nums) for p in num_parts if parts.get(p["name"]))
    vok, _ = verifier_ok(answer, cited_text) if cited else (not ans_nums, [])
    s.update({"status": status, "status_ok": status_ok, "answer_correct": correct,
              "cited_exist": bool(cited) and not invented, "invented_ids": len(invented),
              "cite_has_value": has_val, "gold_cited": any(g in cited for g in case["gold_ids"]) if case["gold_ids"] else True,
              "verifier_ok": vok, "unit_ok": unit_ok, "forbidden_hit": forbidden,
              "parts_ok": ";".join(f"{k}={int(v)}" for k, v in parts.items()), "n_cited": len(cited)})
    return s
