"""Re-score calls.csv from stored raw_text with the current scoring.py and cases.json."""
import json
import pandas as pd
import openrouter_client as oc
from scoring import score

def load() -> pd.DataFrame:
    d = pd.read_csv("results/calls.csv", keep_default_na=False)
    cases = {c["id"]: c for c in json.load(open("cases.json"))}
    out = []
    for _, r in d.iterrows():
        if r.http_status != 200 or r.case_id not in cases:
            out.append({}); continue
        parsed = oc._parse_json(r.raw_text)
        out.append(score(cases[r.case_id], parsed, r.finish_reason, r.raw_text, r.error))
    sc = pd.DataFrame(out, index=d.index)
    for c in sc.columns:
        d[c] = sc[c]
    for c in ["cost", "latency_s", "input_tokens", "output_tokens", "reasoning_tokens"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    for c in ["json_valid", "status_ok", "answer_correct", "cited_exist", "cite_has_value", "gold_cited", "verifier_ok", "unit_ok", "forbidden_hit", "truncated", "empty"]:
        d[c] = d[c].map(lambda x: x is True or str(x) == "True")
    d["invented_ids"] = pd.to_numeric(d["invented_ids"], errors="coerce").fillna(0)
    return d

if __name__ == "__main__":
    pd.set_option("display.width", 250)
    d = load()
    g = d[d.phase == "grid"].groupby("model").agg(cost=("cost", "sum"), json=("json_valid", "mean"), status=("status_ok", "mean"),
        ans=("answer_correct", "mean"), inv=("invented_ids", "sum"), lat=("latency_s", "median"), vok=("verifier_ok", "mean"))
    print(g.round(4).to_string())
    pv = d[d.phase == "grid"].pivot_table(index="case_id", columns=d.model.str.split("/").str[1].str[:10], values="answer_correct", aggfunc="first").astype(int)
    print(pv.to_string())
