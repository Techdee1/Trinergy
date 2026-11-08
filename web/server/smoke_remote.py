"""Remote smoke test / pre-presentation warm-up check for a deployed API. Standard library only; never reads or prints a key.

    python web/server/smoke_remote.py https://well-archive-api.onrender.com
    python web/server/smoke_remote.py URL --no-live                 # free: no model call at all (cached + vague questions only)
    python web/server/smoke_remote.py URL --rate-limit-test         # adds the X-Forwarded-For probes and the 7-in-a-minute burst
    python web/server/smoke_remote.py URL --origin https://my-frontend.vercel.app --json report.json

Live model cost is capped (--max-cost, default $0.03; a handful of single-report questions cost well under $0.01 in total). The rate-limit test
uses part of the server's per-IP daily allowance (about 15 asks); do not run it right before a presentation. Exit code 1 if any check FAILs.
"""

from __future__ import annotations

import argparse
import csv
import http.client
import json
import random
import re
import statistics
import struct
import sys
import time
import urllib.parse
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PRIMARY, ESCALATION = "anthropic/claude-haiku-5.5", "anthropic/claude-sonnet-5.5"
CHALLENGE_SAMPLE = ["T2-001", "T2-016", "T2-017", "T2-020", "T2-031"]
KEYLIKE = [re.compile(p) for p in (r"sk-or-[A-Za-z0-9_\-]{6,}", r"sk-[A-Za-z0-9]{20,}", r"(?i)bearer\s+[A-Za-z0-9._\-]{16,}",
                                   r"(?i)openrouter[_-]?(api[_-]?)?key\s*[=:]\s*\S{8,}", r"(?i)\bapi[_-]?key[\"']?\s*[=:]\s*[\"']?[A-Za-z0-9_\-]{16,}")]
TRACEBACK = re.compile(r"Traceback \(most recent|File \"[^\"]+\.py\"|\.py\", line \d+|site-packages|raise \w+Error")
VAGUE = "What happened?"


class Resp:
    def __init__(self, status, headers, body, elapsed):
        self.status, self.headers, self.body, self.elapsed = status, headers, body, elapsed

    def json(self):
        return json.loads(self.body.decode("utf-8"))

    @property
    def text(self):
        return self.body.decode("utf-8", "replace")


class Client:
    """One fresh connection per request (so every latency includes TLS, like a first visit). Every response is scanned for key-like text."""

    def __init__(self, base: str, timeout: float = 120.0):
        u = urllib.parse.urlparse(base.rstrip("/"))
        self.scheme, self.host, self.port = u.scheme, u.hostname, u.port
        self.timeout, self.hits, self.n_responses = timeout, [], 0
        self.ask_times: list[float] = []

    def _conn(self):
        cls = http.client.HTTPSConnection if self.scheme == "https" else http.client.HTTPConnection
        return cls(self.host, self.port, timeout=self.timeout)

    def scan(self, label: str, headers: dict, body: bytes) -> None:
        self.n_responses += 1
        blob = "\n".join(f"{k}: {v}" for k, v in headers.items()) + "\n" + body.decode("latin-1")
        for rx in KEYLIKE:
            m = rx.search(blob)
            if m:
                self.hits.append(f"{label}: matches /{rx.pattern[:30]}/")      # the match itself is never stored or printed

    def request(self, method, path, body=None, headers=None, raw: bytes | None = None) -> Resp:
        h = {"User-Agent": "smoke-remote/1", "Accept": "*/*", **(headers or {})}
        data = raw
        if body is not None:
            data = json.dumps(body).encode()
            h.setdefault("Content-Type", "application/json")
        t0 = time.perf_counter()
        c = self._conn()
        try:
            c.request(method, path, body=data, headers=h)
            r = c.getresponse()
            payload = r.read()
            hdrs = {k.lower(): v for k, v in r.getheaders()}
            resp = Resp(r.status, hdrs, payload, time.perf_counter() - t0)
        finally:
            c.close()
        self.scan(f"{method} {path[:50]}", resp.headers, resp.body)
        return resp

    def ask(self, question, path="/ask", headers=None, tag="ask") -> Resp:
        """POST /ask paced to stay inside the 6-per-minute window; one retry after a 429 (reported by the caller via .retried)."""
        now = time.time()
        self.ask_times = [t for t in self.ask_times if now - t < 61]
        if len(self.ask_times) >= 6:
            time.sleep(61 - (now - self.ask_times[0]))
        r = self.request("POST", path, {"question": question}, headers)
        self.ask_times.append(time.time())
        r.retried = False
        if r.status == 429:
            wait = min(65, int(r.headers.get("retry-after", "30")) + 1)
            time.sleep(wait)
            r = self.request("POST", path, {"question": question}, headers)
            self.ask_times.append(time.time())
            r.retried = True
        return r


