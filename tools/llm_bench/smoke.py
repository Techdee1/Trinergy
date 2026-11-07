import json, os
from dotenv import load_dotenv
load_dotenv("../../.env")
import openrouter_client as oc
cfg = oc.ClientConfig(cache_dir="results/cache", ledger_path="results/ledger.csv", spend_cap_usd=1.0)
import pathlib; cfg.cache_dir = pathlib.Path(cfg.cache_dir); cfg.ledger_path = pathlib.Path(cfg.ledger_path)
r = oc.call_llm("Reply with JSON only.", "[A-1] density 1.03 g/cm3", "What is the density?", "meta-llama/llama-4-scout", config=cfg, use_cache=False, source="smoke")
d = r.__dict__.copy(); print(json.dumps(d, indent=1)[:1200])
