"""Running the pipeline on other question sets: keys, hybrid mode, question files, output safety, phrasing, and the
guarantee that the 32 published questions are unchanged. No network, no spend."""
import hashlib
import json
import socket
from pathlib import Path

import pytest

from submission.archive_qa import answer as A
from submission.archive_qa import config, llm as L, pipeline, route, write
from submission.archive_qa.llm import LLM, Cache, CacheMiss, FakeLLM, LayeredCache, LLMConfig, cache_key
from submission.archive_qa.route import find_dates
from submission.archive_qa.wells import canonical_well, discover_reports
from tests.conftest import needs_data

FIXTURE = Path(__file__).parent / "fixtures" / "routing_32.json"
SECRET = "sk-or-v1-unit-test-secret"


# ---- keys ---------------------------------------------------------------------------------------------------


def test_every_alias_is_found_and_canonical_wins(monkeypatch):
    for name in L.KEY_ENV_NAMES:
        for n in L.KEY_ENV_NAMES:
            monkeypatch.delenv(n, raising=False)
        monkeypatch.setenv(name, SECRET)
        assert L.find_key() == (name, SECRET)
    monkeypatch.setenv("openrouter_api_key", "b")
    monkeypatch.setenv("OPENROUTER_KEY", "a")
    assert L.find_key()[0] == "OPENROUTER_KEY"
    assert L.KEY_ENV_NAMES[0] == "OPENROUTER_KEY" == L.CANONICAL_KEY_NAME


def test_describe_key_names_the_variable_never_the_value(monkeypatch):
    assert L.describe_key() == "no key found: live mode off, using cached answers"
    monkeypatch.setenv("OpenRouter_Key", SECRET)
    text = L.describe_key()
    assert "OpenRouter_Key" in text and SECRET not in text
    cfg = L.load_config()
    assert cfg.live and SECRET not in repr(cfg) and SECRET not in json.dumps(cfg.describe())