ROWS: list[tuple[str, str, str, str]] = []
COST = {"incurred": 0.0}


def row(cid: str, name: str, status: str, detail: str) -> None:
    ROWS.append((cid, name, status, detail))
    print(f"[{status:<4}] {cid:>3} {name}: {detail}", flush=True)


def check(cid, name):
    """Decorator: run a check, turn an exception into a FAIL row."""
    def deco(fn):
        def run(*a, **k):
            try:
                return fn(*a, **k)
            except Exception as e:  # noqa: BLE001
                row(cid, name, "FAIL", f"check crashed: {type(e).__name__}: {str(e)[:160]}")
        run.__name__ = fn.__name__
        return run
    return deco


def missing(obj, keys):
    return [k for k in keys if not isinstance(obj, dict) or k not in obj]


def png_size(data: bytes):
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", data[16:24])


# ------------------------------------------------------------------ the checks


def c1_latency(c: Client, state):
    t0 = time.perf_counter()
    r = None
    for attempt in range(8):                       # a sleeping Render instance may answer 502/503 while it wakes
        r = c.request("GET", "/health")
        if r.status == 200:
            break
        time.sleep(5)
    first = time.perf_counter() - t0
    warm = []
    for _ in range(5):
        warm.append(c.request("GET", "/health").elapsed)
    state["health"] = r.json() if r.status == 200 else {}
    note = ("looks like a wake from sleep" if first > 5 else "instance was already awake (a cold start cannot be shown if something woke it first)")
    row("1", "latency", "PASS" if r.status == 200 and statistics.median(warm) < 1.5 else "FAIL",
        f"first request {first:.2f}s ({note}); warm /health median {statistics.median(warm) * 1000:.0f} ms, worst {max(warm) * 1000:.0f} ms (5 requests, new TLS connection each)")
    state["latency"] = {"first_s": round(first, 2), "median_ms": round(statistics.median(warm) * 1000), "worst_ms": round(max(warm) * 1000)}


TRACE_KEYS = {"router", "contexts", "model_calls", "verifier", "retries", "escalations", "second_pass", "arbitration", "cited", "decisions", "warnings", "totals", "events"}
DETAIL_KEYS = ["id", "set", "question", "status", "answer", "rationale", "confidence", "verified", "flags", "router_mode", "source", "evidence", "cited_records", "clarification", "trace"]


@check("2", "GET endpoints and shapes")
def c2_get_endpoints(c: Client, state, unseen_id_hint):
    problems, ok = [], []

    def get(path):
        r = c.request("GET", path)
        if r.status != 200:
            problems.append(f"{path} -> {r.status}")
            return None
        return r

    h = get("/health")
    if h:
        m = missing(h.json(), ["status", "live_mode", "models", "version", "attribution", "budget_remaining_usd", "details"])
        (problems.append(f"/health missing {m}") if m else ok.append("/health"))
    q = get("/questions")
    qs = q.json() if q else {}
    if q:
        bad = [k for k in qs.get("questions", []) if missing(k, ["id", "set", "question", "status", "confidence", "flags", "router_mode"])]
        if qs.get("count") != 72 or qs.get("sets") != {"challenge": 32, "unseen": 40} or bad:
            problems.append(f"/questions count={qs.get('count')} sets={qs.get('sets')} badrows={len(bad)}")
        else:
            ok.append("/questions(72=32+40)")
    state["questions"] = qs
    unseen = next((x["id"] for x in qs.get("questions", []) if x["set"] == "unseen"), unseen_id_hint)
    for qid in CHALLENGE_SAMPLE + [unseen]:
        r = get(f"/questions/{qid}")
        if r:
            d = r.json()
            m = missing(d, DETAIL_KEYS) + [f"trace.{k}" for k in TRACE_KEYS - set(d.get("trace", {}))]
            (problems.append(f"/questions/{qid} missing {m}") if m else ok.append(qid))
    for path, keys in (("/archive", ["wells", "wellbores", "reports", "record_counts", "attribution"]), ("/trajectories", ["method", "approximate", "caveats", "wellbores"]),
                       ("/costs", ["ledger", "per_question", "model_mix", "cache_hit_rate", "budget"]), ("/generalisation", ["available", "summary", "questions", "attribution"])):
        r = get(path)
        if not r:
            continue
        d = r.json()
        m = missing(d, keys)
        extra = ""
        if path == "/archive" and len(d.get("reports", [])) != 32:
            m.append("32 reports")
        if path == "/trajectories":
            st = {w["status"] for w in d.get("wellbores", [])}
            if st != {"ok", "skipped"}:
                m.append(f"statuses {st}")
        if path == "/generalisation" and (not d.get("available") or len(d.get("questions", [])) != 40):
            m.append("40 unseen results")
        (problems.append(f"{path} missing {m}") if m else ok.append(path))
    row("2", "GET endpoints/shapes", "FAIL" if problems else "PASS", ("; ".join(problems) if problems else f"{len(ok)} endpoints/ids OK: " + ", ".join(ok)))
    state["unseen_id"] = unseen


