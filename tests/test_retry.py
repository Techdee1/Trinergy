"""Truncation / invalid-JSON retry on the primary model, and ABSENT citation added in code. FakeLLM only."""
import json

import pytest

from submission.archive_qa import answer as A
from submission.archive_qa import llm as L
from submission.archive_qa.llm import LLM, Cache, FakeLLM, LLMConfig, load_config
from submission.archive_qa.prompts import SYSTEM_PROMPT
from submission.archive_qa.route import load_questions
from submission.archive_qa.write import answer_notes, build_evidence
from tests.conftest import needs_data
from tests.test_answer import FLUID, good, make

TRUNC = ('{"status": "answered", "answer": "The NaCl brine dens', "length")


@pytest.fixture(scope="module")
def qtext():
    return load_questions().set_index("question_id")["question_text"]


def go(tmp_path, script, qid, qtext, reports, located):
    llm, fake = make(tmp_path, script)
    a = A.answer_question(qid, qtext[qid], located, reports, llm, dump=False)
    return a, fake, llm


# ---- retry before escalation ----------------------------------------------------------------------------------


@needs_data
def test_truncated_reply_is_retried_on_the_primary_with_1500_before_escalating(tmp_path, qtext, reports, located):
    def script(system, user, model, max_tokens):
        return TRUNC if max_tokens == 400 else good()

    a, fake, llm = go(tmp_path, script, "T2-016", qtext, reports, located)
    assert [(c["model"], c["max_tokens"]) for c in fake.calls] == [("m1", 400), ("m1", 1500), ("m1", 400), ("m1", 1500)]
    assert "m2" not in [c["model"] for c in fake.calls]                      # never reached Sonnet
    assert a.verified and a.status == "answered" and a.llm_calls == 4 and not a.disagree
    assert sum("truncated (finish_reason=length)" in n and "max_tokens 1500" in n for n in a.notes) == 2
    # each call is its own cache entry; the retry's cap is part of its key
    assert len(llm.cache.entries) == 4
    caps = sorted(e["role"] for e in llm.cache.entries.values())
    assert caps == ["primary", "primary_retry", "primary_run2", "primary_run2_retry"]
    assert sum(e["finish_reason"] == "length" for e in llm.cache.entries.values()) == 2


@needs_data
def test_invalid_json_without_length_is_also_retried(tmp_path, qtext, reports, located):
    def script(system, user, model, max_tokens):
        return "Sure! Here is the answer: not json" if max_tokens == 400 else good()

    a, fake, _ = go(tmp_path, script, "T2-016", qtext, reports, located)
    assert [c["max_tokens"] for c in fake.calls] == [400, 1500, 400, 1500] and a.verified
    assert any("not valid JSON" in n for n in a.notes)


@needs_data
def test_no_retry_when_the_first_reply_is_fine(tmp_path, qtext, reports, located):
    a, fake, _ = go(tmp_path, lambda s, u, m: good(), "T2-016", qtext, reports, located)
    assert [c["max_tokens"] for c in fake.calls] == [400, 400] and a.llm_calls == 2
    assert not any("retried" in n for n in a.notes)


@needs_data
def test_run_one_needing_the_retry_does_not_fire_the_disagreement_flag(tmp_path, qtext, reports, located):
    seen = []

    def script(system, user, model, max_tokens):
        seen.append(max_tokens)
        return TRUNC if len(seen) == 1 else good()          # only run 1's first call is truncated

    a, fake, _ = go(tmp_path, script, "T2-016", qtext, reports, located)
    assert seen == [400, 1500, 400]                          # run 1 retried, run 2 clean
    assert not a.disagree and not any("runs disagree" in n for n in a.notes)
    assert a.verified and not a.needs_review


