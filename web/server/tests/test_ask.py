"""POST /ask: cached answers offline, NOT EVALUATED for uncached without a key, honest abstentions, guards."""

import json

import pytest
from fastapi.testclient import TestClient

from submission.archive_qa import config
from web.server.app import create_app
from web.server.engine import Engine
from web.server.schemas import QuestionDetail

from .conftest import frozen_hashes, make_settings, scripted_backend

UNCACHED = "What was the operator in the 15/9-F-11-B report dated 2013-06-28?"
UNCACHED2 = "Which company was the operator in the 15/9-F-11-B report dated 2013-06-28?"


def test_cached_question_returns_cached_answer_without_key(client):
    committed = {a["question_id"]: a for a in json.loads(config.ANSWERS_PATH.read_text(encoding="utf-8"))}
    q = client.get("/questions/T2-001").json()
    r = client.post("/ask", json={"question": q["question"]})
    assert r.status_code == 200
    d = r.json()
    QuestionDetail.model_validate(d)
    assert d["id"] == "T2-001" and d["set"] == "challenge" and d["source"] == "cache"
    assert d["answer"] == committed["T2-001"]["answer"] and d["trace"]["totals"]["live_calls"] == 0
    assert d["trace"]["totals"]["cache_hits"] >= 1 and d["trace"]["totals"]["incurred_cost_usd"] == 0


def test_uncached_without_key_is_not_evaluated(client):
    d = client.post("/ask", json={"question": UNCACHED}).json()
    assert d["status"] == "not_evaluated" and d["confidence"] == 0.0
    assert d["answer"].startswith("NOT EVALUATED") and d["cited_records"] == [] and d["evidence"] == ""
    assert "not_evaluated" in d["flags"] and d["source"] == "none"
    calls = d["trace"]["model_calls"]
    assert calls and calls[-1]["outcome"] == "cache_miss_offline" and calls[-1]["prompt_tokens"] == 0     # a lookup, not a model call
    assert d["trace"]["totals"]["live_calls"] == 0 and d["trace"]["router"]["mode"] == "single_report"


def test_nonexistent_well_and_date_abstain_without_model(client):
    for q in ("What was the measured depth in the report for well F-99 on 2013-08-12?",
              "Who was the operator in the 15/9-F-1-C report dated 2031-01-01?"):
        d = client.post("/ask", json={"question": q}).json()
        assert d["status"] == "abstain" and "early_abstain" in d["flags"] and d["trace"]["model_calls"] == []
        assert d["trace"]["router"]["early_abstain"] and d["cited_records"] == []
        assert [e["stage"] for e in d["trace"]["events"]] == ["route", "result"]


def test_unmappable_question_is_an_honest_abstain_with_trace(client):
    d = client.post("/ask", json={"question": "What is the capital of France?"}).json()
    assert d["status"] == "abstain" and "router_unmapped" in d["flags"] and d["trace"]["model_calls"] == []
    assert d["trace"]["router"]["gate"] == "router_unmapped" and d["trace"]["router"]["confidence"]["level"] == "low"
    assert [e["stage"] for e in d["trace"]["events"]] == ["route", "gate", "result"]


def test_gate_never_overrides_a_cached_answer(engine):
    """Every cataloged question (incl. archive-wide meta questions with no topic words) keeps its cached answer."""
    gated = [c["id"] for c in engine.catalog if "router_unmapped" in engine.replayed(c["id"]).flags]
    assert gated == []


def test_validation_errors(client):
    r = client.post("/ask", json={"question": "x" * 401})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "question_too_long"
    assert client.post("/ask", json={"question": "   "}).status_code == 422
    assert client.post("/ask", json={}).json()["detail"]["code"] == "validation_error"


def test_ask_persists_and_get_by_id(client):
    d = client.post("/ask", json={"question": UNCACHED}).json()
    assert d["id"].startswith("ASK-")
    again = client.get(f"/questions/{d['id']}")
    assert again.status_code == 200 and again.json()["answer"] == d["answer"]


def test_rate_limit(tmp_path):
    e = Engine(make_settings(tmp_path, rate_per_min=3))
    try:
        with TestClient(create_app(engine=e)) as c:
            codes = [c.post("/ask", json={"question": "What is the capital of France?"}).status_code for _ in range(5)]
            assert codes == [200, 200, 200, 429, 429]
            r = c.post("/ask", json={"question": "What is the capital of France?"})
            assert r.json()["detail"]["code"] == "rate_limited" and int(r.headers["retry-after"]) >= 1
    finally:
        e.close()


def test_daily_rate_limit():
    from web.server.guards import RateLimited, RateLimiter
    t = [1000.0]
    rl = RateLimiter(100, 3, clock=lambda: t[0])
    for _ in range(3):
        rl.check("ip")
    with pytest.raises(RateLimited):
        rl.check("ip")
    rl.check("other-ip")
    t[0] += 86401
    rl.check("ip")


def test_live_ask_with_scripted_model_and_spend_guard(tmp_path):
    e = Engine(make_settings(tmp_path, server_budget_usd=0.0015), backend=scripted_backend())
    try:
        with TestClient(create_app(engine=e)) as c:
            h0 = c.get("/health").json()
            assert h0["live_mode"] is True
            d = c.post("/ask", json={"question": UNCACHED}).json()
            assert d["source"] == "live" and d["status"] == "answered" and d["answer"] == "Statoil" and d["verified"]
            t = d["trace"]["totals"]
            assert t["live_calls"] == 2 and t["incurred_cost_usd"] == pytest.approx(0.002)       # run 1 + run 2, no escalation
            assert c.get("/health").json()["budget_remaining_usd"] == 0 and c.get("/health").json()["live_mode"] is False
            # budget used up: an uncached question is refused with a clear message, a cached one still works
            r = c.post("/ask", json={"question": UNCACHED2})
            assert r.status_code == 503 and r.json()["detail"]["code"] == "budget_exhausted"
            # the same question again is now in the RUNTIME cache and costs nothing
            again = c.post("/ask", json={"question": UNCACHED}).json()
            assert again["source"] == "cache" and again["answer"] == "Statoil"
            q = c.get("/questions/T2-001").json()["question"]
            assert c.post("/ask", json={"question": q}).status_code == 200
    finally:
        e.close()


def test_provider_fallback_warning_surfaces_in_trace(tmp_path):
    import logging
    from submission.archive_qa.llm import FakeLLM

    class Falling(FakeLLM):
        def chat(self, *a, **k):
            logging.getLogger("archive_qa.llm").warning("pinned provider %s is unavailable for this key (HTTP 404); falling back", ["Anthropic"])
            self._pin_disabled = True
            return super().chat(*a, **k)

    inner = scripted_backend()
    fb = Falling(inner.script, tokens=inner.tokens, cost=inner.cost)
    e = Engine(make_settings(tmp_path), backend=fb)
    try:
        d = e.ask(UNCACHED)
        assert [w["code"] for w in d.trace.warnings] == ["provider_fallback"] and "provider_fallback" in d.flags
        assert any(ev.stage == "warning" for ev in d.trace.events)
        assert e.provider_fallback_active
    finally:
        e.close()
