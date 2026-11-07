"""POST /ask/stream: the SSE stages are exactly the stages that happened (they ARE the final trace's events)."""

import json

import pytest

from web.server.schemas import QuestionDetail

from .test_ask import UNCACHED

MULTI_PART = "What was the operator in the 15/9-F-11-B report dated 2013-06-28? Answer briefly."     # makes the verifier escalate


def sse(client, question):
    events = []
    with client.stream("POST", "/ask/stream", json={"question": question}) as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        buf = ""
        for chunk in r.iter_text():
            buf += chunk
        for block in buf.split("\n\n"):
            if not block.strip() or block.startswith(":"):
                continue
            ev = dict(line.split(": ", 1) for line in block.split("\n") if ": " in line)
            events.append((ev["event"], json.loads(ev["data"])))
    return events


def check_stream_is_the_trace(events):
    assert events[-1][0] == "result"
    detail = QuestionDetail.model_validate(events[-1][1])
    live = events[:-1]
    trace_events = [e for e in detail.trace.events if e.stage != "result"]
    assert [n for n, _ in live] == [e.stage for e in trace_events]                       # nothing extra, nothing missing, same order
    for (name, payload), e in zip(live, trace_events):
        assert payload["seq"] == e.seq and payload["stage"] == name and payload["data"] == e.data
    stages = [n for n, _ in live]
    t = detail.trace
    assert stages.count("model_call") == t.totals.model_calls and stages.count("verify") == len(t.verifier)
    assert ("second_pass" in stages) == t.second_pass["ran"]
    assert ("escalate" in stages) == bool(t.escalations) and ("arbitrate" in stages) == t.arbitration["ran"]
    assert ("aggregates_added" in stages) == any(c.aggregates for c in t.contexts)
    assert stages.count("route") == 1 and stages[0] == "route"
    return detail


def test_stream_live_escalation_stages(fake_client):
    ev = sse(fake_client, MULTI_PART)
    d = check_stream_is_the_trace(ev)
    stages = [n for n, _ in ev]
    assert stages.count("escalate") == 1 and stages.index("escalate") < len(stages) - 1
    i = stages.index("escalate")
    assert stages[i + 1] == "model_call" and ev[i + 1][1]["data"]["outcome"] == "live"          # escalate comes right before its call
    assert d.source == "live" and d.trace.totals.live_calls == 3 and "escalated" in d.flags


def test_stream_clean_live_answer(fake_client):
    d = check_stream_is_the_trace(sse(fake_client, UNCACHED))
    assert d.status == "answered" and [m.purpose for m in d.trace.model_calls][:2] == [
        "primary run 1", "primary run 2 (independent repeat, disagreement check)"]


def test_stream_early_abstain_has_only_route_and_result(client):
    ev = sse(client, "What was the measured depth in the report for well F-99 on 2013-08-12?")
    assert [n for n, _ in ev] == ["route", "result"]
    check_stream_is_the_trace(ev)


def test_stream_uncached_without_key(client):
    d = check_stream_is_the_trace(sse(client, UNCACHED))
    assert d.status == "not_evaluated" and d.trace.model_calls[-1].outcome == "cache_miss_offline"


@pytest.mark.parametrize("qid", [f"T2-{i:03d}" for i in range(1, 33)])
def test_stream_every_challenge_question(client, qid):
    q = client.get(f"/questions/{qid}").json()["question"]
    d = check_stream_is_the_trace(sse(client, q))
    assert d.id == qid and d.source in ("cache", "none")
    got = client.get(f"/questions/{qid}").json()
    assert (d.answer, d.status, d.confidence, d.evidence) == (got["answer"], got["status"], got["confidence"], got["evidence"])


def test_stream_validation_and_budget_errors(client):
    assert client.post("/ask/stream", json={"question": "x" * 500}).status_code == 422
