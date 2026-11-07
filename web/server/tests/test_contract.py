"""Every endpoint returns the documented shape; the committed answers are reproduced exactly."""

import json

import pytest

from submission.archive_qa import config
from web.server.schemas import Health, QuestionDetail

TRACE_KEYS = {"router", "contexts", "model_calls", "verifier", "retries", "escalations", "second_pass", "arbitration", "cited",
              "decisions", "warnings", "totals", "events"}


def test_health_shape_and_no_key(client):
    h = client.get("/health").json()
    Health.model_validate(h)
    assert set(h) == {"status", "live_mode", "models", "version", "attribution", "budget_remaining_usd", "details"}
    assert h["attribution"] == "Data: Equinor Volve dataset"
    assert h["live_mode"] is False and h["budget_remaining_usd"] == 2.0 and set(h["models"]) == {"primary", "escalation"}
    assert "key" not in json.dumps(h).replace("key_configured", "")


def test_questions_list(client):
    r = client.get("/questions").json()
    assert r["sets"]["challenge"] == 32 and r["count"] == len(r["questions"])
    for q in r["questions"]:
        assert set(q) == {"id", "set", "question", "status", "confidence", "flags", "router_mode"}
    assert {q["set"] for q in r["questions"]} <= {"challenge", "unseen"}
    assert len(client.get("/questions?set=challenge").json()["questions"]) == 32


def test_question_detail_matches_committed_predictions(client):
    import csv
    with config.PREDICTIONS_PATH.open(encoding="utf-8", newline="") as f:
        committed = {r["question_id"]: r for r in csv.DictReader(f)}
    assert len(committed) == 32
    for qid, a in committed.items():
        d = client.get(f"/questions/{qid}").json()
        QuestionDetail.model_validate(d)
        assert set(d["trace"]) == TRACE_KEYS
        assert (d["answer"], f"{d['confidence']:.2f}", d["evidence"]) == (a["answer"], a["confidence"], a["evidence"]), qid
        assert d["source"] in ("cache", "none")


def test_cited_record_fields(client):
    d = client.get("/questions/T2-017").json()
    assert d["cited_records"]
    for c in d["cited_records"]:
        assert {"id", "type", "text", "report", "well", "report_date", "evidence"} <= set(c)
        ev = c["evidence"]
        assert ev["kind"] in ("pdf", "xml_only", "absent") and ev["label"]
        if ev["kind"] == "pdf":
            assert ev["page"] >= 1 and ev["page_url"] == f"/pages/{c['id']}.png" and ev["pdf_file"].endswith(".pdf")


def test_unknown_question_404(client):
    r = client.get("/questions/NOPE")
    assert r.status_code == 404 and r.json()["detail"]["code"] == "unknown_question"


def test_archive(client):
    a = client.get("/archive").json()
    assert len(a["reports"]) == 32 and a["wellbores"] and a["wells"]
    assert {"file", "pdf_file", "well", "wellbore", "date", "pages", "records"} <= set(a["reports"][0])
    assert all(r["pages"] and r["pages"] >= 1 for r in a["reports"])
    assert a["record_counts"]["total"] == sum(a["record_counts"]["by_type"].values())
    assert sum(w["reports"] for w in a["wells"]) == 32


def test_trajectories(client):
    t = client.get("/trajectories").json()
    assert t["approximate"] is True and t["caveats"]
    by = {w["wellbore"]: w for w in t["wellbores"]}
    assert all(w["approximate"] for w in by.values())
    assert any(w["status"] == "skipped" and w["reason"] for w in by.values())
    ok = [w for w in by.values() if w["status"] == "ok"]
    assert ok
    for w in ok:
        assert [s["md"] for s in w["stations"]] == sorted(s["md"] for s in w["stations"])
        assert w["max_tvd_difference_m"] is not None and w["max_tvd_difference_m"] < 5     # computed TVD agrees with the archive's
        assert {"x", "y", "tvd", "tvd_reported", "record_id"} <= set(w["stations"][0])


def test_costs(client):
    c = client.get("/costs").json()
    assert c["ledger"]["calls"] == c["derived_from_cache"]["entries"]
    assert abs(c["ledger"]["cost_usd"] - c["derived_from_cache"]["cost_usd"]) < 1e-5
    assert {m["model"] for m in c["model_mix"]} >= {"anthropic/claude-haiku-5.5", "anthropic/claude-sonnet-5.5"}
    assert c["budget"]["remaining_usd"] == 2.0 and "hit_rate" in c["cache_hit_rate"]["asks"]
    assert any(q["set"] == "challenge" for q in c["per_question"])


def test_generalisation_present_or_clear_message(client):
    g = client.get("/generalisation").json()
    assert set(g) == {"available", "message", "summary", "questions", "attribution"}
    if g["available"]:
        assert g["summary"]["questions"] == len(g["questions"]) == 40
    else:
        assert g["message"] and g["questions"] == []


def test_generalisation_absent(tmp_path):
    from web.server.costs_view import generalisation
    g = generalisation(tmp_path)
    assert g["available"] is False and "results.json" in g["message"] and g["questions"] == []


def test_attribution_everywhere(client):
    assert client.get("/health").headers["x-data-attribution"] == "Data: Equinor Volve dataset"
    assert client.get("/archive").json()["attribution"] == "Data: Equinor Volve dataset"


def test_openapi_and_docs(client):
    spec = client.get("/openapi.json").json()
    assert {"/health", "/questions", "/questions/{question_id}", "/ask", "/ask/stream", "/archive", "/trajectories", "/costs",
            "/generalisation", "/pages/{record_id}.png", "/pages/{record_id}/boxes"} <= set(spec["paths"])
    assert client.get("/docs").status_code == 200


def test_cors_header(client):
    r = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-origin" not in client.get("/health", headers={"Origin": "http://evil.example"}).headers