def test_dotenv_is_loaded_and_tolerates_spaces(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text(f'# comment\nOPENROUTER_KEY   =   {SECRET}  \nLLM_CONCURRENCY = 3\n')
    monkeypatch.setattr(L, "env_files", lambda: [env])
    assert L.find_key() == ("OPENROUTER_KEY", SECRET)
    assert L.load_config().concurrency == 3
    env.write_text(f'OpenRouter_Key = "{SECRET}"\n')
    assert L.find_key() == ("OpenRouter_Key", SECRET)


def test_no_key_means_offline_and_missing_optional_settings_never_crash(monkeypatch):
    for n in ("LLM_MODEL_PRIMARY", "LLM_MODEL_ESCALATION", "LLM_PROVIDER", "LLM_MODEL_FAST"):
        monkeypatch.delenv(n, raising=False)
    cfg = L.load_config()
    assert not cfg.live and cfg.provider and cfg.primary and cfg.escalation
    monkeypatch.setenv("LLM_PROVIDER", "")
    assert L.load_config().provider in (None, [], ())          # empty pin = default routing, not an error


# ---- hybrid mode and NOT EVALUATED -------------------------------------------------------------------------


def test_cache_key_includes_the_question_text():
    s = {"max_tokens": 400}
    a = cache_key("sys", "ctx", "What was the depth on 2014-03-14?", "", "m", s)
    b = cache_key("sys", "ctx", "What was the pressure on 2014-03-14?", "", "m", s)
    assert a != b and a == cache_key("sys", "ctx", "What was the depth on 2014-03-14?", "", "m", s)


@needs_data
def test_same_question_id_with_other_text_is_a_miss(tmp_path, located):
    reports = discover_reports(config.XML_DIR)
    fake = FakeLLM({}) 
    llm = LLM(LLMConfig(primary="m1", escalation="m2", live=False), None, Cache(tmp_path / "c.json"), tmp_path / "l.csv")
    q1 = "What was the density of the NaCl brine sampled from the active pit on well 15/9-F-1-C on 2014-03-26?"
    q2 = "What was the temperature of the NaCl brine sampled from the active pit on well 15/9-F-1-C on 2014-03-26?"
    llm_live = LLM(LLMConfig(primary="m1", escalation="m2", live=True, concurrency=1), fake, llm.cache, tmp_path / "l.csv")
    A.answer_question("Q-1", q1, located, reports, llm_live, dump=False)       # fills the cache for text 1
    n = len(fake.calls)
    A.answer_question("Q-1", q1, located, reports, llm, dump=False, raise_on_miss=True)   # same id, same text: hit offline
    with pytest.raises(CacheMiss):
        A.answer_question("Q-1", q2, located, reports, llm, dump=False, raise_on_miss=True)   # same id, other text: miss
    assert len(fake.calls) == n


@needs_data
def test_hybrid_key_present_calls_the_model_only_for_misses(tmp_path, located):
    reports = discover_reports(config.XML_DIR)
    base = Cache(tmp_path / "committed.json")
    fake = FakeLLM({})
    cfg = LLMConfig(primary="m1", escalation="m2", live=True, concurrency=1)
    llm = LLM(cfg, fake, LayeredCache(base, Cache(tmp_path / "runtime.json")), tmp_path / "l.csv")
    q = "What was the density of the NaCl brine sampled from the active pit on well 15/9-F-1-C on 2014-03-26?"
    A.answer_question("Q-1", q, located, reports, llm, dump=False)
    first = len(fake.calls)
    assert first > 0 and llm.live_calls == first
    A.answer_question("Q-1", q, located, reports, llm, dump=False)
    assert len(fake.calls) == first                                       # now cached in the runtime layer
    assert not (tmp_path / "committed.json").exists() or not base.entries   # the committed layer is never written


@needs_data
def test_no_key_and_no_cache_gives_a_not_evaluated_row_and_a_summary(tmp_path, located):
    reports = discover_reports(config.XML_DIR)
    llm = LLM(LLMConfig(primary="m1", escalation="m2", live=False), None, Cache(tmp_path / "e.json"), tmp_path / "l.csv")
    qs = route.pd.DataFrame({"question_id": ["N-1", "N-2"], "question_text": [
        "What was the density of the NaCl brine sampled from the active pit on well 15/9-F-1-C on 2014-03-26?",
        "What did the report for well 15/9-F-14 on 2013-06-10 say?"]})
    answers = A.answer_all(qs, located, reports, llm, dump=False)      # no raise
    ne = answers[0]
    assert ne.status == "not_evaluated" and ne.answer == "NOT EVALUATED: no API key and no cached answer"
    assert ne.confidence == 0 and write.build_evidence(ne, located) == "" and ne.needs_review
    assert answers[1].early_abstain                                     # early abstentions still work offline
    out = pipeline.not_evaluated_summary(answers)
    assert "1 of 2" in out and "N-1" in out and "OPENROUTER_KEY" in out
    p = write.write_predictions(answers, located, tmp_path / "p.csv", order=["N-1", "N-2"])
    rep = write.validate_predictions(predictions_path=p, expected_ids=["N-1", "N-2"])
    assert rep["valid"], rep


def test_pinned_provider_unavailable_falls_back_to_default_routing(monkeypatch, caplog):
    sent = []

    def once(self, system, user, model, max_tokens, temperature, reasoning=None, provider=None):
        sent.append((model, provider))
        if provider:
            raise L.ProviderUnavailable("HTTP 404 with provider pin ['Anthropic']")
        return L.RawResponse("{}", 1, 1, 0.0, "stop")

    monkeypatch.setattr(L.OpenRouterBackend, "_once", once)
    b = L.OpenRouterBackend(SECRET)
    pin = {"order": ["Anthropic"], "allow_fallbacks": False, "require_parameters": False}
    with caplog.at_level("WARNING", logger="archive_qa.llm"):
        assert b.chat("s", "u", "anthropic/claude-haiku-5.5", 10, provider=pin).text == "{}"
        b.chat("s", "u", "anthropic/claude-haiku-5.5", 10, provider=pin)
    assert sent == [("anthropic/claude-haiku-5.5", pin), ("anthropic/claude-haiku-5.5", None),
                    ("anthropic/claude-haiku-5.5", None)]                 # same model; the pin is not retried
    assert any("falling back" in r.message for r in caplog.records) and SECRET not in caplog.text


# ---- question file and output ------------------------------------------------------------------------------


@pytest.mark.parametrize("cols", [["question_id", "question_text"], ["QUESTION_ID", "Question"], ["ID", "Prompt"],
                                  ["Id", "TEXT", "extra"]])
def test_column_detection_is_case_insensitive(tmp_path, cols):
    f = tmp_path / "q.csv"
    f.write_text(",".join(cols) + "\nX-1,What was the depth?" + "," * (len(cols) - 2) + "\n")
    df = pipeline.read_questions(f)
    assert list(df.columns) == ["question_id", "question_text"] and df.iloc[0].tolist() == ["X-1", "What was the depth?"]


def test_missing_columns_error_names_the_columns_found(tmp_path):
    f = tmp_path / "q.csv"
    f.write_text("foo,bar\n1,2\n")
    with pytest.raises(ValueError, match="foo"):
        pipeline.read_questions(f)


def test_duplicate_ids_are_rejected(tmp_path):
    f = tmp_path / "q.csv"
    f.write_text("id,question\nA,x\nA,y\n")
    with pytest.raises(ValueError, match="Duplicate"):
        pipeline.read_questions(f)


@needs_data
def test_a_different_run_never_targets_the_committed_predictions(tmp_path):
    assert pipeline.resolve_output(None, None) == config.PREDICTIONS_PATH
    other = tmp_path / "my_questions.csv"
    other.write_text("id,question\nA,x\n")
    out = pipeline.resolve_output(other, None)
    assert out != config.PREDICTIONS_PATH and out.name == "predictions_my_questions.csv"
    assert pipeline.resolve_output(other, tmp_path / "o.csv") == tmp_path / "o.csv"
    assert pipeline.resolve_output(other, config.PREDICTIONS_PATH) == config.PREDICTIONS_PATH   # only when asked


# ---- phrasing -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize("text,want", [
    ("F-11B", "15/9-F-11-B"), ("F 11 B", "15/9-F-11-B"), ("15/9-F-11 B", "15/9-F-11-B"), ("NO 15/9-F-11 B", "15/9-F-11-B"),
    ("15_9_F_11_B", "15/9-F-11-B"), ("f-15-d", "15/9-F-15-D"), ("F-1C", "15/9-F-1-C"), ("F-1-C", "15/9-F-1-C"),
    ("f-1c", "15/9-F-1-C"), ("F-14", "15/9-F-14"), ("15/9-19 A", "15/9-19-A"),
])
def test_well_phrasings(text, want):
    assert canonical_well(f"What happened in well {text} that day?") == want


