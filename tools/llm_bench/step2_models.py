import json, requests
d = requests.get("https://openrouter.ai/api/v1/models", timeout=60).json()["data"]
json.dump(d, open("results/models_raw.json", "w"))
rows = []
for m in d:
    sp = set(m.get("supported_parameters") or [])
    a = m.get("architecture", {})
    if not ({"structured_outputs", "response_format"} & sp): continue
    if (m.get("context_length") or 0) < 32000: continue
    if "text" not in a.get("output_modalities", []) or "text" not in a.get("input_modalities", []): continue
    if m["id"].endswith(":free"): continue
    try: pi = float(m["pricing"]["prompt"])*1e6; po = float(m["pricing"]["completion"])*1e6
    except Exception: continue
    if pi < 0: continue
    rows.append((m["id"], pi, po, m["context_length"], "reasoning" in sp, "structured_outputs" in sp, m.get("created")))
print(len(rows), "eligible of", len(d))
import re
fam = re.compile(r"^(anthropic|openai|google|deepseek|qwen|meta-llama|mistralai|x-ai|z-ai|moonshotai|amazon|nvidia)/")
rows = [r for r in rows if fam.match(r[0])]
rows.sort(key=lambda r: r[1]*3+r[2])
for r in rows: print(f"{r[0]:55s} in {r[1]:7.3f} out {r[2]:7.3f} ctx {r[3]:8d} reas={int(r[4])} so={int(r[5])}")
