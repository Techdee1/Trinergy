"""LLM layer: cache, offline, retries, budget, ledger. No network, no spend."""
import json

import pytest

from submission.archive_qa import llm as L
from submission.archive_qa.llm import (LLM, BudgetExceeded, Cache, CacheMiss, FakeLLM, LLMConfig, OpenRouterBackend,
                                       TransientError, cache_key, load_config, parse_json_reply)


def make(tmp_path, backend=None, **cfg):
    c = LLMConfig(primary="m-primary", escalation="m-escalation", live=backend is not None, **cfg)
    return LLM(c, backend, Cache(tmp_path / "cache.json"), tmp_path / "ledger.csv")


def ask(llm, ctx="CTX", q="Q?", model="m-primary", **kw):
    return llm.ask("SYS", ctx, q, model, question_id="T2-000", **kw)


def test_cache_hit_skips_client(tmp_path):
    fake = FakeLLM()
    llm = make(tmp_path, fake)
    a, b = ask(llm), ask(llm)
    assert len(fake.calls) == 1 and not a.cache_hit and b.cache_hit and a.parsed == b.parsed
    assert llm.live_calls == 1 and llm.cache_hits == 1
    rows = (tmp_path / "ledger.csv").read_text().splitlines()
    assert len(rows) == 3 and rows[1].endswith("False") and rows[2].endswith("True")  # header + 2 calls
    # a different model, context or feedback is a different call
    ask(llm, model="m-escalation"); ask(llm, ctx="CTX2"); ask(llm, feedback="fix")
    assert len(fake.calls) == 4


def test_offline_cache_miss_raises_clearly(tmp_path):
    llm = make(tmp_path, backend=None)
    with pytest.raises(CacheMiss) as e:
        ask(llm)
    assert "T2-000" in str(e.value) and "llm_cache.json" in str(e.value)


def test_offline_replays_cache_written_live(tmp_path):
    live = make(tmp_path, FakeLLM({"CTX": {"status": "abstain", "answer": "x", "cited_ids": [], "rationale": "r"}}))
    first = ask(live)
    offline = LLM(LLMConfig(primary="m-primary", live=False), None, Cache(tmp_path / "cache.json"), tmp_path / "l2.csv")
    again = ask(offline)
    assert again.cache_hit and again.parsed == first.parsed


def test_cache_never_stores_context_or_key(tmp_path):
    llm = make(tmp_path, FakeLLM())
    ask(llm, ctx="SECRET-EVIDENCE-LINE-123")
    text = (tmp_path / "cache.json").read_text()
    assert "SECRET-EVIDENCE-LINE-123" not in text
    data = json.loads(text)
    (entry,) = data["entries"].values()
    assert set(entry) >= {"response", "model", "usage"} and data["_meta"]["models"]["primary"] == "m-primary"


def test_cache_key_is_stable_and_field_boundaries_do_not_collide():
    s = {"temperature": 0, "max_tokens": 500}
    k = cache_key("sys", "ctx", "q", "", "m", s)
    assert k == cache_key("sys", "ctx", "q", "", "m", s) and len(k) == 64
    assert k != cache_key("sys", "ctx", "q", "", "m2", s)
    assert k != cache_key("sys", "ctx", "q", "", "m", {**s, "max_tokens": 600})
    assert cache_key("ab", "c", "q", "", "m", s) != cache_key("a", "bc", "q", "", "m", s)


def test_budget_guard(tmp_path):
    llm = make(tmp_path, FakeLLM(cost=0.001), budget_usd=0.0015)
    ask(llm, ctx="1"); ask(llm, ctx="2")        # spent 0.001 then 0.002
    with pytest.raises(BudgetExceeded):
        ask(llm, ctx="3")
    assert ask(llm, ctx="1").cache_hit          # cached answers are free and never blocked


def test_retries_only_429_and_5xx(monkeypatch):
    be = OpenRouterBackend("k", max_attempts=3, backoff=0)
    calls = []

    def flaky(*a, **k):
        calls.append(1)
        if len(calls) < 3:
            raise TransientError("HTTP 429")
        return L.RawResponse("{}")

    monkeypatch.setattr(be, "_once", flaky)
    assert be.chat("s", "u", "m", 10, 0.0).text == "{}" and len(calls) == 3

    calls.clear()
    monkeypatch.setattr(be, "_once", lambda *a, **k: (calls.append(1), (_ for _ in ()).throw(TransientError("HTTP 503")))[1])
    with pytest.raises(RuntimeError, match="still failing"):
        be.chat("s", "u", "m", 10, 0.0)
    assert len(calls) == 3

    calls.clear()
    monkeypatch.setattr(be, "_once", lambda *a, **k: (calls.append(1), (_ for _ in ()).throw(RuntimeError("HTTP 401")))[1])
    with pytest.raises(RuntimeError, match="401"):
        be.chat("s", "u", "m", 10, 0.0)
    assert len(calls) == 1  # 4xx other than 429 is not retried


