"""Rate-limit client identity (never the leftmost X-Forwarded-For) and security headers on every response."""

import json
import re
import time

import pytest
from fastapi.testclient import TestClient

from submission.archive_qa.llm import FakeLLM
from web.server.app import create_app
from web.server.clientid import client_identity, identity_mode
from web.server.engine import Engine

from .conftest import make_settings, scripted_backend
from .test_ask import UNCACHED

Q = {"question": "What happened?"}            # costs nothing, still counts against the limiter


def make_client(tmp_path, **kw):
    e = Engine(make_settings(tmp_path, **kw))
    return e, TestClient(create_app(engine=e))


def codes(c, n, headers):
    return [c.post("/ask", json=Q, headers=headers(i) if callable(headers) else headers).status_code for i in range(n)]


# ------------------------------------------------------------------ identity: unit
def test_identity_order_and_validation():
    h = lambda **k: {key.replace("_", "-"): v for key, v in k.items()}          # noqa: E731
    assert client_identity(h(cf_connecting_ip="1.1.1.1", x_forwarded_for="2.2.2.2, 3.3.3.3"), "9.9.9.9", True) == ("1.1.1.1", "cf-connecting-ip")
    assert client_identity(h(x_forwarded_for="6.6.6.6, 3.3.3.3"), "9.9.9.9", True) == ("3.3.3.3", "x-forwarded-for")            # rightmost, not leftmost
    assert client_identity(h(x_forwarded_for="6.6.6.6, 3.3.3.3, 4.4.4.4"), "9.9.9.9", True, hops=2) == ("3.3.3.3", "x-forwarded-for")
    assert client_identity(h(x_forwarded_for="3.3.3.3"), "9.9.9.9", True, hops=2) == ("9.9.9.9", "client-address")             # fewer hops than trusted
    assert client_identity(h(cf_connecting_ip="not-an-ip", x_forwarded_for="x, 3.3.3.3"), "9.9.9.9", True)[0] == "3.3.3.3"       # junk skipped
    assert client_identity(h(cf_connecting_ip="1.1.1.1", x_forwarded_for="2.2.2.2"), "9.9.9.9", False) == ("9.9.9.9", "client-address")   # ignored
    assert client_identity({}, None, False) == ("unknown", "client-address")
    assert client_identity(h(cf_connecting_ip="2001:db8::1"), "9.9.9.9", True)[0] == "2001:db8::1"
    assert "TRUST_PROXY=0" in identity_mode(False, 1) and "1 from the right" in identity_mode(True, 1)


# ------------------------------------------------------------------ identity: through the app
def test_spoofed_x_forwarded_for_does_not_create_a_new_bucket(tmp_path):
    e, c = make_client(tmp_path, rate_per_min=3, trust_proxy=True)
    try:
        with c:   # the proxy appends the real address (9.9.9.9) on the right; the client controls only what is on the left
            got = codes(c, 5, lambda i: {"X-Forwarded-For": f"10.0.0.{i + 1}, 9.9.9.9"})
            assert got == [200, 200, 200, 429, 429]
            assert c.post("/ask", json=Q, headers={"X-Forwarded-For": "1.2.3.4, 9.9.9.9"}).status_code == 429
            assert c.post("/ask", json=Q, headers={"X-Forwarded-For": "1.2.3.4, 8.8.8.8"}).status_code == 200      # a different real client
    finally:
        e.close()


def test_different_cf_connecting_ip_is_a_different_bucket_and_beats_xff(tmp_path):
    e, c = make_client(tmp_path, rate_per_min=2, trust_proxy=True)
    try:
        with c:
            same_xff = {"X-Forwarded-For": "5.5.5.5, 9.9.9.9"}
            assert codes(c, 3, {**same_xff, "CF-Connecting-IP": "1.1.1.1"}) == [200, 200, 429]
            assert c.post("/ask", json=Q, headers={**same_xff, "CF-Connecting-IP": "1.1.1.2"}).status_code == 200      # new bucket
            assert c.post("/ask", json=Q, headers={"X-Forwarded-For": "7.7.7.7, 6.6.6.6", "CF-Connecting-IP": "1.1.1.1"}).status_code == 429   # CF wins
    finally:
        e.close()


def test_proxy_headers_are_ignored_when_the_proxy_is_not_trusted(tmp_path):
    e, c = make_client(tmp_path, rate_per_min=2, trust_proxy=False)
    try:
        with c:
            got = codes(c, 4, lambda i: {"CF-Connecting-IP": f"1.1.1.{i + 1}", "X-Forwarded-For": f"2.2.2.{i + 1}, 3.3.3.3"})
            assert got == [200, 200, 429, 429]
    finally:
        e.close()


def test_hop_count_is_configurable(tmp_path):
    e, c = make_client(tmp_path, rate_per_min=1, trust_proxy=True, trusted_proxy_hops=2)
    try:
        with c:
            # two trusted hops: the client address is the second entry from the right
            assert c.post("/ask", json=Q, headers={"X-Forwarded-For": "spoof, 4.4.4.4, 9.9.9.9"}).status_code == 200
            assert c.post("/ask", json=Q, headers={"X-Forwarded-For": "other, 4.4.4.4, 9.9.9.9"}).status_code == 429
    finally:
        e.close()


