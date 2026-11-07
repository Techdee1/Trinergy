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
    rf = sent["json"]["response_format"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["strict"] is True
    assert rf["json_schema"]["schema"]["required"] == ["status", "answer", "cited_ids", "rationale"]
    assert "seed" not in sent["json"] and "provider" not in sent["json"] and "reasoning" not in sent["json"]
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


def test_live_requires_a_key_and_defaults_to_the_recommended_models(monkeypatch, tmp_path):
    env = _clean_env(monkeypatch, tmp_path)
    with pytest.raises(RuntimeError, match="OPENROUTER_KEY"):
        load_config(live=True, dotenv_path=env)
    monkeypatch.setenv("OpenRouter_Key", "k")
    cfg = load_config(live=True, dotenv_path=env)
    assert (cfg.primary, cfg.escalation) == ("anthropic/claude-haiku-5.5", "anthropic/claude-sonnet-5.5")
    assert cfg.concurrency == 8 and cfg.temperature == 0.0


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


# ---- per-role settings ---------------------------------------------------------------------------------


def _clean_env(monkeypatch, tmp_path):
    for n in ("OpenRouter_Key", "OPENROUTER_API_KEY", "LLM_MODEL_PRIMARY", "LLM_MODEL_ESCALATION", "LLM_MODEL_FAST",
              "LLM_MAX_TOKENS", "LLM_REASONING", "LLM_ESCALATION_MAX_TOKENS", "LLM_ESCALATION_REASONING",
              "LLM_PROVIDER", "LLM_CONCURRENCY"):
        monkeypatch.delenv(n, raising=False)
    monkeypatch.setattr(L.config, "LLM_CACHE_PATH", tmp_path / "none.json")
    return tmp_path / "none.env"


def test_recommended_settings_are_the_defaults(monkeypatch, tmp_path):
    cfg = load_config(dotenv_path=_clean_env(monkeypatch, tmp_path))
    p, e = cfg.role_settings("primary"), cfg.role_settings("escalation")
    pin = {"order": ["Anthropic"], "allow_fallbacks": False, "require_parameters": False}
    assert p == {"temperature": 0.0, "max_tokens": 400, "response_format": "json_schema", "reasoning": "none", "provider": pin}
    assert e == {"temperature": 0.0, "max_tokens": 1500, "response_format": "json_schema", "reasoning": "minimal", "provider": pin}
    assert cfg.settings == p and L.DEFAULT_MAX_TOKENS == 400
    assert p["provider"]["require_parameters"] is False   # true makes every Claude request return HTTP 404


def test_env_overrides_and_validation(monkeypatch, tmp_path):
    env = _clean_env(monkeypatch, tmp_path)
    monkeypatch.setenv("LLM_MAX_TOKENS", "2500")
    monkeypatch.setenv("LLM_ESCALATION_MAX_TOKENS", "3000")
    monkeypatch.setenv("LLM_REASONING", "LOW")
    cfg = load_config(dotenv_path=env)
    assert (cfg.max_tokens, cfg.reasoning, cfg.escalation_max_tokens) == (2500, "low", 3000)
    assert cfg.describe()["max_tokens"] == 2500 and cfg.describe()["escalation_reasoning"] == "minimal"
    unset = load_config(dotenv_path=_clean_env(monkeypatch, tmp_path))
    assert cache_key("s", "c", "q", "", "m", unset.settings) != cache_key("s", "c", "q", "", "m", cfg.settings)
    monkeypatch.setenv("LLM_MAX_TOKENS", "0")
    with pytest.raises(ValueError, match="LLM_MAX_TOKENS"):
        load_config(dotenv_path=env)
    monkeypatch.setenv("LLM_MAX_TOKENS", "400")
    monkeypatch.setenv("LLM_ESCALATION_REASONING", "turbo")
    with pytest.raises(ValueError, match="LLM_ESCALATION_REASONING"):
        load_config(dotenv_path=env)


def test_provider_pin_can_be_changed_or_switched_off(monkeypatch, tmp_path):
    env = _clean_env(monkeypatch, tmp_path)
    monkeypatch.setenv("LLM_PROVIDER", "Google,Anthropic")
    assert load_config(dotenv_path=env).role_settings("primary")["provider"]["order"] == ["Google", "Anthropic"]
    monkeypatch.setenv("LLM_PROVIDER", "")
    assert "provider" not in load_config(dotenv_path=env).role_settings("primary")


def test_reasoning_and_provider_sent_to_api_only_when_set(monkeypatch):
    import requests

    bodies = []

    class R:
        status_code, text = 200, ""

        def json(self):
            return {"choices": [{"message": {"content": "{}"}}], "usage": {}}

    monkeypatch.setattr(requests, "post", lambda url, json=None, **k: (bodies.append(json), R())[1])
    be = OpenRouterBackend("k")
    be._once("s", "u", "m", 400, 0.0)
    pin = {"order": ["Anthropic"], "allow_fallbacks": False, "require_parameters": False}
    be._once("s", "u", "m", 1500, 0.0, "minimal", pin)
    assert "reasoning" not in bodies[0] and "provider" not in bodies[0] and bodies[0]["max_tokens"] == 400
    assert bodies[1]["reasoning"] == {"effort": "minimal"} and bodies[1]["provider"] == pin


def test_each_role_uses_its_own_settings_and_cache_keys(tmp_path):
    fake = FakeLLM()
    llm = make(tmp_path, fake)
    ask(llm, role="primary")
    ask(llm, model="m-escalation", role="escalation")
    prim, esc = fake.calls
    assert (prim["max_tokens"], prim["reasoning"]) == (400, "none") and prim["temperature"] == 0.0
    assert (esc["max_tokens"], esc["reasoning"]) == (1500, "minimal")
    assert prim["provider"] == esc["provider"] == {"order": ["Anthropic"], "allow_fallbacks": False, "require_parameters": False}


def test_run_salt_gives_a_separate_cache_entry_with_identical_settings(tmp_path):
    fake = FakeLLM()
    llm = make(tmp_path, fake)
    a, b, c = ask(llm), ask(llm, run="2"), ask(llm, run="2")
    assert len(fake.calls) == 2 and not a.cache_hit and not b.cache_hit and c.cache_hit
    assert fake.calls[0]["max_tokens"] == fake.calls[1]["max_tokens"] and fake.calls[0]["user"] == fake.calls[1]["user"]
    s = {"max_tokens": 400}
    assert cache_key("s", "c", "q", "", "m", s) == cache_key("s", "c", "q", "", "m", s, "")   # no salt: old keys unchanged
    assert cache_key("s", "c", "q", "", "m", s, "2") != cache_key("s", "c", "q", "", "m", s)


def test_prompt_hash_is_part_of_the_key_and_saved_in_meta(tmp_path):
    from submission.archive_qa.prompts import prompt_sha
    llm = make(tmp_path, FakeLLM())
    llm.ask("PROMPT A", "c", "q", "m-primary")
    llm.ask("PROMPT B", "c", "q", "m-primary")
    assert len(llm.cache.entries) == 2
    assert llm.cache.meta["prompt_sha"] == prompt_sha("PROMPT B")


def test_offline_replay_takes_per_role_settings_from_cache_meta(monkeypatch, tmp_path):
    env = _clean_env(monkeypatch, tmp_path)
    cache = tmp_path / "c.json"
    rec = {"primary": {"max_tokens": 2200, "reasoning": "low", "provider": {"order": ["Google"]}},
           "escalation": {"max_tokens": 900, "reasoning": "high"}}
    cache.write_text(json.dumps({"_meta": {"settings": rec, "models": {"primary": "p/1"}}, "entries": {}}))
    monkeypatch.setattr(L.config, "LLM_CACHE_PATH", cache)
    cfg = load_config(live=False, dotenv_path=env)
    assert (cfg.primary, cfg.max_tokens, cfg.reasoning, cfg.provider) == ("p/1", 2200, "low", ("Google",))
    assert (cfg.escalation_max_tokens, cfg.escalation_reasoning) == (900, "high")   # same keys as the live run
    monkeypatch.setenv("LLM_MAX_TOKENS", "300")                                      # an explicit env value still wins
    assert load_config(live=False, dotenv_path=env).max_tokens == 300
