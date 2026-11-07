"""/costs and /generalisation: read-only views of the committed ledger, the caches and the evaluation outputs."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path


def _cache_entries(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")).get("entries", {})
    except (OSError, ValueError):
        return {}


def _mix(entries: dict) -> dict:
    by_model: dict[str, dict] = defaultdict(lambda: {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0})
    by_role: dict[str, dict] = defaultdict(lambda: {"calls": 0, "cost_usd": 0.0})
    per_q: dict[str, dict] = defaultdict(lambda: {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0})
    for e in entries.values():
        u = e.get("usage", {})
        for d in (by_model[e.get("model", "?")], per_q[e.get("question_id") or "?"]):
            d["calls"] += 1
            d["prompt_tokens"] += u.get("prompt_tokens", 0)
            d["completion_tokens"] += u.get("completion_tokens", 0)
            d["cost_usd"] += u.get("cost_usd", 0.0)
        r = by_role[e.get("role", "?")]
        r["calls"] += 1
        r["cost_usd"] += u.get("cost_usd", 0.0)
    calls = sum(m["calls"] for m in by_model.values()) or 1
    cost = sum(m["cost_usd"] for m in by_model.values()) or 1.0
    mix = [{"model": k, **{kk: (round(vv, 6) if kk == "cost_usd" else vv) for kk, vv in v.items()},
            "share_of_calls": round(v["calls"] / calls, 4), "share_of_cost": round(v["cost_usd"] / cost, 4)}
           for k, v in sorted(by_model.items(), key=lambda kv: -kv[1]["calls"])]
    return {"model_mix": mix, "by_role": {k: {"calls": v["calls"], "cost_usd": round(v["cost_usd"], 6)} for k, v in sorted(by_role.items())},
            "per_question": {k: {kk: (round(vv, 6) if kk == "cost_usd" else vv) for kk, vv in v.items()} for k, v in sorted(per_q.items())}}


def costs(committed_cache: Path, cost_csv: Path, runtime_cache: Path, gen_caches: list[Path], spend, stats: dict, catalog_sets: dict) -> dict:
    committed = _cache_entries(committed_cache)
    cm = _mix(committed)
    ledger = None
    try:
        with Path(cost_csv).open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        tot = next((r for r in rows if r["question_id"].startswith("TOTAL")), None)
        if tot:
            ledger = {"source": "submission/indexes/cost_summary.csv", "calls": int(tot["calls"]), "prompt_tokens": int(tot["prompt_tokens"]),
                      "completion_tokens": int(tot["completion_tokens"]), "cost_usd": float(tot["cost_usd"]), "label": tot["question_id"]}
    except (OSError, KeyError, ValueError):
        pass
    c_total = sum(v["cost_usd"] for v in cm["per_question"].values())
    gen_entries: dict = {}
    for p in gen_caches:
        gen_entries.update(_cache_entries(p))
    gm = _mix(gen_entries)
    rt = _cache_entries(runtime_cache)
    rm = _mix(rt)
    per_q = []
    for qid, v in {**cm["per_question"], **gm["per_question"], **rm["per_question"]}.items():
        per_q.append({"question_id": qid, "set": catalog_sets.get(qid, "adhoc" if qid.startswith("ASK-") else "other"), **v})
    per_q.sort(key=lambda r: (r["set"], r["question_id"]))
    n_ch = len([1 for q in cm["per_question"] if catalog_sets.get(q) == "challenge"]) or 1
    replay, asks = stats["replay"], stats["ask"]
    rate = lambda s: round(s["cache_hits"] / s["model_calls"], 4) if s["model_calls"] else None  # noqa: E731
    return {
        "ledger": ledger or {"source": "derived from the committed cache (cost_summary.csv not found)",
                             "calls": sum(v["calls"] for v in cm["per_question"].values()), "cost_usd": round(c_total, 6)},
        "derived_from_cache": {"entries": len(committed), "cost_usd": round(c_total, 6),
                               "cost_per_challenge_question_usd": round(c_total / n_ch, 6)},
        "per_question": per_q,
        "model_mix": cm["model_mix"], "by_role": cm["by_role"],
        "other_caches": {"generalisation_read_only": {"entries": len(gen_entries), "cost_usd": round(sum(v["cost_usd"] for v in gm["per_question"].values()), 6),
                                                       "model_mix": gm["model_mix"]},
                         "runtime": {"entries": len(rt), "cost_usd": round(sum(v["cost_usd"] for v in rm["per_question"].values()), 6),
                                     "model_mix": rm["model_mix"]}},
        "cache_hit_rate": {"asks": {**asks, "hit_rate": rate(asks)},
                           "startup_replay": {**replay, "hit_rate": rate(replay)},
                           "note": "since server start; asks = POST /ask and /ask/stream, startup_replay = offline replay of the cataloged questions"},
        "budget": {"server_budget_usd": spend.budget, "spent_usd": round(spend.spent, 6), "remaining_usd": round(spend.remaining, 6),
                   "live_requests": spend.requests, "ask_live_enabled": spend.remaining > 0},
    }


def generalisation(gen_dir: Path) -> dict:
    gen_dir = Path(gen_dir)

    def load(name):
        try:
            return json.loads((gen_dir / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    results, scores, expected = load("results.json"), load("scores.json"), load("expected.json")
    if results is None or scores is None:
        missing = [n for n, v in (("results.json", results), ("scores.json", scores)) if v is None]
        return {"available": False,
                "message": f"No generalisation outputs found in submission/eval/generalisation ({', '.join(missing)} missing). "
                           "Run `python submission/eval/generalisation/run.py` then `score.py` to produce them; they are git-ignored.",
                "summary": None, "questions": []}
    base_scores, base_results = load("scores_baseline.json") or {}, load("results_baseline.json") or {}
    texts: dict[str, str] = {}
    try:
        with (gen_dir / "questions.csv").open(encoding="utf-8-sig", newline="") as f:
            texts = {r["question_id"]: r["question_text"] for r in csv.DictReader(f)}
    except OSError:
        pass
    expected = expected or {}
    qs, cat = [], defaultdict(lambda: {"n": 0, "score": 0.0})
    for qid in sorted(results):
        r, ex = results[qid], expected.get(qid, {})
        sc = scores.get(qid)
        qs.append({"id": qid, "question": texts.get(qid), "category": ex.get("category"), "kind": ex.get("kind"),
                   "expected": ex.get("expected"), "expected_reports": ex.get("files"), "score": sc,
                   "baseline_score": base_scores.get(qid), "status": r.get("status"), "mode": r.get("mode"),
                   "confidence": r.get("confidence"), "verified": r.get("verified"), "cost_usd": r.get("cost_usd"),
                   "answer": r.get("answer"), "evidence": r.get("evidence"), "detail_url": f"/questions/{qid}"})
        c = cat[ex.get("category") or "?"]
        c["n"] += 1
        c["score"] += sc or 0
    n = len(qs)
    mean = lambda d: round(sum(d.values()) / len(d), 4) if d else None  # noqa: E731
    statuses: dict[str, int] = defaultdict(int)
    for r in results.values():
        statuses[r.get("status")] += 1
    return {"available": True, "message": None,
            "summary": {"questions": n, "mean_score": mean({k: v for k, v in scores.items() if k in results}),
                        "baseline_mean_score": mean(base_scores) if base_scores else None,
                        "by_category": {k: {"n": v["n"], "mean_score": round(v["score"] / v["n"], 4)} for k, v in sorted(cat.items())},
                        "status_counts": dict(statuses), "cost_usd": round(sum(r.get("cost_usd", 0) for r in results.values()), 6),
                        "scoring": "1 = the answer contains every expected item and cites every expected report (or abstains when "
                                   "an absence was expected); expected values are computed independently from the XML (see score.py)"},
            "questions": qs}