@pytest.mark.parametrize("text", ["F-1 and F-11 differ", "F-1 a lot", "well F-12 on the day"])
def test_a_following_word_is_not_a_sidetrack_letter(text):
    assert canonical_well(text) in ("15/9-F-1", "15/9-F-12")


@pytest.mark.parametrize("text", ["2014-03-14", "14 March 2014", "March 14th, 2014", "March 14, 2014", "14/03/2014",
                                  "14.03.2014", "14th of March 2014", "the report of 14 Mar 2014", "03/14/2014"])
def test_date_phrasings(text):
    assert [d.iso for d in find_dates(f"What did the well do on {text}?")] == ["2014-03-14"]


def test_numbers_that_are_not_dates_are_ignored():
    assert find_dates("Depth 1.420 m, 15/9-19 A, 3.5 in") == []


@needs_data
def test_the_32_published_questions_route_exactly_as_before():
    fx = json.loads(FIXTURE.read_text())
    now = route.route_all()
    assert set(now["question_id"]) == set(fx)
    for _, r in now.iterrows():
        f = fx[r.question_id]
        assert (r["mode"], bool(r.early_abstain), [x.strip() for x in r.candidate_files.split(";") if x.strip()]) \
            == (f["mode"], f["early_abstain"], f["candidate_files"]), r.question_id