@check("2b", "page images and boxes")
def c2b_pages(c: Client, state):
    d = state["details"]
    printed = next((rec for qid in sorted(d) for rec in d[qid]["cited_records"] if rec["evidence"]["kind"] == "pdf"), None)
    xml_only = next((rec for qid in sorted(d) for rec in d[qid]["cited_records"] if rec["evidence"]["kind"] == "xml_only"), None)
    problems = []
    rid = printed["id"]
    b = c.request("GET", f"/pages/{rid}/boxes")
    bj = b.json() if b.status == 200 else {}
    if b.status != 200 or missing(bj, ["page", "page_width", "page_height", "boxes", "match", "png_url"]) or not bj.get("boxes"):
        problems.append(f"boxes {b.status} {missing(bj, ['boxes'])}")
    sizes = {}
    for z in (1.0, 1.5, 2.0):
        r = c.request("GET", f"/pages/{rid}.png?zoom={z}")
        sz = png_size(r.body) if r.status == 200 and r.headers.get("content-type", "").startswith("image/png") else None
        sizes[z] = sz
        if sz is None or r.elapsed > 30 or len(r.body) < 20_000:
            problems.append(f"png zoom {z}: status {r.status}, type {r.headers.get('content-type')}, {len(r.body)} B")
        elif bj and (abs(sz[0] - bj["page_width"] * z) > 2 or abs(sz[1] - bj["page_height"] * z) > 2):
            problems.append(f"png zoom {z} is {sz}, expected about {bj['page_width'] * z:.0f}x{bj['page_height'] * z:.0f}")
    plain = c.request("GET", f"/pages/{rid}.png?highlight=false")
    hl = c.request("GET", f"/pages/{rid}.png")
    if plain.body == hl.body:
        problems.append("highlight=false returns the same image as the highlighted one")
    detail = f"record {rid}: boxes {len(bj.get('boxes', []))} (match {bj.get('match')}), PNG sizes {sizes}"
    row("2b", "page images + boxes", "FAIL" if problems else "PASS", "; ".join(problems) or detail)
    if not xml_only:       # no cited record is XML-only: look through the status/wellbore records of a question's context
        ctx = d["T2-001"]["trace"]["contexts"][0]["records"]
        for rec in [x for x in ctx if x["type"] in ("status", "wellbore", "header")][:60]:
            r = c.request("GET", f"/pages/{rec['id']}/boxes")
            if r.status == 404 and r.json().get("detail", {}).get("code") == "xml_only":
                xml_only = {"id": rec["id"]}
                break
    if xml_only:
        r1, r2 = c.request("GET", f"/pages/{xml_only['id']}.png"), c.request("GET", f"/pages/{xml_only['id']}/boxes")
        ok = all(r.status == 404 and r.json().get("detail", {}).get("code") == "xml_only" for r in (r1, r2))
        row("2c", "404 xml_only", "PASS" if ok else "FAIL", f"record {xml_only['id']}: png {r1.status}, boxes {r2.status}, code {r1.json().get('detail', {}).get('code') if r1.status == 404 else '-'}, "
            f"message {r1.json().get('detail', {}).get('message', '')[:70]!r}")
    else:
        row("2c", "404 xml_only", "FAIL", "no XML-only record found to test with")


@check("3", "parity with predictions.csv")
def c3_parity(c: Client, state, predictions: Path):
    with predictions.open(encoding="utf-8", newline="") as f:
        pred = {r["question_id"]: r for r in csv.DictReader(f)}
    answers_json = predictions.parent / "indexes" / "answers.json"
    statuses = {a["question_id"]: a["status"] for a in json.loads(answers_json.read_text(encoding="utf-8"))} if answers_json.exists() else {}
    details, diffs = {}, []
    state["questions"] = c.request("GET", "/questions").json()
    listed = {x["id"]: x for x in state["questions"].get("questions", [])}
    for qid, p in pred.items():
        r = c.request("GET", f"/questions/{qid}")
        if r.status != 200:
            diffs.append(f"{qid}: HTTP {r.status}")
            continue
        d = r.json()
        details[qid] = d
        notes = re.sub(r"\s+", " ", re.sub(r"^EARLY ABSTAIN:\s*", "", d["rationale"] or "")).strip()
        for name, a, b in (("answer", d["answer"], p["answer"]), ("evidence", d["evidence"], p["evidence"]), ("confidence", f"{d['confidence']:.2f}", p["confidence"]),
                           ("notes", notes, p["notes"]), ("status", d["status"], statuses.get(qid, d["status"])), ("list-status", listed.get(qid, {}).get("status"), d["status"])):
            if a != b:
                diffs.append(f"{qid}.{name}")
    state["details"] = details
    row("3", "parity (32 challenge answers)", "FAIL" if diffs or len(pred) != 32 else "PASS",
        (f"{len(diffs)} differences: {diffs[:6]}" if diffs else f"all {len(pred)} answers, evidence, confidences and notes equal predictions.csv"
         f"{'; statuses equal answers.json' if statuses else '; statuses not compared (answers.json absent locally)'}") + f"; /questions has {state['questions'].get('count')} items")