@needs_data
def test_genuinely_different_final_runs_still_disagree(tmp_path, qtext, reports, located):
    seen = []

    def script(system, user, model, max_tokens):
        seen.append(max_tokens)
        if len(seen) == 1:
            return TRUNC
        if len(seen) == 2:
            return good()
        return good(answer="The density was 1.03 g/cm3 and 345 bar.") if len(seen) == 3 else good(cited_ids=["NOPE-1"])

    a, _, _ = go(tmp_path, script, "T2-016", qtext, reports, located)    # 4th call = the arbiter, which fails verification
    assert a.disagree and any("runs disagree" in n for n in a.notes)


@needs_data
def test_escalates_only_after_the_retry_also_fails(tmp_path, qtext, reports, located):
    def script(system, user, model, max_tokens):
        return "garbage" if model == "m1" else good()

    a, fake, _ = go(tmp_path, script, "T2-016", qtext, reports, located)
    assert [(c["model"], c["max_tokens"]) for c in fake.calls] == [
        ("m1", 400), ("m1", 1500), ("m1", 400), ("m1", 1500), ("m2", 1500)]
    assert a.verified and a.model == "m2" and any("escalated to m2" in n for n in a.notes)


@needs_data
def test_retry_replays_offline_from_the_cache(tmp_path, qtext, reports, located):
    def script(system, user, model, max_tokens):
        return TRUNC if max_tokens == 400 else good()

    live, fake, llm = go(tmp_path, script, "T2-016", qtext, reports, located)
    offline = LLM(LLMConfig(primary="m1", escalation="m2", live=False), None, Cache(tmp_path / "c.json"), tmp_path / "l2.csv")
    again = A.answer_question("T2-016", qtext["T2-016"], located, reports, offline, dump=False)
    assert (again.status, again.answer, again.cited_ids, again.confidence) == (
        live.status, live.answer, live.cited_ids, live.confidence)
    assert offline.live_calls == 0 and offline.cache_hits == 4 and not again.disagree


# ---- cache + config ----------------------------------------------------------------------------------------------


def test_max_tokens_override_is_part_of_the_cache_key(tmp_path):
    fake = FakeLLM()
    llm = LLM(LLMConfig(primary="m1", escalation="m2", live=True), fake, Cache(tmp_path / "c.json"), tmp_path / "l.csv")
    llm.ask("S", "ctx", "q", "m1", question_id="T")
    llm.ask("S", "ctx", "q", "m1", question_id="T", max_tokens=1500)
    llm.ask("S", "ctx", "q", "m1", question_id="T", max_tokens=1500)       # same override: cache hit
    assert [c["max_tokens"] for c in fake.calls] == [400, 1500] and len(llm.cache.entries) == 2 and llm.cache_hits == 1


