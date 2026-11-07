import json, sys
from dotenv import load_dotenv
load_dotenv("../../.env")
import openrouter_client as oc
from pathlib import Path
cfg = oc.ClientConfig(cache_dir=Path("results/cache"), ledger_path=Path("results/ledger.csv"), spend_cap_usd=1.0)
for m in sys.argv[1].split(","):
    for rs in [None, {"effort": "none"}, {"effort": "minimal"}]:
        res = oc.call_llm("Reply with JSON only.", "[A-1] density 1.03 g/cm3", "What is the density?", m, max_tokens=120, reasoning=rs,
                          provider={"order": ["Anthropic"], "allow_fallbacks": False, "require_parameters": False}, config=cfg, use_cache=False, source="probe")
        print(f"{m[:26]:26s} reasoning={json.dumps(rs):18s} -> http {res.http_status} valid={res.parsed is not None} prov={res.provider} rt={res.reasoning_tokens} lat={res.latency_s:.2f} raw={res.raw_text[:90]!r}", flush=True)