@check("4", "health + key hygiene")
def c4_health(c: Client, state, args):
    h = state["health"]
    problems = []
    if h.get("live_mode") is not True:
        problems.append(f"live_mode={h.get('live_mode')} (key missing, or budget used up?)")
    if h.get("models") != {"primary": args.primary, "escalation": args.escalation}:
        problems.append(f"models={h.get('models')}")
    if "budget_remaining_usd" not in h or not isinstance(h["budget_remaining_usd"], (int, float)):
        problems.append("budget_remaining_usd missing")
    if h.get("attribution") != "Data: Equinor Volve dataset":
        problems.append(f"attribution={h.get('attribution')!r}")
    state["_c4"] = (problems, h)


def c4_final(c: Client, state):
    problems, h = state.pop("_c4", ([], {}))
    if c.hits:
        problems.append(f"KEY-LIKE TEXT in {len(c.hits)} response(s): {c.hits[:3]}")
    row("4", "health fields + no key-like text", "FAIL" if problems else "PASS",
        "; ".join(problems) or f"live_mode true, models ok, budget ${h.get('budget_remaining_usd')}, attribution ok; {c.n_responses} responses (bodies+headers) scanned, none key-like")


def tokens_ok(d, live: bool):
    calls = d["trace"]["model_calls"]
    live_calls = [m for m in calls if m["outcome"] == "live"]
    return bool(live_calls) and all(m["tokens_source"] == "provider_reported" and (m["prompt_tokens"] or 0) > 0 and (m["completion_tokens"] or 0) > 0
                                    and m["cost_usd"] > 0 for m in live_calls)


@check("5", "ask cached")
def c5_cached(c: Client, state):
    q = state["details"]["T2-001"]["question"]
    r = c.ask(q)
    d = r.json()
    t = d["trace"]["totals"]
    ok = r.status == 200 and d["source"] == "cache" and t["live_calls"] == 0 and t["incurred_cost_usd"] == 0 and d["status"] == "answered" and d["id"] == "T2-001"
    row("5", "POST /ask cached T2-001", "PASS" if ok else "FAIL",
        f"HTTP {r.status}, status {d.get('status')}, source {d.get('source')}, live calls {t['live_calls']}, incurred ${t['incurred_cost_usd']}, answer {d['answer'][:30]!r}, {r.elapsed * 1000:.0f} ms")
    COST["incurred"] += t["incurred_cost_usd"]


def pick_reports(state, c: Client, n=3):
    a = c.request("GET", "/archive").json()
    rng = random.Random(state["seed"])
    reps = rng.sample(a["reports"], n)
    return [(r["wellbore"], r["date"]) for r in reps]


@check("6", "ask new questions live")
def c6_live(c: Client, state, args):
    if args.no_live:
        row("6", "POST /ask new (live)", "SKIP", "--no-live")
        return
    (w1, d1), (w2, d2), (w3, d3) = pick_reports(state, c)
    state["stream_q"] = f"What is the rig name in the {w3} report dated {d3}?"
    qa = f"Who is listed as the operator in the {w1} report dated {d1}?"
    qb = f"What was the wave height in the {w2} report dated {d2}?"
    out = []
    for label, q, want in (("answerable", qa, "answered"), ("absent field", qb, "abstain")):
        if COST["incurred"] > args.max_cost - 0.01:
            row("6", f"live {label}", "SKIP", f"cost cap reached (${COST['incurred']:.4f})")
            continue
        r = c.ask(q)
        d = r.json()
        t = d["trace"]["totals"]
        COST["incurred"] += t["incurred_cost_usd"]
        was_cached = d["source"] == "cache"
        cites = [x for x in d["cited_records"] if x["evidence"]["kind"] != "absent"]
        status_ok = d["status"] == want and (want != "answered" or (cites and d["verified"])) and (want != "abstain" or any(x["evidence"]["kind"] == "absent" for x in d["cited_records"]))
        tok = tokens_ok(d, True) if not was_cached else True
        ok = r.status == 200 and status_ok and tok and (d["source"] in ("live", "mixed") or was_cached)
        out.append((label, ok, d, q, r))
        row("6", f"live {label}", "PASS" if ok else "FAIL",
            f"HTTP {r.status} {r.elapsed:.1f}s, status {d['status']} (wanted {want}), source {d['source']}"
            f"{' (already in the runtime cache from an earlier run: new text each run is not guaranteed)' if was_cached else ''}, "
            f"calls {[(m['model'].split('/')[-1], m['outcome'], m['prompt_tokens'], m['completion_tokens'], m['tokens_source']) for m in d['trace']['model_calls']][:3]}, "
            f"generation cost ${t['generation_cost_usd']:.5f}, incurred ${t['incurred_cost_usd']:.5f}, answer {d['answer'][:50]!r}")
    if out:
        label, ok, d, q, r = out[0]
        r2 = c.ask(q)
        d2 = r2.json()
        t2 = d2["trace"]["totals"]
        COST["incurred"] += t2["incurred_cost_usd"]
        ok2 = r2.status == 200 and d2["source"] == "cache" and t2["live_calls"] == 0 and t2["incurred_cost_usd"] == 0 and d2["answer"] == d["answer"]
        row("6b", "same question again", "PASS" if ok2 else "FAIL",
            f"source {d2.get('source')}, live calls {t2['live_calls']}, incurred ${t2['incurred_cost_usd']}, same answer {d2['answer'] == d['answer']}, {r2.elapsed * 1000:.0f} ms")


