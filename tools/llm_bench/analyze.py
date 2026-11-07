import json, re
import pandas as pd
import rescore
from scoring import numbers
pd.set_option("display.width", 260); pd.set_option("display.max_columns", 40)
d = rescore.load()
models = json.load(open("results/models_raw.json"))
price = {m["id"]: (float(m["pricing"]["prompt"]) * 1e6, float(m["pricing"]["completion"]) * 1e6) for m in models}
g = d[d.phase == "grid"]
lat = d[d.phase.isin(["grid", "latency"])]

def dec_key(t):
    try:
        j = json.loads(t); return json.dumps([j["status"], numbers(j["answer"]), sorted(j["cited_ids"])])
    except Exception: return t
rows = []
for m, x in g.groupby("model"):
    L = d[(d.phase == "latency") & (d.model == m)]
    rep = pd.concat([L, x[x.case_id.isin(L.case_id.unique())]]) if len(L) else None
    det_raw = det_dec = ""
    if rep is not None and len(rep):
        per = rep.groupby("case_id")
        det_raw = f"{int((per.raw_text.nunique() == 1).sum())}/4"
        det_dec = f"{int((per.raw_text.apply(lambda s: s.map(dec_key).nunique()) == 1).sum())}/4"
    rows.append({"model": m, "in_$/M": price[m][0], "out_$/M": price[m][1], "avg_in_tok": x.input_tokens.mean(), "avg_out_tok": x.output_tokens.mean(),
                 "avg_reason_tok": x.reasoning_tokens.mean(), "cost_per_call": x.cost.mean(), "p50_s": lat[lat.model == m].latency_s.median(), "max_s": lat[lat.model == m].latency_s.max(),
                 "json_valid": x.json_valid.mean(), "status_acc": x.status_ok.mean(), "answer_acc": x.answer_correct.mean(), "halluc_cites": int(x.invented_ids.sum()),
                 "empty": int(x["empty"].sum()), "length_trunc": int(x.truncated.sum()), "verifier_ok": x.verifier_ok.mean(), "det_raw_4": det_raw, "det_decision_4": det_dec,
                 "provider": ",".join(sorted(x.provider.unique())), "reasoning": x.reasoning_setting.iloc[0]})
S = pd.DataFrame(rows).sort_values("cost_per_call"); S.to_csv("results/summary.csv", index=False)
print(S.round(5).to_string(index=False))

# silent vs detectable errors (answer wrong, JSON valid)
print("\n-- wrong answers: would the code verifier catch them? (cited ids exist AND numbers supported) --")
w = g[~g.answer_correct]
w = w.assign(caught=lambda t: (t.invented_ids > 0) | (~t.verifier_ok) | (~t.cite_has_value))
print(w.groupby("model").agg(wrong=("caught", "size"), caught=("caught", "sum")).to_string())
for _, r in w.iterrows():
    print(f"{r.model[:22]:22s} {r.case_id:24s} status={r.status:8s} parts={r.parts_ok} caught={r.caught}")

# per-case matrix on type
print("\n-- projections (16-case avg tokens) --")
esc = {"sonnet": g[g.model == "anthropic/claude-sonnet-5.5"].cost.mean(), "opus": g[g.model == "anthropic/claude-opus-5.5"].cost.mean()}
print("escalation per-call:", esc)
proj = []
for _, r in S.iterrows():
    c = r.cost_per_call
    proj.append({"model": r.model, "run32": 32 * c, "10runs": 320 * c, "200q": 200 * c, "run32+25%->sonnet": 24 * c + 8 * esc["sonnet"], "run32+25%->opus": 24 * c + 8 * esc["opus"]})
P = pd.DataFrame(proj); P.to_csv("results/projection.csv", index=False)
print(P.round(4).to_string(index=False))
print("share of $15: run32 for haiku", 32 * S[S.model.str.contains("haiku")].cost_per_call.iloc[0] / 15)
# context size scaling
print(g.groupby("model").apply(lambda t: pd.Series({"cost_small(<=8 lines)": t[t.case_id.isin(["A1_fluid_density","B3_pob","C1_failure_cost_partial","F_date_window"])].cost.mean(),
                                                       "cost_large(>=28)": t[t.case_id.isin(["A4_activity_end_depth","D2_depth_difference","E2_distractor_activity"])].cost.mean()})).round(5).to_string())
tot = __import__("openrouter_client").ledger_total(__import__("pathlib").Path("results/ledger.csv"))
print("\nLEDGER TOTAL $%.4f" % tot)
l = pd.read_csv("results/ledger.csv"); print(l.groupby("source").cost.agg(["size", "sum"]).round(4).sort_values("sum", ascending=False).head(8).to_string())
print("by prefix:", l.assign(p=l.source.str.split(":").str[0]).groupby("p").cost.sum().round(4).to_dict())
print("phase costs:", d.groupby("phase").cost.sum().round(4).to_dict())