def test_health_reports_the_mode_but_no_address(tmp_path):
    e, c = make_client(tmp_path, trust_proxy=True)
    try:
        with c:
            c.post("/ask", json=Q, headers={"CF-Connecting-IP": "203.0.113.77", "X-Forwarded-For": "198.51.100.5, 192.0.2.9"})
            raw = c.get("/health").text
            ci = json.loads(raw)["details"]["rate_limit"]["client_identity"]
            assert ci["trust_proxy"] is True and ci["trusted_proxy_hops"] == 1 and "CF-Connecting-IP" in ci["mode"]
            assert ci["sources_used_since_start"] == {"cf-connecting-ip": 1}
            assert not re.search(r"\b(203\.0\.113\.77|198\.51\.100\.5|192\.0\.2\.9)\b", raw)
    finally:
        e.close()


def test_whoami_echoes_what_the_server_sees(tmp_path):
    e, c = make_client(tmp_path, trust_proxy=True)
    try:
        with c:
            d = c.get("/whoami", headers={"CF-Connecting-IP": "203.0.113.5", "X-Forwarded-For": "6.6.6.6, 203.0.113.5"}).json()
            assert d["identity_source"] == "cf-connecting-ip" and d["bucket_key"] == "203.0.113.5"
            assert d["seen"]["x-forwarded-for"] == "6.6.6.6, 203.0.113.5" and d["seen"]["cf-connecting-ip"] == "203.0.113.5"
    finally:
        e.close()


# ------------------------------------------------------------------ security headers
REQUIRED = ["strict-transport-security", "x-content-type-options", "x-frame-options", "referrer-policy", "content-security-policy"]


def assert_secure(r, docs=False):
    h = r.headers
    assert all(k in h for k in REQUIRED), (r.request.url.path, [k for k in REQUIRED if k not in h])
    assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"
    assert h["referrer-policy"] == "strict-origin-when-cross-origin" and "max-age=" in h["strict-transport-security"]
    assert ("cdn.jsdelivr.net" in h["content-security-policy"]) == docs
    assert "frame-ancestors 'none'" in h["content-security-policy"]


def test_headers_on_every_kind_of_response(client, engine):
    rid = "19A-19970829-ACT-04"
    for path in ("/health", "/questions", "/questions/T2-001", "/archive", "/trajectories", "/costs", "/generalisation", "/whoami", "/openapi.json",
                 f"/pages/{rid}.png", f"/pages/{rid}/boxes"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert_secure(r)
    for path, status in (("/questions/NOPE", 404), ("/no/such/path", 404), ("/pages/NOPE.png", 404)):
        r = client.get(path)
        assert r.status_code == status
        assert_secure(r)
    r = client.post("/ask", json={"question": "x" * 401})
    assert r.status_code == 422
    assert_secure(r)
    r = client.options("/ask", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
    assert_secure(r)
    assert client.get("/health").headers["x-data-attribution"] == "Data: Equinor Volve dataset"


def test_headers_on_429_and_500(tmp_path):
    e, c = make_client(tmp_path, rate_per_min=1)
    try:
        app = c.app

        @app.get("/boom")
        def boom():
            raise RuntimeError("secret internal detail")
        with TestClient(app, raise_server_exceptions=False) as t:
            t.post("/ask", json=Q)
            r = t.post("/ask", json=Q)
            assert r.status_code == 429
            assert_secure(r)
            r = t.get("/boom")
            assert r.status_code == 500 and "secret internal detail" not in r.text and r.json()["detail"]["code"] == "internal_error"
            assert_secure(r)
    finally:
        e.close()


def test_docs_still_load_and_the_csp_allows_what_they_load(client):
    for path in ("/docs", "/redoc"):
        r = client.get(path)
        assert r.status_code == 200 and "text/html" in r.headers["content-type"]
        assert_secure(r, docs=True)
        csp = r.headers["content-security-policy"]
        hosts = set(re.findall(r"https://([^/\"')\s]+)", r.text))
        assert hosts, path
        for host in hosts:
            assert host in csp, f"{path} loads {host} but the CSP does not allow it"
        if path == "/docs":
            assert "'unsafe-inline'" in csp          # Swagger UI's bootstrap is an inline script
    assert client.get("/openapi.json").status_code == 200


def test_sse_still_streams_incrementally_with_the_headers(tmp_path):
    def slow(system, user, model, max_tokens=None):
        time.sleep(0.6)
        return scripted_backend().script(system, user, model, max_tokens)
    e = Engine(make_settings(tmp_path), backend=FakeLLM(slow, tokens=(100, 20), cost=0.001))
    try:
        with TestClient(create_app(engine=e)) as c:
            t0, arrivals, names = time.perf_counter(), [], []
            with c.stream("POST", "/ask/stream", json={"question": UNCACHED}) as r:
                assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
                assert_secure(r)
                for line in r.iter_lines():
                    if line.startswith("event: "):
                        names.append(line[7:])
                        arrivals.append(time.perf_counter() - t0)
            assert names[0] == "route" and names[-1] == "result" and "model_call" in names
            assert arrivals[-1] - arrivals[0] > 0.9, arrivals           # produced over ~1.2 s and delivered over that time, not at the end
            assert arrivals[names.index("model_call")] < arrivals[-1] - 0.3
    finally:
        e.close()