@check("7", "vague question")
def c7_vague(c: Client, state):
    r = c.ask(VAGUE)
    d = r.json()
    ok = (r.status == 200 and "needs_clarification" in d["flags"] and d["trace"]["model_calls"] == [] and d["trace"]["totals"]["incurred_cost_usd"] == 0
          and len(d["clarification"]["examples"]) == 3 and d["status"] == "abstain")
    row("7", "vague -> needs_clarification", "PASS" if ok else "FAIL",
        f"HTTP {r.status}, flags {d.get('flags')}, model calls {len(d['trace']['model_calls'])}, examples {len((d.get('clarification') or {}).get('examples', []))}")


def parse_sse(buf: str):
    out = []
    for block in buf.split("\n\n"):
        if block.strip() and not block.startswith(":"):
            f = dict(line.split(": ", 1) for line in block.split("\n") if ": " in line)
            if "event" in f:
                out.append((f["event"], f.get("data", "")))
    return out


@check("8", "SSE streaming")
def c8_stream(c: Client, state, args):
    live = not args.no_live
    q = state.get("stream_q") if live else VAGUE
    if COST["incurred"] > args.max_cost - 0.01:
        row("8", "POST /ask/stream", "SKIP", "cost cap reached")
        return
    now = time.time()
    c.ask_times = [t for t in c.ask_times if now - t < 61]
    if len(c.ask_times) >= 6:
        time.sleep(61 - (now - c.ask_times[0]))
    conn = c._conn()
    t0 = time.perf_counter()
    conn.request("POST", "/ask/stream", body=json.dumps({"question": q}), headers={"Content-Type": "application/json", "Accept": "text/event-stream", "User-Agent": "smoke-remote/1"})
    resp = conn.getresponse()
    c.ask_times.append(time.time())
    hdrs = {k.lower(): v for k, v in resp.getheaders()}
    events, buf, first_byte = [], "", None
    while True:
        chunk = resp.read1(65536)
        if not chunk:
            break
        if first_byte is None:
            first_byte = time.perf_counter() - t0
        buf += chunk.decode("utf-8", "replace")
        while "\n\n" in buf:
            block, buf = buf.split("\n\n", 1)
            for name, data in parse_sse(block + "\n\n"):
                events.append((name, time.perf_counter() - t0, data))
    conn.close()
    c.scan("POST /ask/stream", hdrs, "".join(d for _, _, d in events).encode("utf-8", "replace"))
    names = [n for n, _, _ in events]
    arrivals = [round(t, 2) for _, t, _ in events]
    server_t = []
    for n, _, data in events:
        if n not in ("result", "error"):
            try:
                server_t.append(json.loads(data)["t_ms"] / 1000)
            except (ValueError, KeyError):
                pass
    result = next((json.loads(d) for n, _, d in events if n == "result"), None)
    if result:
        COST["incurred"] += result["trace"]["totals"]["incurred_cost_usd"]
    span_server = (max(server_t) if server_t else 0)
    # buffered = events that the server produced seconds apart arrive together
    pre = [t for n, t, _ in events if n != "result"]
    spread = (max(pre) - min(pre)) if len(pre) > 1 else 0
    final_gap = (events[-1][1] - max(pre)) if pre else 0
    buffered = bool(live and span_server > 0.5 and spread < 0.35 * span_server)
    ok_events = names[:1] == ["route"] and names[-1:] == ["result"] and resp.status == 200 and hdrs.get("content-type", "").startswith("text/event-stream")
    notes = [f"HTTP {resp.status}", f"first byte {first_byte:.2f}s" if first_byte is not None else "no data",
             "events (name@arrival s): " + ", ".join(f"{n}@{t:.2f}" for n, t, _ in events),
             f"server stages spanned {span_server:.2f}s, arrived spread {spread:.2f}s",
             f"headers: content-type={hdrs.get('content-type')}, cache-control={hdrs.get('cache-control')}, x-accel-buffering={hdrs.get('x-accel-buffering')}, "
             f"content-encoding={hdrs.get('content-encoding')}, transfer-encoding={hdrs.get('transfer-encoding')}"]
    if not live:
        notes.append("--no-live: a cached/vague stream has no slow stage, so incremental delivery cannot be demonstrated")
    status = "FAIL" if (not ok_events or buffered) else ("WARN" if not live or span_server <= 0.5 else "PASS")
    if buffered:
        notes.append("BUFFERED: events were produced over seconds but arrived together")
    row("8", "POST /ask/stream incremental", status, "; ".join(notes))
    state["stream_buffered"] = buffered


