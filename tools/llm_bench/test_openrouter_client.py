"""Mocked tests: no network, no spend."""
import json
import pytest
import requests
import openrouter_client as oc

GOOD = {"status": "answered", "answer": "1.03 g/cm3", "cited_ids": ["A-1"], "rationale": "x"}


class FakeResp:
    def __init__(self, status=200, content=None, cost=0.001, headers=None):
        self.status_code = status
        self.headers = headers or {}
        self._body = {
            "model": "m/x",
            "provider": "FakeProv",
            "choices": [{"message": {"content": json.dumps(GOOD) if content is None else content},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20, "cost": cost,
                      "completion_tokens_details": {"reasoning_tokens": 0}},
        } if status == 200 else {"error": {"message": "boom", "code": status}}

    def json(self):
        return self._body


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("OpenRouter_Key", "test-key")
    monkeypatch.setattr(oc, "_sleep", lambda s: None)
    monkeypatch.setattr(oc, "_spent_session", 0.0)
    return oc.ClientConfig(cache_dir=tmp_path / "cache", ledger_path=tmp_path / "ledger.csv", spend_cap_usd=0.01)


def _call(cfg, **kw):
    return oc.call_llm("sys", "ctx", "q", "m/x", config=cfg, **kw)


def test_cache_hit_makes_no_second_request(monkeypatch, env):
    calls = []
    monkeypatch.setattr(oc, "_http_post", lambda *a, **k: calls.append(1) or FakeResp())
    r1, r2 = _call(env), _call(env)
    assert len(calls) == 1
    assert not r1.cache_hit and r2.cache_hit and r2.cost == 0.0
    assert r2.parsed == GOOD and r1.provider == "FakeProv"
    rows = env.ledger_path.read_text().strip().splitlines()
    assert len(rows) == 3 and rows[2].split(",")[7] == "True"  # header + miss + hit


def test_retry_on_429_then_success(monkeypatch, env):
    seq = [FakeResp(429), FakeResp(503), FakeResp()]
    monkeypatch.setattr(oc, "_http_post", lambda *a, **k: seq.pop(0))
    r = _call(env)
    assert r.parsed == GOOD and r.attempts == 3 and len(r.retry_log) == 2


def test_retry_gives_up_after_three(monkeypatch, env):
    monkeypatch.setattr(oc, "_http_post", lambda *a, **k: FakeResp(429))
    r = _call(env)
    assert r.error == "http_429" and r.attempts == 3 and r.parsed is None


def test_network_error_retried(monkeypatch, env):
    seq = [requests.Timeout("t"), FakeResp()]
    def post(*a, **k):
        x = seq.pop(0)
        if isinstance(x, Exception):
            raise x
        return x
    monkeypatch.setattr(oc, "_http_post", post)
    assert _call(env).parsed == GOOD


def test_spend_guard_blocks_before_request(monkeypatch, env):
    calls = []
    monkeypatch.setattr(oc, "_http_post", lambda *a, **k: calls.append(1) or FakeResp(cost=0.009))
    _call(env)                                   # spends 0.009 of 0.01 cap
    with pytest.raises(oc.SpendGuardError):
        oc.call_llm("sys", "ctx", "q2", "m/x", config=env, prices_per_m=(1.0, 10.0), max_tokens=400)
    assert len(calls) == 1                       # second request never sent


def test_json_parse_failure_not_cached(monkeypatch, env):
    monkeypatch.setattr(oc, "_http_post", lambda *a, **k: FakeResp(content="not json"))
    r = _call(env)
    assert r.parsed is None and r.error == "json_parse"
    assert not list(env.cache_dir.glob("*.json")) if env.cache_dir.exists() else True


def test_off_contract_json_rejected(monkeypatch, env):
    monkeypatch.setattr(oc, "_http_post", lambda *a, **k: FakeResp(content='{"status":"maybe","answer":"","cited_ids":[]}'))
    assert _call(env).error == "json_parse"


def test_key_never_in_result_or_ledger(monkeypatch, env):
    monkeypatch.setattr(oc, "_http_post", lambda *a, **k: FakeResp())
    r = _call(env)
    assert "test-key" not in json.dumps(r.__dict__, default=str)
    assert "test-key" not in env.ledger_path.read_text()


def test_missing_key(monkeypatch, env):
    monkeypatch.delenv("OpenRouter_Key")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(oc.MissingKeyError):
        _call(env)
