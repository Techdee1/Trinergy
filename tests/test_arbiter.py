"""Run-disagreement comparison (question echoes excluded) and the Sonnet arbiter. FakeLLM only."""
import pytest

from submission.archive_qa import answer as A
from submission.archive_qa.answer import key_tokens, runs_differ
from submission.archive_qa.route import load_questions
from tests.conftest import needs_data
from tests.test_answer import FLUID, good, make
from tests.test_retry import go

OTHER = good(answer="The NaCl brine density was 1.05 g/cm3.")
ARBITER_OK = good(answer="Density 1.03 g/cm3 (NaCl brine, active pit).")
ARBITER_BAD = good(answer="The density was 9.99 g/cm3.")


@pytest.fixture(scope="module")
def qtext():
    return load_questions().set_index("question_id")["question_text"]


def by_model(run_replies, arbiter):
    it = iter(run_replies)
    return lambda s, u, m: arbiter if m == "m2" else next(it)


# ---- comparison -----------------------------------------------------------------------------------------------------


def test_numbers_that_echo_the_question_do_not_count():
    q = 'On well 15/9-F-12 on 2007-06-14, to what depth was the 36" hole opener BHA run in hole?'
    a = {"status": "answered", "answer": '85 m MD (the 36" hole opener BHA was run in hole to 85 m MD)'}
    b = {"status": "answered", "answer": "85 m MD"}
    assert runs_differ(a, b) and not runs_differ(a, b, q)                      # only the echoed 36 differed
    assert runs_differ(a, {**b, "answer": "86 m MD"}, q)                       # a genuine difference still counts
    assert key_tokens(a["answer"], q) == {"n:85"}


def test_times_are_compared_as_whole_tokens_and_date_digits_never_count():
    assert key_tokens("Landed 2013-12-13T19:15:00 (report 2013-12-14)") == {"t:19:15"}
    assert key_tokens("between 19:15 and 24:00") == {"t:19:15", "t:24:00"}
    assert not runs_differ({"status": "answered", "answer": "at 19:15 on 2013-12-13"},
                           {"status": "answered", "answer": "at 2013-12-13T19:15:00 (report 2013-12-14)"})
    assert runs_differ({"status": "answered", "answer": "at 19:15"}, {"status": "answered", "answer": "at 19:20"})
    assert key_tokens("19:15", "from 19:15 to 23:45") == set()                  # a time echoed from the question


def test_enumerators_are_not_key_numbers():
    assert key_tokens("Two days. (1) a at 2800 m. (2) b at 3570 m.") == {"n:2800", "n:3570"}


def test_status_difference_counts_even_without_numbers():
    assert runs_differ({"status": "answered", "answer": "x"}, {"status": "partial", "answer": "x"})


# ---- arbiter: both branches -------------------------------------------------------------------------------------------


@needs_data
def test_arbiter_answer_that_verifies_is_committed(tmp_path, qtext, reports, located):
    a, fake, llm = go(tmp_path, by_model([good(), OTHER], ARBITER_OK), "T2-016", qtext, reports, located)
    assert [c["model"] for c in fake.calls] == ["m1", "m1", "m2"]                      # exactly one arbiter call
    assert "9.99" not in a.answer and a.answer == ARBITER_OK["answer"]                # the arbiter's answer is committed
    assert a.verified and not a.disagree and not a.needs_review and a.confidence == 0.95
    assert a.llm_calls == 3 and a.model == "m2"
    assert any("arbitrated by m2" in n and "verified answer is committed" in n for n in a.notes)
    assert not any("REVIEW" in n or "VERIFIER FAILED" in n for n in a.notes)
    # the arbiter ran with the ESCALATION settings and saw both runs
    arb = fake.calls[2]
    assert arb["max_tokens"] == 1500 and arb["reasoning"] == "minimal"
    assert "ARBITRATION" in arb["user"] and "Run A" in arb["user"] and "Run B" in arb["user"]
    assert "1.03" in arb["user"] and "1.05" in arb["user"]


@needs_data
def test_arbiter_answer_that_fails_verification_keeps_run_one_with_a_review_note(tmp_path, qtext, reports, located):
    a, fake, _ = go(tmp_path, by_model([good(), OTHER], ARBITER_BAD), "T2-016", qtext, reports, located)
    assert [c["model"] for c in fake.calls] == ["m1", "m1", "m2", "m2"]                # arbiter + ONE retry, never a third
    assert a.answer == good()["answer"] and a.model == "m1"                           # run 1, unchanged
    assert a.disagree and a.needs_review and a.verified                               # run 1 itself verified
    note = next(n for n in a.notes if n.startswith("REVIEW: runs disagree"))
    assert "failed verification twice" in note and "kept run 1" in note and "only in run 2" in note


@needs_data
def test_no_arbiter_when_runs_agree_or_only_differ_by_question_numbers(tmp_path, qtext, reports, located):
    a, fake, _ = go(tmp_path, lambda s, u, m: good(), "T2-016", qtext, reports, located)
    assert [c["model"] for c in fake.calls] == ["m1", "m1"] and not a.disagree
    worded = good(answer="1.03 g/cm3 (NaCl brine, active pit, sampled 2014-03-25T21:00:00).")
    a, fake, _ = go(tmp_path / "w", by_model([good(), worded], ARBITER_OK), "T2-016", qtext, reports, located)
    assert [c["model"] for c in fake.calls] == ["m1", "m1"] and not a.disagree