def test_http_status_handling(monkeypatch):
    class R:
        def __init__(self, code, body):
            self.status_code, self._b, self.text = code, body, json.dumps(body)

        def json(self):
            return self._b

    sent = {}

    def post(url, json=None, headers=None, timeout=None):
        sent.update(json=json, headers=headers)
        return R(200, {"choices": [{"message": {"content": '{"a":1}'}}],
                       "usage": {"prompt_tokens": 7, "completion_tokens": 3, "cost": 0.0002}})

    import requests
    monkeypatch.setattr(requests, "post", post)
    out = OpenRouterBackend("sk-secret")._once("s", "u", "mdl", 500, 0.0)
    assert (out.prompt_tokens, out.completion_tokens, out.cost_usd) == (7, 3, 0.0002)
    assert sent["json"]["temperature"] == 0 and sent["json"]["max_tokens"] == 500
    assert sent["json"]["response_format"] == {"type": "json_object"}
    monkeypatch.setattr(requests, "post", lambda *a, **k: R(429, {"error": "rate sk-secret"}))
    with pytest.raises(TransientError) as e:
        OpenRouterBackend("sk-secret")._once("s", "u", "m", 5, 0.0)
    assert "sk-secret" not in str(e.value)  # key is scrubbed from error text


def test_api_key_never_in_repr_or_describe(monkeypatch, tmp_path):
    monkeypatch.setenv("OpenRouter_Key", "sk-very-secret")
    monkeypatch.setenv("LLM_MODEL_PRIMARY", "a/b")
    monkeypatch.setenv("LLM_MODEL_ESCALATION", "c/d")
    cfg = load_config(live=True, dotenv_path=tmp_path / "none.env")
    assert cfg.live and cfg.api_key == "sk-very-secret"
    assert "sk-very-secret" not in repr(cfg) and "sk-very-secret" not in json.dumps(cfg.describe())
    assert load_config(live=False, dotenv_path=tmp_path / "none.env").api_key is None  # offline ignores the key


def test_live_requires_key_and_models(monkeypatch, tmp_path):
    for n in ("OpenRouter_Key", "OPENROUTER_API_KEY", "LLM_MODEL_PRIMARY", "LLM_MODEL_ESCALATION"):
        monkeypatch.delenv(n, raising=False)
    monkeypatch.setattr(L.config, "LLM_CACHE_PATH", tmp_path / "none.json")
    with pytest.raises(RuntimeError, match="OpenRouter_Key"):
        load_config(live=True, dotenv_path=tmp_path / "none.env")
    monkeypatch.setenv("OpenRouter_Key", "k")
    with pytest.raises(L.ModelsNotSet, match="LLM_MODEL_PRIMARY"):
        load_config(live=True, dotenv_path=tmp_path / "none.env")


def test_offline_models_come_from_cache_meta(monkeypatch, tmp_path):
    for n in ("LLM_MODEL_PRIMARY", "LLM_MODEL_ESCALATION", "LLM_MODEL_FAST"):
        monkeypatch.delenv(n, raising=False)
    cache = tmp_path / "c.json"
    cache.write_text(json.dumps({"_meta": {"models": {"primary": "p/1", "escalation": "e/2"}}, "entries": {}}))
    monkeypatch.setattr(L.config, "LLM_CACHE_PATH", cache)
    cfg = load_config(live=False, dotenv_path=tmp_path / "none.env")
    assert (cfg.primary, cfg.escalation) == ("p/1", "e/2")


def test_env_file_names_only(tmp_path):
    f = tmp_path / ".env"
    f.write_text('# c\nOpenRouter_Key="abc"\nexport LLM_MODEL_PRIMARY=x/y\n\nBAD LINE\n')
    assert L.env_names(f) == ["LLM_MODEL_PRIMARY", "OpenRouter_Key"]
    assert L.load_env_file(f)["OpenRouter_Key"] == "abc"


def test_parse_json_reply():
    assert parse_json_reply('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_reply('noise {"a": 2} tail') == {"a": 2}
    assert "__unparsed__" in parse_json_reply("not json")


def test_cost_summary(tmp_path):
    llm = make(tmp_path, FakeLLM(cost=0.002))
    llm.ask("S", "c1", "q", "m-primary", question_id="T2-001")
    llm.ask("S", "c2", "q", "m-escalation", question_id="T2-001", role="escalation")
    llm.ask("S", "c3", "q", "m-primary", question_id="T2-002")
    llm.ask("S", "c3", "q", "m-primary", question_id="T2-002")  # cache hit
    path = L.write_cost_summary(llm.cache, llm, tmp_path / "cost_summary.csv")
    rows = path.read_text().splitlines()
    assert rows[0].startswith("question_id,calls,cache_hits") and len(rows) == 4
    assert rows[1].startswith("T2-001,2,0,") and rows[2].startswith("T2-002,1,0,")
    assert rows[3].startswith("TOTAL") and ",3,1,300,150,0.006000" in rows[3]