@check("9", "rate limit identification")
def c9_rate(c: Client, state, args):
    if not args.rate_limit_test:
        row("9", "rate limit behind proxy", "SKIP", "run with --rate-limit-test (uses ~15 asks of the daily allowance); code review result is in the report")
        return
    rnd = random.Random(time.time())
    x1, x2 = (f"203.0.113.{rnd.randint(1, 254)}", f"198.51.100.{rnd.randint(1, 254)}")     # TEST-NET addresses: documentation ranges, never real clients
    who = c.request("GET", "/whoami", headers={"X-Forwarded-For": x1})          # diagnostic: what the server sees for a spoofed header
    wj = who.json() if who.status == 200 else {}
    seen = wj.get("seen", {})
    who_txt = (f"/whoami with a spoofed X-Forwarded-For: source {wj.get('identity_source')}, XFF seen {seen.get('x-forwarded-for')!r}, "
               f"CF-Connecting-IP {'present' if seen.get('cf-connecting-ip') else 'absent'}, spoof used as key: {wj.get('bucket_key') == x1}") if wj else "/whoami unavailable"
    n1 = 0
    last = None
    for _ in range(8):
        r = c.request("POST", "/ask", {"question": VAGUE}, {"X-Forwarded-For": x1})
        c.ask_times.append(time.time())
        last = r
        if r.status == 429:
            break
        n1 += 1
    r2 = c.request("POST", "/ask", {"question": VAGUE}, {"X-Forwarded-For": x2})
    c.ask_times.append(time.time())
    prior = len([t for t in c.ask_times[:-(n1 + 2)] if time.time() - t < 60])
    if n1 >= 6 and r2.status == 200 or wj.get("bucket_key") == x1:
        verdict = ("SPOOFABLE: a fresh X-Forwarded-For value gives a fresh 6-per-minute bucket (the limiter keys on a client-controlled value)")
        status = "FAIL"
    elif r2.status == 429:
        verdict = (f"spoofed X-Forwarded-For ignored: {n1} of my probes passed (the minute already held ~{prior} of my earlier asks), a second spoof value was still refused, "
                   f"so one client = one bucket")
        status = "PASS"
    else:
        verdict = f"unclear: {n1} passed, then 429={last.status == 429}; second header status {r2.status}"
        status = "WARN"
    verdict += "; " + who_txt
    row("9", "rate limit client identity", status, verdict)
    state["xff_verdict"] = verdict
    # 7 in a minute, no header, after the window has cleared
    wait = max(0, 62 - (time.time() - max(c.ask_times)))
    time.sleep(wait)
    codes = []
    for _ in range(7):
        r = c.request("POST", "/ask", {"question": VAGUE})
        c.ask_times.append(time.time())
        codes.append(r.status)
    ra = r.headers.get("retry-after")
    body = r.json().get("detail", {}) if r.status == 429 else {}
    ok = codes == [200] * 6 + [429] and body.get("code") == "rate_limited" and ra is not None
    row("9b", "7 asks in a minute", "PASS" if ok else "FAIL", f"status codes {codes}; 429 body code {body.get('code')}, Retry-After {ra}s (uses ~7 of the daily allowance)")