def test_default_max_tokens_unchanged_and_retry_cap_is_configurable(monkeypatch, tmp_path):
    for n in ("LLM_MAX_TOKENS", "LLM_RETRY_MAX_TOKENS", "OpenRouter_Key", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(n, raising=False)
    monkeypatch.setattr(L.config, "LLM_CACHE_PATH", tmp_path / "none.json")
    cfg = load_config(dotenv_path=tmp_path / "none.env")
    assert (cfg.max_tokens, cfg.retry_max_tokens) == (400, 1500)             # LLM_MAX_TOKENS default untouched
    assert cfg.role_settings("primary")["max_tokens"] == 400
    monkeypatch.setenv("LLM_RETRY_MAX_TOKENS", "2000")
    assert load_config(dotenv_path=tmp_path / "none.env").retry_max_tokens == 2000
    monkeypatch.setenv("LLM_RETRY_MAX_TOKENS", "0")
    with pytest.raises(ValueError, match="LLM_RETRY_MAX_TOKENS"):
        load_config(dotenv_path=tmp_path / "none.env")


def test_retry_cap_and_finish_reason_are_recorded_for_offline_replay(monkeypatch, tmp_path):
    fake = FakeLLM(lambda s, u, m: ('{"sta', "length"))
    llm = LLM(LLMConfig(primary="m1", escalation="m2", live=True, retry_max_tokens=1800), fake,
              Cache(tmp_path / "c.json"), tmp_path / "l.csv")
    r = llm.ask("S", "c", "q", "m1", question_id="T")
    assert r.finish_reason == "length" and r.truncated_or_invalid
    meta = json.loads((tmp_path / "c.json").read_text())["_meta"]
    assert meta["settings"]["retry"] == {"max_tokens": 1800}
    for n in ("LLM_RETRY_MAX_TOKENS", "OpenRouter_Key", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(n, raising=False)
    monkeypatch.setattr(L.config, "LLM_CACHE_PATH", tmp_path / "c.json")
    assert load_config(dotenv_path=tmp_path / "none.env").retry_max_tokens == 1800     # reviewers need no env var
    assert llm.ask("S", "c", "q", "m1", question_id="T").finish_reason == "length"     # replays from the cache


def test_openrouter_backend_reads_finish_reason(monkeypatch):
    import requests

    class R:
        status_code, text = 200, ""

        def json(self):
            return {"choices": [{"message": {"content": '{"sta'}, "finish_reason": "length"}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 400, "cost": 0.001}}

    monkeypatch.setattr(requests, "post", lambda *a, **k: R())
    out = L.OpenRouterBackend("k")._once("s", "u", "m", 400, 0.0)
    assert out.finish_reason == "length" and out.completion_tokens == 400


# ---- ABSENT record cited in code on an abstention --------------------------------------------------------------------


@needs_data
def test_abstain_gets_the_absent_record_added_in_code(tmp_path, qtext, reports, located):
    reply = {"status": "abstain", "answer": "", "cited_ids": [], "rationale": "The report has no cost line."}
    a, fake, _ = go(tmp_path, lambda s, u, m: reply, "T2-025", qtext, reports, located)
    assert "ABSENT" not in SYSTEM_PROMPT                       # proves it is not the prompt that asks for it
    assert a.cited_ids == ["ABSENT-cost"] and a.verified and a.confidence == 0.85
    assert "Searched 1 report(s) and" in a.rationale and "no cost field exists" in a.rationale
    assert "The report has no cost line." in a.rationale       # the model's own rationale is kept
    ev = build_evidence(a, located)
    assert "15_9_F_1_C_2014_03_26.pdf: all sections checked, no cost field" in ev and "ABSENT" not in ev
    assert "Searched 1 report(s)" in answer_notes(a)
    assert len(fake.calls) == 2                                 # no escalation, no extra call


@needs_data
def test_absent_record_not_duplicated_when_the_model_already_cited_it(tmp_path, qtext, reports, located):
    reply = {"status": "abstain", "answer": "No cost field.", "cited_ids": ["ABSENT-cost"], "rationale": "r"}
    a, _, _ = go(tmp_path, lambda s, u, m: reply, "T2-025", qtext, reports, located)
    assert a.cited_ids == ["ABSENT-cost"] and a.rationale.count("Searched 1 report(s)") == 1


@needs_data
def test_absent_record_added_only_for_abstain_and_only_for_the_questions_topic(tmp_path, qtext, reports, located):
    # an answered question about a topic the archive does have: nothing is added
    a, _, _ = go(tmp_path, lambda s, u, m: good(), "T2-016", qtext, reports, located)
    assert a.cited_ids == [FLUID] and not a.absent
    # a partial answer is not an abstention: the ABSENT record is not forced in
    reply = {"status": "partial", "answer": "Equipment failure at 3850 m; no cost is recorded.",
             "cited_ids": ["F15D-20150810-FAIL-01"], "rationale": "cost field absent"}
    p, _, _ = go(tmp_path / "p", lambda s, u, m: reply, "T2-031", qtext, reports, located)
    assert p.status == "partial" and "ABSENT-cost" not in p.cited_ids
    # an abstention with no ABSENT record in its context (a topic that exists) adds nothing
    ab = {"status": "abstain", "answer": "", "cited_ids": [], "rationale": "not in the lines"}
    q, _, _ = go(tmp_path / "q", lambda s, u, m: ab, "T2-016", qtext, reports, located)
    assert q.status == "abstain" and q.cited_ids == [] and not q.absent
