"""Key + credit check. Never prints the key."""
import json, os, requests
from dotenv import load_dotenv
load_dotenv("../../.env")
key = os.environ["OpenRouter_Key"].strip()
H = {"Authorization": f"Bearer {key}"}
for path in ("key", "credits"):
    r = requests.get(f"https://openrouter.ai/api/v1/{path}", headers=H, timeout=30)
    print(path, r.status_code)
    try:
        d = r.json()
        d = d.get("data", d)
        if isinstance(d, dict):
            d.pop("label", None)  # label can contain key fragment
        print(json.dumps(d, indent=1)[:1500])
    except Exception:
        print(r.text[:200])
    print("rate-limit headers:", {k: v for k, v in r.headers.items() if "ratelimit" in k.lower() or k.lower()=="retry-after"})
