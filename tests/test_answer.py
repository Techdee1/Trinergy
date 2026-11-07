"""Answerer + verifier with FakeLLM. No network, no spend."""
import pytest

from submission.archive_qa import answer as A
from submission.archive_qa.context import Context
from submission.archive_qa.llm import LLM, Cache, FakeLLM, LLMConfig
from submission.archive_qa.route import load_questions
from submission.archive_qa.verify import confidence, verify
from submission.archive_qa.write import build_evidence
from tests.conftest import needs_data

FLUID = "F1C-20140326-FLUID-01"


def make(tmp_path, script):
    fake = FakeLLM(script)
    cfg = LLMConfig(primary="m1", escalation="m2", live=True, concurrency=1)
    return LLM(cfg, fake, Cache(tmp_path / "c.json"), tmp_path / "l.csv"), fake


def good(**kw):
    d = {"status": "answered", "cited_ids": [FLUID], "rationale": "r",
         "answer": "The NaCl brine density was 1.03 g/cm3 (sampled 2014-03-25T21:00:00, report 2014-03-26)."}
    d.update(kw)
    return d


@pytest.fixture(scope="module")
def qtext():
    return load_questions().set_index("question_id")["question_text"]


# ---- verifier ------------------------------------------------------------------------------------


def ctx(ids, absent=()):
    return Context("T", "", frozenset(ids) | frozenset(absent), {a: {"kind": "cost"} for a in absent})


@needs_data
def test_verifier_rejects_invented_id(located):
    r = verify(good(cited_ids=[FLUID, "F1C-20140326-FLUID-99"]), ctx([FLUID]), located)
    assert not r.ok and any("never invent IDs" in f and "FLUID-99" in f for f in r.failures)


@needs_data
def test_verifier_rejects_unsupported_number(located):
    r = verify(good(answer="The density was 1.05 g/cm3."), ctx([FLUID]), located)
    assert not r.ok and any("1.05" in f for f in r.failures)


@needs_data
def test_verifier_accepts_supported_and_derived_numbers(located):
    assert verify(good(), ctx([FLUID]), located).ok
    # md=4094 and presBopRating=345 are in the record: their sum, difference and mean are allowed
    for ans in ("Total 4439 m.", "Difference 3749 m.", "Mean 2219.5 m."):
        assert verify(good(answer=ans), ctx([FLUID]), located).ok, ans
    assert not verify(good(answer="Total 4440 m."), ctx([FLUID]), located).ok


@needs_data
def test_verifier_unit_mismatch(located):
    r = verify(good(answer="The density was 1.03 bar."), ctx([FLUID]), located)
    assert not r.ok and any("unit mismatch" in f for f in r.failures)
    assert verify(good(answer="The density was 1.03 sg."), ctx([FLUID]), located).ok


@needs_data
def test_verifier_structure_rules(located):
    assert not verify({"__unparsed__": "x"}, ctx([FLUID]), located).ok
    assert not verify(good(status="maybe"), ctx([FLUID]), located).ok
    assert not verify(good(cited_ids=[]), ctx([FLUID]), located).ok              # answered needs a citation
    assert not verify(good(cited_ids=["ABSENT-cost"]), ctx([FLUID], ["ABSENT-cost"]), located).ok
    r = verify(good(status="abstain", answer="Not available."), ctx([FLUID], ["ABSENT-cost"]), located)
    assert not r.ok and "only ABSENT" in r.message                                # abstention cites ABSENT only
    ok = verify({"status": "abstain", "answer": "No cost field.", "cited_ids": ["ABSENT-cost"], "rationale": "r"},
                ctx([FLUID], ["ABSENT-cost"]), located)
    assert ok.ok
    several = verify(good(answer="x 1.05 y 1.07"), ctx([FLUID]), located)          # all failures are collected
    assert not several.ok and "1.05" in several.message and "1.07" in several.message


def test_confidence_rules():
    c = confidence
    assert c("answered", 1, "single_report", True) == 0.95 and c("answered", 1, "multi_report", True) == 0.9
    assert c("answered", 3, "single_report", True) == 0.8 and c("answered", 6, "multi_report", True) == 0.7
    assert 0.4 <= c("partial", 2, "single_report", True) <= 0.6
    assert c("abstain", 0, "single_report", True, early_abstain=True) == 0.9
    assert c("abstain", 0, "single_report", True, absent_cited=True) == 0.85
    assert 0.75 <= c("abstain", 0, "single_report", True) <= 0.85
    assert c("answered", 1, "single_report", False) == 0.2


