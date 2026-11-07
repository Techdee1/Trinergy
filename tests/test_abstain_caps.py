"""Abstain citations are set in code before verification; multi/archive_wide start at the retry cap. FakeLLM only."""
import pytest

from submission.archive_qa import answer as A
from submission.archive_qa.context import Context
from submission.archive_qa.route import load_questions
from submission.archive_qa.write import build_evidence
from tests.conftest import needs_data
from tests.test_answer import FLUID, good, make
from tests.test_retry import TRUNC, go


@pytest.fixture(scope="module")
def qtext():
    return load_questions().set_index("question_id")["question_text"]


def abstain(cited, answer=""):
    return {"status": "abstain", "answer": answer, "cited_ids": cited, "rationale": "not in the lines"}


# ---- step 2: abstain citations ----------------------------------------------------------------------------------


def test_normalise_reply_is_a_copy_and_only_touches_abstain():
    ctx = Context("T", "", frozenset({"A-1", "ABSENT-cost", "ABSENT-weather"}),
                  {"ABSENT-weather": {"kind": "weather"}, "ABSENT-cost": {"kind": "cost"}})
    original = abstain(["A-1", "BOGUS"])
    out = A.normalise_reply(original, ctx)
    assert out["cited_ids"] == ["ABSENT-cost", "ABSENT-weather"] and original["cited_ids"] == ["A-1", "BOGUS"]
    assert A.normalise_reply(abstain(["A-1"]), Context("T", "", frozenset({"A-1"})))["cited_ids"] == []   # none present -> empty
    answered = good(cited_ids=["A-1"])
    assert A.normalise_reply(answered, ctx) is answered                                                     # untouched
    partial = {"status": "partial", "answer": "x", "cited_ids": ["A-1"], "rationale": "r"}
    assert A.normalise_reply(partial, ctx) is partial
    bad = {"__unparsed__": "{"}
    assert A.normalise_reply(bad, ctx) is bad


@needs_data
@pytest.mark.parametrize("cited", [
    ["F1C-20140326-SUM-SUM24HR", "F1C-20140326-FCST-FORECAST24HR", "ABSENT-cost"],   # real records mixed in
    ["F1C-20140326-ABSENT-cost"],                                                      # malformed ABSENT id
    ["INVENTED-20140326-X-01"],                                                        # invented id
    [],
])
def test_abstain_citing_anything_is_normalised_so_no_escalation(tmp_path, qtext, reports, located, cited):
    a, fake, llm = go(tmp_path, lambda s, u, m: abstain(cited), "T2-025", qtext, reports, located)
    assert [c["model"] for c in fake.calls] == ["m1", "m1"]                    # verified first time: no Sonnet call
    assert a.verified and a.status == "abstain" and a.confidence == 0.85
    assert a.cited_ids == ["ABSENT-cost"] and list(a.absent) == ["ABSENT-cost"]
    assert not any("escalated" in n or "VERIFIER FAILED" in n for n in a.notes)
    ev = build_evidence(a, located)
    assert ev.startswith("ABSENT-cost:") and "SUM24HR" not in ev and "INVENTED" not in ev
    assert "Searched 1 report(s) and" in a.rationale


@needs_data
def test_abstain_without_an_absent_record_cites_nothing(tmp_path, qtext, reports, located):
    # density exists in the report, so there is no ABSENT record; whatever the model cited on the abstain is dropped.
    # (An abstain with a matching line may be escalated once by policy; that is a separate rule.)
    a, fake, _ = go(tmp_path, lambda s, u, m: abstain([FLUID]), "T2-016", qtext, reports, located)
    assert a.cited_ids == [] and not a.absent and a.verified


@needs_data
def test_cache_keeps_the_models_original_reply(tmp_path, qtext, reports, located):
    a, fake, llm = go(tmp_path, lambda s, u, m: abstain(["F1C-20140326-SUM-SUM24HR"]), "T2-025", qtext, reports, located)
    stored = [e["response"]["cited_ids"] for e in llm.cache.entries.values()]
    assert stored == [["F1C-20140326-SUM-SUM24HR"]] * 2 and a.cited_ids == ["ABSENT-cost"]


@needs_data
def test_answered_and_partial_keep_the_models_citations(tmp_path, qtext, reports, located):
    a, _, _ = go(tmp_path, lambda s, u, m: good(), "T2-016", qtext, reports, located)
    assert a.cited_ids == [FLUID] and not a.absent


# ---- step 3: start caps -------------------------------------------------------------------------------------------


@needs_data
def test_single_report_keeps_400_and_multi_modes_start_at_1500(tmp_path, qtext, reports, located):
    seen = {}
    for qid in ("T2-016", "T2-024", "T2-020"):       # single_report, multi_report, archive_wide
        a, fake, _ = go(tmp_path / qid, lambda s, u, m: good(), qid, qtext, reports, located)
        seen[qid] = (a.mode, [c["max_tokens"] for c in fake.calls[:2]])
    assert seen == {"T2-016": ("single_report", [400, 400]), "T2-024": ("multi_report", [1500, 1500]),
                    "T2-020": ("archive_wide", [1500, 1500])}


@needs_data
def test_multi_truncated_at_the_retry_cap_is_not_retried_again(tmp_path, qtext, reports, located):
    def script(system, user, model, max_tokens):
        return TRUNC if model == "m1" else good()

    a, fake, _ = go(tmp_path, script, "T2-024", qtext, reports, located)
    assert [(c["model"], c["max_tokens"]) for c in fake.calls] == [("m1", 1500), ("m1", 1500), ("m2", 1500)]
    assert not any("retried" in n for n in a.notes) and any("escalated to m2" in n for n in a.notes)


@needs_data
def test_single_truncated_at_400_still_retries_at_1500(tmp_path, qtext, reports, located):
    def script(system, user, model, max_tokens):
        return TRUNC if max_tokens == 400 else good()

    a, fake, _ = go(tmp_path, script, "T2-016", qtext, reports, located)
    assert [c["max_tokens"] for c in fake.calls] == [400, 1500, 400, 1500] and a.verified


@needs_data
def test_start_cap_keys_are_separate_cache_entries(tmp_path, qtext, reports, located):
    _, fake, llm = go(tmp_path, lambda s, u, m: good(), "T2-024", qtext, reports, located)
    primaries = [e for e in llm.cache.entries.values() if e["role"] != "escalation"]
    assert sorted(e["role"] for e in primaries) == ["primary", "primary_run2"]        # run 1 and run 2, each its own entry
    assert [c["max_tokens"] for c in fake.calls[:2]] == [1500, 1500]
    assert A.start_cap(llm, "single_report") is None and A.start_cap(llm, "multi_report") == 1500