@check("10", "CORS")
def c10_cors(c: Client, state, args):
    origins = ["http://localhost:5173", "http://localhost:3000", "https://well-archive-demo.vercel.app", "https://evil.example"] + args.origin
    seen = {}
    for o in dict.fromkeys(origins):
        g = c.request("GET", "/health", headers={"Origin": o})
        p = c.request("OPTIONS", "/ask", headers={"Origin": o, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
        seen[o] = (g.headers.get("access-control-allow-origin"), p.status, p.headers.get("access-control-allow-origin"), p.headers.get("access-control-allow-methods"))
    allowed = [o for o, v in seen.items() if v[0] in (o, "*") and v[2] in (o, "*")]
    ev = seen["https://evil.example"]
    problems = []
    if ev[0] in ("https://evil.example", "*"):
        problems.append("an arbitrary origin is allowed")
    for o in args.origin:
        if o not in allowed:
            problems.append(f"{o} is NOT allowed")
    row("10", "CORS", "FAIL" if problems else "PASS",
        f"allowed now: {allowed or 'none'}; denied: {[o for o in seen if o not in allowed]}; preflight status {ev[1]}; {'; '.join(problems) or 'ok'}. "
        f"ALLOWED_ORIGINS should be: http://localhost:5173 (dev) plus the exact Vercel origin (https://<project>.vercel.app, no trailing slash; add preview/custom domains if used)")


@check("11", "input guards")
def c11_guards(c: Client, state):
    problems, notes = [], []
    long_q = "What was the operator in the report for well F-11 B? " + "x" * 360
    r = c.request("POST", "/ask", {"question": long_q[:401]})
    notes.append(f"401 chars -> {r.status}")
    if r.status != 422 or r.json().get("detail", {}).get("code") != "question_too_long":
        problems.append(f"401-char question gave {r.status}")
    bodies = [r]
    r = c.request("POST", "/ask", raw=b'{"question": ', headers={"Content-Type": "application/json"})
    notes.append(f"malformed JSON -> {r.status}")
    bodies.append(r)
    if not 400 <= r.status < 500:
        problems.append(f"malformed JSON gave {r.status}")
    r = c.request("POST", "/ask", raw=b"question=hello", headers={"Content-Type": "application/x-www-form-urlencoded"})
    notes.append(f"wrong content-type -> {r.status}")
    bodies.append(r)
    if not 400 <= r.status < 500:
        problems.append(f"wrong content-type gave {r.status}")
    r = c.request("POST", "/ask", {"question": "   "})
    notes.append(f"blank question -> {r.status}")
    bodies.append(r)
    r = c.request("GET", "/questions/NOPE-999")
    notes.append(f"unknown id -> {r.status}")
    bodies.append(r)
    if r.status != 404 or r.json().get("detail", {}).get("code") != "unknown_question":
        problems.append(f"unknown id gave {r.status}")
    r = c.request("GET", "/no/such/path")
    notes.append(f"unknown path -> {r.status}")
    bodies.append(r)
    r = c.request("POST", "/ask/stream", {"question": "x" * 500})
    notes.append(f"stream 500 chars -> {r.status}")
    bodies.append(r)
    for b in bodies:
        if TRACEBACK.search(b.text):
            problems.append("a stack trace / source path appears in an error body")
    row("11", "input guards, clean errors", "FAIL" if problems else "PASS", "; ".join(problems) or "; ".join(notes) + "; no stack trace or source path in any error body")


@check("13", "security basics")
def c13_security(c: Client, state):
    notes, warns = [], []
    docs = c.request("GET", "/docs")
    notes.append(f"/docs {docs.status} (public Swagger UI: fine for a demo; /openapi.json {c.request('GET', '/openapi.json').status})")
    exposed = []
    for p in ("/.env", "/submission/predictions.csv", "/web/server/data/records.parquet", "/data/", "/static/", "/pages/", "/..%2f..%2fetc%2fpasswd", "/pages/..%2f..%2fetc%2fpasswd.png", "/.git/config"):
        r = c.request("GET", p)
        if r.status == 200 or re.search(r"Index of|<title>Directory", r.text):
            exposed.append(f"{p} -> {r.status}")
    if exposed:
        warns.append(f"EXPOSED: {exposed}")
    notes.append("no file or directory paths served" if not exposed else "")
    err = c.request("GET", "/no/such/path")
    debug = bool(TRACEBACK.search(err.text)) or "debug" in err.text.lower()
    notes.append(f"debug mode: {'ON?' if debug else 'off (404 body is just ' + err.text[:40] + ')'}")
    h = c.request("GET", "/health").headers
    want = ["strict-transport-security", "x-content-type-options", "x-frame-options", "content-security-policy", "referrer-policy"]
    have = [k for k in want if k in h]
    notes.append(f"server={h.get('server')}, via={h.get('via')}, present security headers {have}, missing {[k for k in want if k not in h]}")
    try:
        plain = http.client.HTTPConnection(c.host, 80, timeout=20)
        plain.request("GET", "/health")
        pr = plain.getresponse()
        notes.append(f"http:// -> {pr.status} (location {pr.getheader('location')})")
        plain.close()
    except OSError as e:
        notes.append(f"http:// not reachable ({type(e).__name__})")
    docs_html = c.request("GET", "/docs")
    csp = docs_html.headers.get("content-security-policy", "")
    hosts = set(re.findall(r"https://([^/\"')\s]+)", docs_html.text))
    blocked = [x for x in hosts if x not in csp]
    missing_h = [k for k in want if k not in h]
    if missing_h:
        warns.append(f"MISSING required headers {missing_h}")
    if docs_html.status != 200 or blocked:
        warns.append(f"/docs would break: status {docs_html.status}, hosts not allowed by its CSP {blocked}")
    if h.get("x-frame-options") != "DENY" or h.get("x-content-type-options") != "nosniff":
        warns.append("X-Frame-Options/X-Content-Type-Options not DENY/nosniff")
    notes.append(f"/docs CSP covers its {len(hosts)} external hosts" if not blocked else "")
    row("13", "security basics", "FAIL" if (exposed or debug or missing_h or blocked or docs_html.status != 200 or h.get("x-frame-options") != "DENY") else "PASS", "; ".join(n for n in notes if n) + ("; " + "; ".join(warns) if warns else ""))
    state["headers"] = h


# ------------------------------------------------------------------ main


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base_url")
    ap.add_argument("--predictions", type=Path, default=REPO / "submission" / "predictions.csv")
    ap.add_argument("--no-live", action="store_true", help="make no model call (live checks are skipped)")
    ap.add_argument("--rate-limit-test", action="store_true", help="X-Forwarded-For probes + 7-asks-in-a-minute test (uses daily allowance)")
    ap.add_argument("--max-cost", type=float, default=0.03, help="stop making live calls when this much has been spent (USD)")
    ap.add_argument("--origin", action="append", default=[], help="an origin that must be allowed (repeatable), e.g. the Vercel URL")
    ap.add_argument("--primary", default=PRIMARY)
    ap.add_argument("--escalation", default=ESCALATION)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--json", type=Path, help="also write the result rows to this file")
    args = ap.parse_args()
    c = Client(args.base_url)
    state: dict = {"seed": args.seed if args.seed is not None else int(time.time())}
    print(f"Smoke test of {args.base_url}  (live asks {'off' if args.no_live else 'on'}, cost cap ${args.max_cost})\n")

    c1_latency(c, state)
    budget_before = state["health"].get("budget_remaining_usd")
    c3_parity(c, state, args.predictions)                         # also loads the 32 details used by the next checks
    if not state.get("details"):
        print("parity could not load the answers; stopping")
        return 1
    c2_get_endpoints(c, state, "G-001")
    c2b_pages(c, state)
    c4_health(c, state, args)
    c5_cached(c, state)
    c6_live(c, state, args)
    c7_vague(c, state)
    c8_stream(c, state, args)
    c9_rate(c, state, args)
    c10_cors(c, state, args)
    c11_guards(c, state)
    c13_security(c, state)
    after = c.request("GET", "/health").json()
    budget_after = after.get("budget_remaining_usd")
    c4_final(c, state)
    delta = None if budget_before is None or budget_after is None else round(budget_before - budget_after, 6)
    cost_ok = COST["incurred"] <= args.max_cost and (delta is None or delta <= args.max_cost + 1e-6)
    row("12", "budget and spend", "PASS" if cost_ok else "FAIL",
        f"server budget remaining ${budget_before} -> ${budget_after} (delta ${delta}); live cost summed from the traces ${COST['incurred']:.6f}; cap ${args.max_cost}"
        + ("" if delta is None or abs(delta - COST["incurred"]) < 0.002 else "; NOTE: delta differs from the trace sum (other traffic, or the counter reset by a restart)"))

    order = {"1": 1, "2": 2, "2b": 3, "2c": 4, "3": 5, "4": 6, "5": 7, "6": 8, "6b": 9, "7": 10, "8": 11, "9": 12, "9b": 13, "10": 14, "11": 15, "12": 16, "13": 17}
    print("\n" + "=" * 100)
    print(f"{'#':<4}{'result':<7}check")
    for cid, name, st, detail in sorted(ROWS, key=lambda r: order.get(r[0], 99)):
        print(f"{cid:<4}{st:<7}{name}")
    fails = [r for r in ROWS if r[2] == "FAIL"]
    print(f"\nlatency: {state.get('latency')}")
    print(f"live cost this run: ${COST['incurred']:.6f}; budget ${budget_before} -> ${budget_after}")
    print(f"{len(fails)} FAIL, {sum(r[2] == 'WARN' for r in ROWS)} WARN, {sum(r[2] == 'PASS' for r in ROWS)} PASS, {sum(r[2] == 'SKIP' for r in ROWS)} SKIP")
    if args.json:
        args.json.write_text(json.dumps({"rows": ROWS, "latency": state.get("latency"), "cost": COST["incurred"], "budget": [budget_before, budget_after],
                                         "headers": state.get("headers")}, indent=1), encoding="utf-8")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
