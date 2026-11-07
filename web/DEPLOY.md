# Deploying the API on Render

Nothing here has been deployed and no credential is stored anywhere in the repo. Follow the steps yourself.

## What gets deployed

The repo as it is on `main`: `submission/` (pipeline and committed answer cache), `web/server/` (API) and `web/server/data/` (the 7.5 MB data pack: records, page images, highlight
boxes, unseen-set answers). **No organiser raw file is needed**; `external/` is not in git and not used. The server answers the 72 catalog questions from caches with no key
and no cost; a key only matters for new questions typed into the box.

## 1. Create a separate OpenRouter key with a spending limit

1. Sign in to OpenRouter, open **Keys**, and **Create key**.
2. Name it for this purpose (e.g. `well-archive-demo`) and set a **credit limit of about $3** on the key. Do not reuse your personal or development key.
3. Copy it once (it is shown only at creation). It goes only into Render's dashboard in step 3, never into the repo, a chat or a screenshot.
4. Check the account has at least a few dollars of credit. (A typical new question costs well under one cent; a hard archive-wide one up to about five cents.)

Three independent brakes protect the money: the server's `SERVER_BUDGET_USD` (default $2.00), the per-IP rate limit (6/min, 40/day), and the key's own $3 limit at OpenRouter.
The key limit is the one that always holds: on the free plan the server's spend counter lives on an ephemeral disk and **restarts from zero** after a restart or redeploy.

## 2. Create the service

Option A, Blueprint: in Render choose **New → Blueprint**, select the repository and the `main` branch, and set the Blueprint file path to `web/render.yaml` (if your Render UI only
offers the repo root, use option B).

Option B, by hand: **New → Web Service**, connect the repo, branch `main`, runtime **Python**, root directory empty (the repo root), then:

| setting | value |
|---|---|
| Build command | `pip install -r web/server/requirements.txt` |
| Start command | `uvicorn web.server.app:app --host 0.0.0.0 --port $PORT --workers 1` |
| Health check path | `/health` |
| Auto-deploy | off |
| Instance | Free to rehearse; **Starter on presentation day** (no sleep, more memory) |

Keep `--workers 1`: the rate limiter and the spend counter live in the process.

## 3. Environment variables

| variable | value |
|---|---|
| `PYTHON_VERSION` | `3.12.8` (any 3.12.x Render offers) |
| `OPENROUTER_KEY` | the new key from step 1 (mark it secret). Leave it **unset** to run cache-only: new questions then answer "NOT EVALUATED". |
| `ALLOWED_ORIGINS` | the frontend's origin(s), comma separated, no trailing slash (e.g. `https://well-archive.example.com`). Add `http://localhost:5173` while developing. |
| `SERVER_BUDGET_USD` | `2.00` |
| `RUNTIME_CACHE_DIR` | `/tmp/well-archive-runtime` (free) or `/var/data/runtime` if you attach a persistent disk at `/var/data` (paid plans) |
| `TRUST_PROXY` | `1` |
| `RATE_LIMIT_PER_MIN`, `RATE_LIMIT_PER_DAY` | `6`, `40` (optional) |

Everything else has a safe default (see `web/server/API.md`).

## 4. Deploy and verify

Use **Manual Deploy** and watch the log for `Application startup complete`. Then (replace the URL):

```bash
U=https://well-archive-api.onrender.com
curl -s $U/health                                   # live_mode true only if the key is set; attribution "Data: Equinor Volve dataset"
curl -s $U/questions | head -c 300                  # 72 questions (first call may take ~10 s while the replay warms)
curl -s -o /dev/null -w "%{http_code} %{content_type}\n" $U/pages/19A-19970829-ACT-04.png   # 200 image/png
curl -s -X POST $U/ask -H 'content-type: application/json' \
  -d '{"question":"For well 15/9-19-A in the 1980-01-01 report, what was the kick-off depth in mMD?"}' | head -c 300   # cached answer, source "cache"
```

`/health` must show `details.data_pack.records = 1783`, `budget_remaining_usd = 2.0`, `provider_fallback_active = false`. The interactive docs are at `/docs`.

## 5. Pre-presentation warm-up checklist

The day before
- [ ] Deploy the final `main`; run the four curl checks above; open `/docs`.
- [ ] From the real frontend URL, ask one cached and one new question (this proves CORS and the key). Note `budget_remaining_usd` before and after.
- [ ] Confirm the OpenRouter key's limit and remaining credit on the OpenRouter dashboard.

One hour before
- [ ] Switch the instance to **Starter** (or whatever does not sleep) and redeploy if you changed the plan.
- [ ] `GET /health` until `warm_seconds` is not null (the startup replay finished), then `GET /questions` once.
- [ ] Open every page the demo will show once (`/pages/<record>.png` for the cited records of the demo questions) so the highlighted PNGs are cached.
- [ ] Run each demo question once through the frontend. Cached ones must say `source: cache` and cost nothing.

Ten minutes before
- [ ] `GET /health`: `status ok`, `live_mode true`, `budget_remaining_usd` near 2.0, `provider_fallback_active false`.
- [ ] Keep a tab on `/costs` (budget and cache hit rate) for the session.
- [ ] Know the fallback: if the model is slow or the key fails, stay on the cached questions (they never need the model).

During
- Judges typing new questions spend cents; vague questions get a clarification and cost nothing. If `/ask` returns 429 or 503 `budget_exhausted`, say so: those are the guards working.
- If the app was asleep, the first request takes about a minute; do not retry in a loop (the rate limiter counts retries).

After the event
- [ ] Delete the OpenRouter key (or lower its limit to $0) and clear `OPENROUTER_KEY` in Render, or suspend the service.

## Troubleshooting

| symptom | cause |
|---|---|
| Build fails on `pymupdf` or `pyarrow` | wrong Python version; set `PYTHON_VERSION` to a 3.12.x |
| `Data pack not found` at start | `web/server/data/` missing from the deployed commit (it must be committed) |
| Browser says CORS error | `ALLOWED_ORIGINS` lacks the frontend's exact origin (scheme + host, no trailing slash) |
| `live_mode` false with a key set | key not set for this service, or `SERVER_BUDGET_USD` already used up |
| 429 for everyone | `TRUST_PROXY` not `1`, so all clients share the proxy's IP |
| `/questions` slow once | the startup replay is still warming (about 10 s) |
| trace shows `provider_fallback` | the Anthropic provider is not available on the key; OpenRouter routed the same model elsewhere (answers are still verified) |
