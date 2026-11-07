"""All provider calls are mocked; no network access."""

from types import SimpleNamespace

import openai
import pytest

from src import cost, llm
from src.config import get_settings


@pytest.fixture
def fake_provider(monkeypatch):
    """Replace the real API call; records each call made."""
    calls = []

    def fake(provider, model, prompt, image, json_output, max_tokens):
        calls.append(dict(provider=provider, model=model, prompt=prompt,
                          image=image, max_tokens=max_tokens))
        return '{"answer": 42}', 1000, 500

    monkeypatch.setattr(llm, "_call_provider", fake)
    return calls


# ---- cache


def test_cache_key_is_stable_and_sensitive():
    k = llm.cache_key("prompt", b"img", "m1")
    assert k == llm.cache_key("prompt", b"img", "m1")
    assert len(k) == 64
    assert k != llm.cache_key("prompt", b"img", "m2")
    assert k != llm.cache_key("prompt", b"img2", "m1")
    assert k != llm.cache_key("prompt!", b"img", "m1")
    assert llm.cache_key("p", None, "m") == llm.cache_key("p", b"", "m")
    assert llm.cache_key("ab", b"c", "m") != llm.cache_key("a", b"bc", "m")


def test_cache_hit_skips_api(fake_provider):
    first = llm.call_llm("Extract", image=b"png", source="doc:p1")
    second = llm.call_llm("Extract", image=b"png", source="doc:p1")
    assert first == second == {"answer": 42}
    assert len(fake_provider) == 1

    llm.call_llm("Extract", image=b"other", source="doc:p2")
    assert len(fake_provider) == 2


def test_text_output_and_max_tokens(fake_provider):
    text = llm.call_llm("Hi", json_output=False, max_output_tokens=77)
    assert text == '{"answer": 42}'
    assert fake_provider[0]["max_tokens"] == 77


# ---- ledger / cost


def test_ledger_records_usage_and_cost(fake_provider):
    llm.call_llm("Extract", source="a.pdf:p1")
    llm.call_llm("Extract", source="a.pdf:p1")  # cache hit

    df = cost.load_ledger()
    assert list(df.columns) == llm.LEDGER_FIELDS
    assert len(df) == 2

    paid, hit = df.iloc[0], df.iloc[1]
    # 1000 in * $2/1M + 500 out * $8/1M = 0.002 + 0.004
    assert (paid.input_tokens, paid.output_tokens) == (1000, 500)
    assert paid.cost_usd == pytest.approx(0.006)
    assert not paid.cache_hit
    assert paid.source == "a.pdf:p1"
    assert (paid.provider, paid.model) == ("openai", "test-model")
    assert (hit.input_tokens, hit.output_tokens, hit.cost_usd) == (0, 0, 0)
    assert hit.cache_hit

    s = cost.summarize()
    assert s["calls"] == 2 and s["cache_hits"] == 1 and s["paid_calls"] == 1
    assert s["cost_usd"] == pytest.approx(0.006)
    assert s["avg_cost_per_call"] == pytest.approx(0.003)
    assert cost.project(1000, summary=s) == pytest.approx(6.0)


def test_summary_without_ledger():
    s = cost.summarize()
    assert s["calls"] == 0 and s["cost_usd"] == 0
    assert cost.project(100, summary=s) == 0


# ---- JSON parsing


def test_parse_json_strips_fences():
    assert llm.parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    with pytest.raises(llm.LLMJSONError) as e:
        llm.parse_json("not json")
    assert e.value.raw == "not json"


# ---- retries


def _connection_error():
    return openai.APIConnectionError(request=None)


def test_retries_transient_then_succeeds(monkeypatch):
    attempts = []

    def flaky(*args):
        attempts.append(1)
        if len(attempts) < 3:
            raise _connection_error()
        return "{}", 1, 1

    monkeypatch.setattr(llm, "_call_provider", flaky)
    assert llm.call_llm("p") == {}
    assert len(attempts) == 3


def test_gives_up_after_max_attempts(monkeypatch):
    attempts = []

    def always_down(*args):
        attempts.append(1)
        raise _connection_error()

    monkeypatch.setattr(llm, "_call_provider", always_down)
    with pytest.raises(openai.APIConnectionError):
        llm.call_llm("p")
    assert len(attempts) == 3  # LLM_MAX_ATTEMPTS in conftest


def test_does_not_retry_non_transient(monkeypatch):
    attempts = []

    def bad_request(*args):
        attempts.append(1)
        raise ValueError("bad request")

    monkeypatch.setattr(llm, "_call_provider", bad_request)
    with pytest.raises(ValueError):
        llm.call_llm("p")
    assert len(attempts) == 1


# ---- provider adapters read usage correctly (fake SDK responses)


def _client_returning(monkeypatch, client):
    monkeypatch.setattr(llm, "_get_client", lambda *a: client)


def test_openai_adapter(monkeypatch):
    seen = {}

    def create(**kw):
        seen.update(kw)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))],
            usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7),
        )

    _client_returning(monkeypatch, SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    out = llm._call_provider("openai", "m", "p", b"img", True, 50)
    assert out == ('{"ok": true}', 11, 7)
    assert seen["max_completion_tokens"] == 50
    assert seen["response_format"] == {"type": "json_object"}


def test_anthropic_adapter(monkeypatch):
    def create(**kw):
        assert kw["max_tokens"] == 50
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="hi")],
            usage=SimpleNamespace(input_tokens=10, output_tokens=3,
                                  cache_creation_input_tokens=None, cache_read_input_tokens=2),
        )

    _client_returning(monkeypatch, SimpleNamespace(messages=SimpleNamespace(create=create)))
    assert llm._call_provider("anthropic", "m", "p", b"img", False, 50) == ("hi", 12, 3)


def test_gemini_adapter(monkeypatch):
    def generate_content(model, contents, config):
        assert config.max_output_tokens == 50
        return SimpleNamespace(
            text="{}",
            usage_metadata=SimpleNamespace(prompt_token_count=20, candidates_token_count=4,
                                           thoughts_token_count=6),
        )

    _client_returning(monkeypatch, SimpleNamespace(
        models=SimpleNamespace(generate_content=generate_content)))
    assert llm._call_provider("gemini", "m", "p", b"img", True, 50) == ("{}", 20, 10)


def test_rejects_unknown_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mystery")
    assert get_settings().llm_provider == "mystery"
    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        llm.call_llm("p")