# ---- the guarantee: 32 published questions, no key, no network ----------------------------------------------


@needs_data
def test_32_questions_without_any_key_are_byte_identical_and_open_no_socket(monkeypatch, tmp_path, located):
    import requests

    def no_socket(*a, **k):
        raise AssertionError("a network socket was opened")

    monkeypatch.setattr(socket, "socket", no_socket)
    monkeypatch.setattr(socket, "create_connection", no_socket)
    monkeypatch.setattr(requests, "post", no_socket)
    assert L.find_key() == (None, None)                                   # conftest cleared every variable and .env
    reports = discover_reports(config.XML_DIR)
    questions = pipeline.read_questions(None)
    assert len(questions) == 32
    client = LLM.from_env(runtime_cache_path=tmp_path / "runtime.json")
    assert client.backend is None
    answers = A.answer_all(questions, located, reports, client, dump=False, strict=True)    # strict: any CacheMiss raises
    assert not [a for a in answers if a.status == "not_evaluated"] and client.live_calls == 0
    out = write.write_predictions(answers, located, tmp_path / "predictions.csv")
    committed = config.PREDICTIONS_PATH.read_bytes()
    assert hashlib.md5(out.read_bytes()).hexdigest() == hashlib.md5(committed).hexdigest()
    assert out.read_bytes() == committed
    rep = write.validate_predictions(predictions_path=out)
    assert rep["valid"], rep
    assert not (tmp_path / "runtime.json").exists() or not json.loads((tmp_path / "runtime.json").read_text()).get("entries")


# ---- 7a: well variants and date pairing --------------------------------------------------------------------


@needs_data
@pytest.mark.parametrize("w", ["F-1B", "F-1 B", "F-1-B", "15/9-F-1 B", "NO 15/9-F-1 B", "15_9_F_1_B", "f-1b"])
def test_each_date_pairs_with_the_report_for_its_own_wellbore(w):
    q = f"Compare the last casing depth in the 24 September 2013 report for {w} with that in the 2013-08-12 report for F-1: which was deeper?"
    r = route.route_question(q, discover_reports(config.XML_DIR))
    assert r.wells == ["15/9-F-1-B", "15/9-F-1"]
    assert "UNMATCHED" not in r.reason
    assert {"15_9_F_1_B_2013_09_24", "15_9_F_1_2013_08_12"} <= set(r.candidate_files)


@needs_data
def test_well_before_date_pairing_is_unchanged():
    q = "What changed between F-11-B (2013-05-29) and F-1-B (2013-08-30)?"
    r = route.route_question(q, discover_reports(config.XML_DIR))
    assert {"15_9_F_11_B_2013_05_29", "15_9_F_1_B_2013_08_30"} <= set(r.candidate_files) and "UNMATCHED" not in r.reason


# ---- 7b-7d: computed aggregates, second pass, generic absence ----------------------------------------------

import re  # noqa: E402

from submission.archive_qa import enrich  # noqa: E402
from submission.archive_qa.context import build_context  # noqa: E402

CONTEXTS_32 = Path(__file__).parent / "fixtures" / "contexts_32.json"


@pytest.fixture(scope="module")
def reps():
    return discover_reports(config.XML_DIR)


def ctx_for(q, records, reps, **kw):
    return build_context("X", q, route.route_question(q, reps), records, **kw)


@needs_data
def test_the_contexts_of_the_32_are_byte_identical(located, reps):
    fx = json.loads(CONTEXTS_32.read_text())
    for q in route.load_questions().itertuples():
        r = route.route_question(q.question_text, reps)
        if r.early_abstain:
            assert q.question_id not in fx
            continue
        c = build_context(q.question_id, q.question_text, r, located)
        assert hashlib.sha256(c.text.encode()).hexdigest() == fx[q.question_id]["sha256"], q.question_id
        assert len(c.ids) == fx[q.question_id]["n_ids"] and not c.agg


