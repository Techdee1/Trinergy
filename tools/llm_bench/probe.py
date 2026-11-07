"""Probe which parameter combos each Anthropic model/provider accepts (tiny prompts)."""
import itertools, json, os, sys
from dotenv import load_dotenv
load_dotenv("../../.env")
import openrouter_client as oc
from pathlib import Path
cfg = oc.ClientConfig(cache_dir=Path("results/cache"), ledger_path=Path("results/ledger.csv"), spend_cap_usd=1.0)
models = sys.argv[1].split(",")
for m in models:
    for jm, rs, rp in itertools.product(["json_schema", "json_object", "none"], [None, {"effort": "none"}, {"effort": "low"}], [True, False]):
        prov = {"require_parameters": rp} if jm != "none" else None
        if jm == "none" and rp is False: continue
        res = oc.call_llm("Reply with JSON only.", "[A-1] density 1.03 g/cm3", "What is the density?", m, max_tokens=120,
                          reasoning=rs, json_mode=jm, provider=prov if jm != "none" else None, config=cfg, use_cache=False, source="probe")
        # require_parameters only passed when json_mode != none (client defaults to True); emulate False by explicit dict
        print(f"{m[:24]:24s} {jm:11s} reasoning={json.dumps(rs):18s} reqparams={rp!s:5s} -> http {res.http_status} err={res.error:10s} valid={res.parsed is not None} prov={res.provider} raw={res.raw_text[:70]!r}", flush=True)