@needs_data
def test_echoed_question_number_does_not_trigger_the_arbiter(tmp_path, qtext, reports, located):
    sid = "F12-20070614-SUM-SUM24HR"
    r1 = {"status": "answered", "answer": '85 m MD (the 36" hole opener BHA was run in hole to 85 m MD)',
          "cited_ids": [sid], "rationale": "r"}
    r2 = {**r1, "answer": "85 m MD"}
    a, fake, _ = go(tmp_path, by_model([r1, r2], ARBITER_BAD), "T2-007", qtext, reports, located)
    assert [c["model"] for c in fake.calls] == ["m1", "m1"] and not a.disagree and a.verified


@needs_data
def test_status_difference_goes_to_the_arbiter(tmp_path, qtext, reports, located):
    partial = {"status": "partial", "answer": "Only 1.03 g/cm3.", "cited_ids": [FLUID], "rationale": "r"}
    a, fake, _ = go(tmp_path, by_model([good(), partial], ARBITER_OK), "T2-016", qtext, reports, located)
    assert [c["model"] for c in fake.calls] == ["m1", "m1", "m2"] and a.model == "m2" and not a.disagree


# ---- never a second Sonnet call; replay ----------------------------------------------------------------------------------


@needs_data
def test_a_failing_run_one_uses_the_single_escalation_as_arbiter(tmp_path, qtext, reports, located):
    bad_first = good(answer="The density was 9.99 g/cm3.")                           # run 1 fails verification
    a, fake, _ = go(tmp_path, by_model([bad_first, OTHER], ARBITER_OK), "T2-016", qtext, reports, located)
    assert [c["model"] for c in fake.calls] == ["m1", "m1", "m2"]                    # one Sonnet call, not two
    assert a.verified and not a.disagree and a.answer == ARBITER_OK["answer"]
    assert any("resolved by the escalation answer" in n for n in a.notes)
    # escalation also fails: still one call, flagged for review
    b, fake, _ = go(tmp_path / "b", by_model([bad_first, OTHER], ARBITER_BAD), "T2-016", qtext, reports, located)
    assert [c["model"] for c in fake.calls] == ["m1", "m1", "m2"] and b.disagree and not b.verified


@needs_data
def test_arbitration_replays_offline_from_the_cache(tmp_path, qtext, reports, located):
    from submission.archive_qa.llm import LLM, Cache, LLMConfig

    live, fake, _ = go(tmp_path, by_model([good(), OTHER], ARBITER_OK), "T2-016", qtext, reports, located)
    offline = LLM(LLMConfig(primary="m1", escalation="m2", live=False), None, Cache(tmp_path / "c.json"), tmp_path / "l2.csv")
    again = A.answer_question("T2-016", qtext["T2-016"], located, reports, offline, dump=False)
    assert (again.answer, again.model, again.disagree, again.notes) == (live.answer, live.model, live.disagree, live.notes)
    assert offline.live_calls == 0 and offline.cache_hits == 3


# ---- arbiter retry: told what the verifier rejected, once --------------------------------------------------------


@needs_data
def test_a_failed_arbiter_is_retried_once_with_the_verifier_message_and_the_retry_is_committed(tmp_path, qtext, reports, located):
    seq, m2 = iter([good(), OTHER]), {"n": 0}

    def script(system, user, model):
        if model == "m2":                       # the arbiter: bad the first time, good once it has been told why
            m2["n"] += 1
            return ARBITER_BAD if m2["n"] == 1 else ARBITER_OK
        return next(seq)

    a, fake, _ = go(tmp_path, script, "T2-016", qtext, reports, located)
    assert [c["model"] for c in fake.calls] == ["m1", "m1", "m2", "m2"]
    first_try, retry = fake.calls[2]["user"], fake.calls[3]["user"]
    assert "ARBITRATION" in first_try and "Your previous arbitration answer failed these checks" not in first_try
    assert "Your previous arbitration answer failed these checks" in retry and "9.99" in retry     # the verifier's message
    assert a.verified and not a.disagree and a.model == "m2" and a.answer == ARBITER_OK["answer"]
    assert any("retried" in n and "verifier's message" in n for n in a.notes)
    assert any("arbitrated by m2 (second attempt)" in n for n in a.notes)


@needs_data
def test_the_arbiter_retry_is_not_repeated_and_a_verified_first_arbiter_needs_no_retry(tmp_path, qtext, reports, located):
    a, fake, _ = go(tmp_path, by_model([good(), OTHER], ARBITER_OK), "T2-016", qtext, reports, located)
    assert [c["model"] for c in fake.calls] == ["m1", "m1", "m2"] and not any("retried" in n for n in a.notes)
    b, fake, _ = go(tmp_path / "b", by_model([good(), OTHER], ARBITER_BAD), "T2-016", qtext, reports, located)
    assert [c["model"] for c in fake.calls].count("m2") == 2 and b.disagree