# ---- answerer --------------------------------------------------------------------------------------


@needs_data
def test_answered_with_evidence_format(tmp_path, qtext, located, reports):
    llm, fake = make(tmp_path, lambda s, u, m: good())
    a = A.answer_question("T2-016", qtext["T2-016"], located, reports, llm, dump=False)
    assert (a.status, a.verified, a.confidence, a.llm_calls, len(fake.calls)) == ("answered", True, 0.95, 1, 1)
    ev = build_evidence(a, located)
    assert ev.endswith(f"15_9_F_1_C_2014_03_26.xml {FLUID}")
    assert ev.split(";")[0].startswith("15_9_F_1_C_2014_03_26.pdf p.") and "(Drilling Fluid)" in ev


@needs_data
def test_early_abstain_makes_zero_llm_calls(tmp_path, qtext, located, reports):
    llm, fake = make(tmp_path, lambda s, u, m: pytest.fail("LLM must not be called"))
    a = A.answer_question("T2-027", qtext["T2-027"], located, reports, llm, dump=False)
    assert fake.calls == [] and a.early_abstain and a.status == "abstain" and a.confidence == 0.9
    assert "15/9-F-14" in a.answer and "not answerable" in a.answer.lower()
    ev = build_evidence(a, located)
    assert ev.startswith("Checked document_manifest.csv: 32 daily reports, 8 wellbores")
    assert ".pdf" not in ev and "FLUID" not in ev  # no fake citation
    b = A.answer_question("T2-029", qtext["T2-029"], located, reports, llm, dump=False)
    assert fake.calls == [] and "2013-12-14" in b.answer and "1 day(s) away" in b.answer


@needs_data
def test_abstention_cites_only_absent_records(tmp_path, qtext, located, reports):
    reply = {"status": "abstain", "answer": "The archive has no cost field.", "cited_ids": ["ABSENT-cost"],
             "rationale": "checked"}
    llm, fake = make(tmp_path, lambda s, u, m: reply)
    a = A.answer_question("T2-025", qtext["T2-025"], located, reports, llm, dump=False)
    assert a.status == "abstain" and a.verified and a.confidence == 0.85 and a.cited_ids == ["ABSENT-cost"]
    ev = build_evidence(a, located)
    assert "ABSENT-cost" in ev and "no cost field exists" in ev and "15_9_F_1_C_2014_03_26.xml" in ev
    assert "FLUID" not in ev and "ACT-" not in ev


@needs_data
def test_escalation_after_verifier_failure_passes_feedback(tmp_path, qtext, located, reports):
    def script(system, user, model):
        if model == "m1":
            return good(cited_ids=["F1C-20140326-FLUID-77"])      # invented ID
        assert "VERIFIER FEEDBACK" in user and "FLUID-77" in user  # the verifier's message was passed on
        return good()

    llm, fake = make(tmp_path, script)
    a = A.answer_question("T2-016", qtext["T2-016"], located, reports, llm, dump=False)
    assert [c["model"] for c in fake.calls] == ["m1", "m2"]
    assert a.verified and a.confidence == 0.95 and a.llm_calls == 2 and a.model == "m2"
    assert any("escalated" in n for n in a.notes) and not any("VERIFIER FAILED" in n for n in a.notes)


@needs_data
def test_still_failing_keeps_answer_with_confidence_02(tmp_path, qtext, located, reports):
    bad = good(answer="The density was 9.99 g/cm3.")
    llm, fake = make(tmp_path, lambda s, u, m: bad)
    a = A.answer_question("T2-016", qtext["T2-016"], located, reports, llm, dump=False)
    assert len(fake.calls) == 2 and not a.verified and a.confidence == 0.2
    assert "9.99" in a.answer                                   # the answer is NOT silently changed
    assert any(n.startswith("VERIFIER FAILED:") and "9.99" in n for n in a.notes) and a.needs_review


@needs_data
def test_invented_ids_never_reach_the_evidence_string(tmp_path, qtext, located, reports):
    llm, _ = make(tmp_path, lambda s, u, m: good(cited_ids=[FLUID, "NOPE-20000101-X-01"]))
    a = A.answer_question("T2-016", qtext["T2-016"], located, reports, llm, dump=False)
    assert "NOPE" not in build_evidence(a, located) and "NOPE" not in "".join(a.cited_ids)