def test_intent_detection_is_generic():
    assert enrich.intents("How many reports state that depth?") == {"count"}
    assert "extremum" in enrich.intents("What is the deepest casing?")
    assert "compare" in enrich.intents("Was it higher in A or B?")
    assert enrich.intents("What was the density of the brine?") == set()


@pytest.mark.parametrize("field,q,ok", [
    ("waterDepth", "What is the smallest water depth in the archive?", True),
    ("mdCsgLast", "the deepest last-casing measured depth", True),
    ("elevKelly", "the Kelly bushing elevation", True),
    ("mdKickoff", "the kick-off depth", True),
    ("dateDrillComplete", "the date drilling was completed", True),
    ("md", "any depth at all", False),                  # a bare abbreviation never matches on its own
    ("waterDepth", "the casing depth", False),
])
def test_field_names_match_the_questions_words(field, q, ok):
    assert enrich.field_matches(field, q) is ok


@needs_data
def test_aggregates_are_computed_in_code_from_the_records(located, reps):
    c = ctx_for("What is the smallest water depth recorded anywhere in the archive, and how many reports state that depth?", located, reps)
    rows = located[(located["field"] == "waterDepth") & ~located["missing"]]
    agg = c.agg["AGG-00000000-WATERDEPTH"]
    lo = rows["value_num"].min()
    text = agg["text"]
    assert f"count={len(rows)}" in text and f"min={int(lo)} m in {int((rows['value_num'] == lo).sum())} record(s)" in text
    assert set(agg["sources"]) >= set(rows[rows["value_num"] == lo]["record_id"]) | set(rows[rows["value_num"] == rows["value_num"].max()]["record_id"])
    assert all(rid in c.ids for rid in agg["sources"])                      # the table's real records are in the context
    assert "IDX-00000000-WELLBORES" in c.agg and f"wellbores={located['well'].nunique()}" in c.agg["IDX-00000000-WELLBORES"]["text"]


@needs_data
def test_aggregates_only_for_multi_report_questions_that_ask_for_them(located, reps):
    single = ctx_for("What was the water depth for well F-1C in the report dated 2016-10-22?", located, reps)
    assert not single.agg
    multi_plain = ctx_for("On which report days was the water depth stated across F-1 and F-12?", located, reps)
    assert not multi_plain.agg                                              # no count / extremum / comparison asked
    assert ctx_for("Which has the larger water depth, F-1 or F-12?", located, reps).agg


def _by_script(second=None):
    def script(system, user, model):
        if "FIELD CATALOGUE" in user:
            return second(user) if second else {"status": "abstain", "answer": "", "cited_ids": [], "rationale": "r"}
        return {"status": "abstain", "answer": "", "cited_ids": [], "rationale": "first pass found nothing"}
    return script


def _llm(tmp_path, script):
    fake = FakeLLM(script)
    return LLM(LLMConfig(primary="m1", escalation="m2", live=True, concurrency=1), fake, Cache(tmp_path / "c.json"), tmp_path / "l.csv"), fake


Q_ARCH = "What is the smallest water depth recorded anywhere in the archive?"


@needs_data
def test_second_pass_runs_once_on_a_multi_question_that_abstained_and_is_traced(tmp_path, located, reps):
    def second(user):
        m = re.search(r"\[(\w+-\d{8}-STATUS-WATERDEPTH)\][^\n]*waterDepth=(\d+)", user)
        return {"status": "answered", "answer": f"{m[2]} m", "cited_ids": [m[1]], "rationale": "from the field table"}
    llm, fake = _llm(tmp_path, _by_script(second))
    a = A.answer_question("S-1", Q_ARCH, located, reps, llm, dump=False)
    assert a.trace_mode == "second_pass" and a.status == "answered" and a.verified
    assert any("second pass" in n for n in a.notes)
    assert sum("FIELD CATALOGUE" in c["user"] for c in fake.calls) >= 1
    assert all(re.fullmatch(r"\w+-\d{8}-[\w-]+", c) for c in a.cited_ids)


