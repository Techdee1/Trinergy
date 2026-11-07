"""3-step tool loop with a dummy lookup tool (for the later interactive agent demo)."""
import json, re, sys, time
from pathlib import Path
from dotenv import load_dotenv
load_dotenv("../../.env")
import openrouter_client as oc

CFG = oc.ClientConfig(cache_dir=Path("results/cache"), ledger_path=Path("results/ledger.csv"), spend_cap_usd=1.0)
CASE = next(c for c in json.load(open("cases.json")) if c["id"] == "A2_water_depth")
LINES = {l[1:l.index("]")]: l for l in CASE["context"].split("\n")}
TOOLS = [
    {"type": "function", "function": {"name": "search_records", "description": "List record IDs for a well report date (YYYY-MM-DD) and a record kind (STATUS, ACT, FLUID, CSG, FAIL).",
     "parameters": {"type": "object", "properties": {"well": {"type": "string"}, "date": {"type": "string"}, "kind": {"type": "string"}}, "required": ["well", "date", "kind"]}}},
    {"type": "function", "function": {"name": "get_record", "description": "Return the evidence line for a record ID.",
     "parameters": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}}},
]
SYSTEM = ('Use the tools to find evidence, then reply with JSON only: {"status":"answered"|"partial"|"abstain","answer":str,"cited_ids":[str],"rationale":str}. Cite only IDs returned by tools.')
Q = "What water depth was reported for well 15/9-F-1 B in the report dated 2013-08-30?"

def run_tool(name, args):
    if name == "search_records":
        ids = [i for i in LINES if i.startswith("F1B-20130830") and args.get("kind", "").upper() in i]
        return json.dumps(ids)
    if name == "get_record":
        return LINES.get(args.get("id", ""), "not found")
    return "unknown tool"

def loop(model, extra):
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": Q}]
    cost = 0.0; calls = 0; bad = 0; t0 = time.perf_counter(); tok_in = tok_out = 0
    for step in range(6):
        if oc.ledger_total(CFG.ledger_path) > 0.85:
            return {"error": "spend guard"}
        payload = {"model": model, "messages": msgs, "tools": TOOLS, "tool_choice": "auto", "temperature": 0, "max_tokens": 400, **extra}
        r = oc._http_post(f"{oc.BASE_URL}/chat/completions", {"Authorization": f"Bearer {oc._get_key()}", "Content-Type": "application/json"}, payload, 90)
        if r.status_code != 200:
            return {"error": f"http {r.status_code} {str(r.text)[:160]}", "cost": cost}
        b = r.json(); u = b.get("usage", {}); cost += float(u.get("cost") or 0); tok_in += u.get("prompt_tokens", 0); tok_out += u.get("completion_tokens", 0)
        res = oc.LLMResult(parsed=None, raw_text="", model=model, provider=b.get("provider", ""), input_tokens=u.get("prompt_tokens", 0),
                           output_tokens=u.get("completion_tokens", 0), cost=float(u.get("cost") or 0), latency_s=0)
        oc._append_ledger(CFG, res, "tool_test")
        m = b["choices"][0]["message"]; msgs.append({k: v for k, v in m.items() if k in ("role", "content", "tool_calls", "reasoning_details") and v is not None})
        if not m.get("tool_calls"):
            parsed = oc._parse_json(m.get("content") or "")
            ok = bool(parsed) and re.search(r"\b91\b", parsed["answer"]) is not None and all(c in LINES for c in parsed["cited_ids"])
            return {"steps": step + 1, "tool_calls": calls, "bad_args": bad, "final_valid_json": parsed is not None, "correct": ok, "cost": cost,
                    "latency_s": time.perf_counter() - t0, "in": tok_in, "out": tok_out}
        for tc in m["tool_calls"]:
            calls += 1
            try:
                args = json.loads(tc["function"]["arguments"] or "{}")
            except ValueError:
                args = {}; bad += 1
            msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": run_tool(tc["function"]["name"], args)})
    return {"error": "no final answer in 6 steps", "cost": cost}

CONF = {"openai/gpt-oss-120b": {"reasoning": {"effort": "low"}},
        "anthropic/claude-haiku-5.5": {"reasoning": {"effort": "none"}, "provider": {"order": ["Anthropic"], "allow_fallbacks": False}}}
for m, extra in CONF.items():
    for i in range(3):
        print(m, i, json.dumps(loop(m, extra)), flush=True)