@needs_data
def test_second_pass_keeps_the_first_answer_when_it_does_not_improve(tmp_path, located, reps):
    llm, fake = _llm(tmp_path, _by_script(None))
    a = A.answer_question("S-2", Q_ARCH, located, reps, llm, dump=False)
    assert a.trace_mode == "normal" and a.status == "abstain"
    assert any("first pass is kept" in n for n in a.notes)


@needs_data
def test_second_pass_never_runs_for_single_report_questions_or_known_absent_fields(tmp_path, located, reps):
    llm, fake = _llm(tmp_path, _by_script(None))
    A.answer_question("S-3", "What was the water depth for well 15/9-F-1-C in the report dated 2014-03-26?", located, reps, llm, dump=False)
    A.answer_question("S-4", "What was the total daily spread cost for well 15/9-F-1-C across all reports in the archive?", located, reps, llm, dump=False)
    assert not any("FIELD CATALOGUE" in c["user"] for c in fake.calls)


@needs_data
def test_a_cited_aggregate_is_replaced_by_its_source_records(tmp_path, located, reps):
    def script(system, user, model):
        return {"status": "answered", "answer": "The smallest water depth is 84 m.", "cited_ids": ["AGG-00000000-WATERDEPTH"], "rationale": "r"}
    llm, _ = _llm(tmp_path, script)
    a = A.answer_question("S-5", Q_ARCH, located, reps, llm, dump=False)
    assert a.status == "answered" and a.verified, (a.failures, a.notes)
    assert a.cited_ids and all(i in set(located["record_id"]) for i in a.cited_ids)
    assert "AGG-00000000-WATERDEPTH" not in write.build_evidence(a, located)


@needs_data
def test_an_aggregate_cannot_support_a_number_it_does_not_state(tmp_path, located, reps):
    def script(system, user, model):
        return {"status": "answered", "answer": "The smallest water depth is 77 m.", "cited_ids": ["AGG-00000000-WATERDEPTH"], "rationale": "r"}
    llm, _ = _llm(tmp_path, script)
    a = A.answer_question("S-6", Q_ARCH, located, reps, llm, dump=False)
    assert not a.verified and any("77" in f for f in a.failures)


@needs_data
def test_generic_absence_record_when_no_term_occurs_and_not_otherwise(located, reps):
    c = ctx_for("How many helicopter flights were made to the rig for well 15/9-F-1-B on 2014-01-29?", located, reps)
    assert "ABSENT-search" in c.absent and "helicopter" in c.absent["ABSENT-search"]["kind"]
    assert "[ABSENT-search]" in c.text and "none occurs" in c.text
    # answerable questions, including word forms that differ from the field names, get no such record
    for q in ["On what date was well 15/9-F-1 spudded, according to the 2013-07-30 report?",
              "According to the report of 2015-08-10 for well 15/9-F-15-D, what was the date drilling was completed?",
              "What was the report number of the 2013-11-11 daily drilling report for 15/9-F-15-D?"]:
        assert "ABSENT-search" not in ctx_for(q, located, reps).absent, q
    # existing field-kind ABSENT records are unchanged and not doubled
    w = ctx_for("What weather and sea state were recorded for well 15/9-F-15-D on 2013-12-14?", located, reps)
    assert "ABSENT-weather" in w.absent and "ABSENT-search" not in w.absent


@needs_data
def test_a_field_whose_name_matches_brings_its_section_into_a_single_report_context(located, reps):
    c = ctx_for("According to the report of 2015-08-10 for well 15/9-F-15-D, what was the date drilling was completed?", located, reps)
    assert "dateDrillComplete" in c.text
