"""New answering rules: date-window note, derived-value rule, abstain flag, multi-part check, escalation policy,
disagreement flag, early abstain, mud-logging ABSENT record. FakeLLM only: no network, no spend."""
import json

import pandas as pd
import pytest

from submission.archive_qa import answer as A
from submission.archive_qa.context import Context, build_context, in_date_window, window_note
from submission.archive_qa.route import find_times, load_questions, route_question
from submission.archive_qa.store import has_field
from submission.archive_qa.verify import (matching_evidence, says_derived, split_parts, unaddressed_parts, verify)
from submission.archive_qa.write import answer_notes, save_answers_json
from tests.conftest import needs_data
from tests.test_answer import FLUID, good, make

Q16 = "What was the density of the NaCl brine sampled from the active pit on well 15/9-F-1-C on 2014-03-26?"


def rec_df(rows):
    """Minimal records frame: (record_id, well, report_date, section, field, value, text)."""
    out = []
    for rid, well, day, section, fld, value, text in rows:
        num = float(value) if isinstance(value, (int, float)) else float("nan")
        out.append({"record_id": rid, "well": well, "report_date": day, "section": section, "field": fld,
                    "value": str(value), "value_num": num, "unit": "m", "attrs": None, "text": text})
    return pd.DataFrame(out)


def cx(ids, absent=None):
    absent = absent or {}
    return Context("T", "", frozenset(ids) | frozenset(absent), absent)


# ---- date window --------------------------------------------------------------------------------------------


def test_find_times():
    assert find_times("at 21:00 on 2014-03-26 and again at 9:05, not 12:60") == ["21:00", "09:05"]
    assert find_times("no clock time on 2014-03-26") == []


def test_in_date_window_needs_time_report_date_and_previous_day():
    ts, rd = "2014-03-25T21:00:00", "2014-03-26"
    assert in_date_window(ts, rd, ["21:00"], [rd])
    assert not in_date_window(ts, rd, [], [rd])                       # question names no clock time
    assert not in_date_window(ts, rd, ["22:00"], [rd])                # a different time
    assert not in_date_window(ts, rd, ["21:00"], ["2014-03-30"])      # question is about another date
    assert not in_date_window("2014-03-26T21:00:00", rd, ["21:00"], [rd])   # same day: nothing to explain
    assert not in_date_window(None, rd, ["21:00"], [rd])


def test_window_note_states_report_date_and_event_timestamp():
    n = window_note("F1C-20140326-FLUID-01", "2014-03-25T21:00:00", "2014-03-26", "2014-03-25T00:00:00", "2014-03-26T00:00:00")
    assert "2014-03-25T21:00:00" in n and "report 2014-03-26" in n and '"21:00 on 2014-03-26"' in n
    assert not n.startswith("[")                                      # a note, not a citeable record line


@needs_data
def test_context_adds_window_note_only_when_the_question_names_the_time(reports, located):
    q = "What was the density of the NaCl brine in the active pit at 21:00 on 2014-03-26 for well 15/9-F-1-C?"
    r = route_question(q, reports)
    assert r.event_times == ["21:00"]
    c = build_context("TX", q, r, located)
    lines = c.text.splitlines()
    i = next(k for k, l in enumerate(lines) if l.startswith(f"[{FLUID}]"))
    assert lines[i + 1].startswith("WINDOW NOTE:") and "2014-03-25T21:00:00" in lines[i + 1] and "report 2014-03-26" in lines[i + 1]
    assert FLUID in c.ids and not any(l.startswith("WINDOW NOTE") for l in build_context("T", Q16, route_question(Q16, reports), located).text.splitlines())


@needs_data
def test_window_note_reaches_the_model(tmp_path, reports, located):
    q = "What was the density of the NaCl brine in the active pit at 21:00 on 2014-03-26 for well 15/9-F-1-C?"
    llm, fake = make(tmp_path, lambda s, u, m: good())
    A.answer_question("T2-016", q, located, reports, llm, dump=False)
    assert "WINDOW NOTE: [F1C-20140326-FLUID-01]" in fake.calls[0]["user"]


# ---- derived-value rule -------------------------------------------------------------------------------------

CASING = rec_df([("X-20130812-CSG-01", "15/9-F-1", "2013-08-12", "casing", "length", 13.6, "Casing length 13.6 m"),
                 ("X-20130812-CSG-02", "15/9-F-1", "2013-08-12", "casing", "length", 12.34, "Casing length 12.34 m"),
                 ("X-20130812-CSG-03", "15/9-F-1", "2013-08-12", "casing", "length", 2410.35, "Casing length 2410.35 m")])
BOTH = ["X-20130812-CSG-01", "X-20130812-CSG-02"]


def derived(answer, rationale="r", cited=BOTH, extra=None):
    p = {"status": "answered", "answer": answer, "cited_ids": cited, "rationale": rationale}
    return verify(p, cx(CASING.record_id), CASING, "What is the combined length of the two joints?")


def test_says_derived():
    assert says_derived("The combined length is 25.94 m") and says_derived("difference of 18 m") and says_derived("13.6 + 12.34")
    assert not says_derived("The length is 13.6 m (record F1-20130812-CSG-01 on 2013-08-12)")   # IDs and dates are not cues


def test_derived_value_accepted_when_stated_derived_with_cited_operands():
    assert derived("The combined length is 25.94 m (13.6 m + 12.34 m).").ok
    assert derived("Total 25.94 m.", rationale="13.6 m plus 12.34 m").ok          # operands stated in the rationale
    assert derived("Mean joint length 12.97 m (13.6 and 12.34).").ok


def test_derived_value_rejected_without_the_derivation_cue():
    r = derived("25.94 m.", rationale="the sum of 13.6 m and 12.34 m")          # the ANSWER must say it is derived
    assert not r.ok and "25.94" in r.message


def test_derived_value_rejected_when_operands_not_stated():
    assert not derived("The combined length is 25.94 m.").ok


def test_derived_value_rejected_when_an_operand_is_not_cited():
    # 2410.35 is in the archive but the model did not cite that record: 2410.35 + 12.34 = 2422.69 is unsupported
    r = derived("The combined length is 2422.69 m (2410.35 m + 12.34 m).")
    assert not r.ok


def test_benchmark_coincidence_cases_are_rejected():
    # benchmark: wrong derived answers (26.0 for 25.94, 19 for 18) were accepted by the old pair-wise rule
    assert not derived("The combined length is 26.0 m (13.6 m + 12.34 m).").ok
    assert not derived("The combined length is 26.14 m (13.6 m + 12.34 m).").ok
    d = rec_df([("Y-20130824-ACT-01", "15/9-F-1", "2013-08-24", "activity", "md", 2602, "md=2602 m"),
                ("Y-20130824-ACT-03", "15/9-F-1", "2013-08-24", "activity", "md", 2620, "md=2620 m")])
    p = {"status": "answered", "cited_ids": ["Y-20130824-ACT-01", "Y-20130824-ACT-03"], "rationale": "r",
         "answer": "The depth increased by 19 m (2620 m - 2602 m)."}
    assert not verify(p, cx(d.record_id), d, "By how many metres did the depth increase?").ok
    p["answer"] = "The depth increased by 18 m (2620 m - 2602 m)."
    assert verify(p, cx(d.record_id), d, "By how many metres did the depth increase?").ok


def test_every_plain_number_must_appear_in_a_cited_line():
    assert not derived("The joint is 99 m long.", cited=["X-20130812-CSG-01"]).ok
    assert derived("The joint is 13.6 m long.", cited=["X-20130812-CSG-01"]).ok


# ---- abstain although a matching line exists -----------------------------------------------------------------

FL = rec_df([(FLUID, "15/9-F-1-C", "2014-03-26", "fluid", "density", 1.03,
              "density=1.03 g/cm3; type=NaCl brine; locationSample=Active pit")])
ABSTAIN = {"status": "abstain", "answer": "", "cited_ids": [], "rationale": "not found"}


def test_abstain_with_matching_line_is_flagged_not_failed():
    r = verify(ABSTAIN, cx(FL.record_id), FL, Q16)
    assert r.ok and r.flags and r.flagged_ids == [FLUID] and r.needs_escalation and FLUID in r.message


def test_abstain_flag_requires_well_date_and_field():
    c = cx(FL.record_id)
    assert matching_evidence(ABSTAIN, c, FL, Q16) == [FLUID]
    assert not matching_evidence(ABSTAIN, c, FL, Q16.replace("15/9-F-1-C", "15/9-F-12"))          # another well
    assert not matching_evidence(ABSTAIN, c, FL, Q16.replace("2014-03-26", "2014-03-30"))         # another date
    assert not matching_evidence(ABSTAIN, c, FL, "What was the casing shoe depth on well 15/9-F-1-C on 2014-03-26?")  # another field
    assert not matching_evidence({**ABSTAIN, "status": "answered"}, c, FL, Q16)                    # only abstentions
    assert matching_evidence(ABSTAIN, c, FL, Q16.replace("2014-03-26", "2014-03-25")) == [FLUID]  # D+1 fallback day


def test_abstain_is_not_flagged_when_the_archive_has_no_such_field():
    q = "What was the total daily spread cost for well 15/9-F-1-C on 2014-03-26?"
    c = cx(FL.record_id, {"ABSENT-cost": {"kind": "cost"}})
    assert not matching_evidence(ABSTAIN, c, FL, q)
    assert verify({"status": "abstain", "answer": "No cost field.", "cited_ids": ["ABSENT-cost"], "rationale": "r"},
                  c, FL, q).needs_escalation is False


# ---- multi-part questions ----------------------------------------------------------------------------------

MP = "For well 15/9-F-1-C, report 2014-03-26: what was the end depth, and what activity was being performed?"


def test_split_parts():
    assert len(split_parts(MP)) == 2
    assert len(split_parts("What was the bit size and also what was the mud type for 15/9-F-1?")) == 2
    assert len(split_parts("List (1) the bit size (2) the mud type (3) the rop for 15/9-F-1.")) == 3
    assert len(split_parts("What was the end depth? What activity was performed?")) == 2
    assert split_parts("What are the casing and liner sizes for 15/9-F-1?") == ["What are the casing and liner sizes for 15/9-F-1?"]
    assert split_parts(Q16) == [Q16]


def test_unaddressed_parts():
    assert unaddressed_parts(MP, "The end depth was 12 m; the activity was pulling HPDR.")[1] == []
    parts, missing = unaddressed_parts(MP, "The end depth was 12 m.", "found it")
    assert len(parts) == 2 and len(missing) == 1 and "activity" in missing[0]


def test_verifier_requires_every_part_addressed():
    d = rec_df([("A-20140326-ACT-01", "15/9-F-1-C", "2014-03-26", "activity", "md", 12, "md=12 m; comments=Continued pulling HPDR")])
    c = cx(d.record_id)
    one = {"status": "answered", "cited_ids": ["A-20140326-ACT-01"], "rationale": "r", "answer": "The end depth was 12 m."}
    r = verify(one, c, d, MP)
    assert not r.ok and "2 parts" in r.message and "not addressed" in r.message
    both = {**one, "answer": "The end depth was 12 m and the activity was pulling HPDR."}
    assert verify(both, c, d, MP).ok
    assert verify({**one, "status": "partial"}, c, d, MP).ok                  # partial may omit a part


def test_question_for_llm_lists_the_parts():
    q = A.question_for_llm(MP)
    assert q.startswith(MP) and "2 parts" in q and "(1) " in q and "(2) " in q and "rationale" in q
    assert A.question_for_llm(Q16) == Q16


# ---- escalation policy -----------------------------------------------------------------------------------------


def run(tmp_path, script, qid, text, reports, located):
    llm, fake = make(tmp_path, script)
    a = A.answer_question(qid, text, located, reports, llm, dump=False)
    return a, [c["model"] for c in fake.calls], fake


@pytest.fixture(scope="module")
def qtext():
    return load_questions().set_index("question_id")["question_text"]


@needs_data
def test_no_escalation_when_the_verifier_passes(tmp_path, qtext, reports, located):
    a, models, _ = run(tmp_path, lambda s, u, m: good(), "T2-016", qtext["T2-016"], reports, located)
    assert models == ["m1", "m1"] and a.verified
    p = {"status": "partial", "answer": "Only the density: 1.03 g/cm3.", "cited_ids": [FLUID], "rationale": "no more"}
    a, models, _ = run(tmp_path / "p", lambda s, u, m: p, "T2-016", qtext["T2-016"], reports, located)
    assert models == ["m1", "m1"] and a.status == "partial"                      # partial is never an escalation trigger


@needs_data
def test_escalates_once_on_verifier_failure(tmp_path, qtext, reports, located):
    bad = good(answer="The density was 9.99 g/cm3.")
    a, models, fake = run(tmp_path, lambda s, u, m: bad, "T2-016", qtext["T2-016"], reports, located)
    assert models == ["m1", "m1", "m2"] and not a.verified and a.confidence == 0.2        # never a 4th call
    assert any(n.startswith("VERIFIER FAILED") for n in a.notes)


@needs_data
def test_escalates_once_when_abstaining_with_a_matching_line(tmp_path, qtext, reports, located):
    def script(s, u, m):
        return ABSTAIN if m == "m1" else good()

    a, models, fake = run(tmp_path, script, "T2-016", qtext["T2-016"], reports, located)
    assert models == ["m1", "m1", "m2"] and a.status == "answered" and a.verified and a.model == "m2"
    assert any("abstained although a matching evidence line exists" in n for n in a.notes)
    assert "matching the question's well, date and field" in fake.calls[2]["user"]        # the flag is fed back


@needs_data
def test_abstention_confirmed_by_the_escalation_model_is_kept_without_a_third_call(tmp_path, qtext, reports, located):
    a, models, _ = run(tmp_path, lambda s, u, m: ABSTAIN, "T2-016", qtext["T2-016"], reports, located)
    assert models == ["m1", "m1", "m2"] and a.status == "abstain" and a.verified
    assert any("abstention confirmed by the escalation model" in n for n in a.notes)


@needs_data
def test_bad_escalation_does_not_replace_a_first_answer_that_only_had_the_flag(tmp_path, qtext, reports, located):
    def script(s, u, m):
        return ABSTAIN if m == "m1" else good(answer="The density was 9.99 g/cm3.")

    a, models, _ = run(tmp_path, script, "T2-016", qtext["T2-016"], reports, located)
    assert a.status == "abstain" and a.model == "m1" and any("REVIEW: escalated answer failed" in n for n in a.notes)


@needs_data
def test_a_legitimate_abstention_is_not_escalated(tmp_path, qtext, reports, located):
    reply = {"status": "abstain", "answer": "The archive has no cost field.", "cited_ids": ["ABSENT-cost"], "rationale": "checked"}
    a, models, _ = run(tmp_path, lambda s, u, m: reply, "T2-025", qtext["T2-025"], reports, located)
    assert models == ["m1", "m1"] and a.verified and a.status == "abstain"


@needs_data
def test_early_abstains_make_no_llm_call(tmp_path, qtext, reports, located):
    llm, fake = make(tmp_path, lambda s, u, m: pytest.fail("LLM must not be called"))
    for qid in ("T2-027", "T2-029"):
        a = A.answer_question(qid, qtext[qid], located, reports, llm, dump=False)
        assert a.early_abstain and a.llm_calls == 0 and not a.disagree
    assert fake.calls == []


# ---- disagreement flag --------------------------------------------------------------------------------------------


def alternating(first, second):
    seq = iter([first, second])
    return lambda s, u, m: next(seq)


@needs_data
def test_disagreeing_runs_are_flagged_and_run_one_is_committed(tmp_path, qtext, reports, located):
    other = good(answer="The NaCl brine density was 1.05 g/cm3.", rationale="r")
    a, models, _ = run(tmp_path, alternating(good(), other), "T2-016", qtext["T2-016"], reports, located)
    assert models == ["m1", "m1"]                                  # run 2 never triggers escalation
    assert a.disagree and a.needs_review and any(n.startswith("REVIEW: runs disagree") for n in a.notes)
    assert "1.03" in a.answer and "1.05" not in a.answer           # committed answer = run 1
    assert "REVIEW: runs disagree" in answer_notes(a)


@needs_data
def test_status_difference_is_a_disagreement(tmp_path, qtext, reports, located):
    a, _, _ = run(tmp_path, alternating(good(), {"status": "partial", "answer": "Only 1.03 g/cm3.", "cited_ids": [FLUID], "rationale": "r"}),
                  "T2-016", qtext["T2-016"], reports, located)
    assert a.disagree and a.status == "answered"


@needs_data
def test_agreeing_runs_with_different_wording_are_not_flagged(tmp_path, qtext, reports, located):
    worded = good(answer="1.03 g/cm3 (NaCl brine, active pit, sampled 2014-03-25T21:00:00).")
    a, _, _ = run(tmp_path, alternating(good(), worded), "T2-016", qtext["T2-016"], reports, located)
    assert not a.disagree and not any("REVIEW" in n for n in a.notes)


@needs_data
def test_run_two_is_a_separate_cache_entry_with_the_same_settings(tmp_path, qtext, reports, located):
    llm, fake = make(tmp_path, lambda s, u, m: good())
    A.answer_question("T2-016", qtext["T2-016"], located, reports, llm, dump=False)
    assert len(llm.cache.entries) == 2 and fake.calls[0]["max_tokens"] == fake.calls[1]["max_tokens"]
    A.answer_question("T2-016", qtext["T2-016"], located, reports, llm, dump=False)      # replay: both cached
    assert len(fake.calls) == 2


def test_runs_differ_helper():
    d = {"status": "answered", "answer": "1.03 g/cm3 on 2014-03-25T21:00:00"}
    assert not A.runs_differ(d, {"status": "answered", "answer": "Density 1.03 g/cm3 (sampled 2014-03-24T21:00:00)"})
    assert A.runs_differ(d, {**d, "answer": "1.04 g/cm3"}) and A.runs_differ(d, {**d, "status": "abstain"})


@needs_data
def test_disagreement_is_saved_in_answers_json_and_review_queue(tmp_path, qtext, reports, located):
    other = good(answer="The NaCl brine density was 1.05 g/cm3.")
    a, _, _ = run(tmp_path, alternating(good(), other), "T2-016", qtext["T2-016"], reports, located)
    path = save_answers_json([a], located, tmp_path / "answers.json")
    (row,) = json.loads(path.read_text())
    assert row["disagree"] is True and "REVIEW: runs disagree" in row["notes"]


# ---- T2-032 mud logging ----------------------------------------------------------------------------------------------


@needs_data
def test_mud_logging_gets_an_absent_record_and_wireline_does_not_count(qtext, reports, located):
    q = qtext["T2-032"]
    assert "mud logging" in q
    assert not has_field(located, "mud_logging")                        # no mud-logging company/engineer anywhere
    assert has_field(located, "log")                                    # ...although wireline log runs exist
    c = build_context("T2-032", q, route_question(q, reports), located)
    line = next(l for l in c.text.splitlines() if l.startswith("[ABSENT-mud_logging]"))
    assert "no mud logging field exists" in line and c.absent["ABSENT-mud_logging"]["kind"] == "mud_logging"
    wl = [l for l in c.text.splitlines() if "serviceCompany" in l]
    assert wl and all("[ABSENT" not in l and "mud" not in l.lower().split("servicecompany")[1][:40] for l in wl)  # wireline stays wireline


@needs_data
def test_mud_logging_abstention_is_accepted_without_escalation(tmp_path, qtext, reports, located):
    reply = {"status": "abstain", "answer": "The archive records no mud logging company or engineer.",
             "cited_ids": ["ABSENT-mud_logging"], "rationale": "ABSENT-mud_logging"}
    a, models, _ = run(tmp_path, lambda s, u, m: reply, "T2-032", qtext["T2-032"], reports, located)
    assert models == ["m1", "m1"] and a.status == "abstain" and a.verified and a.confidence == 0.85


# ---- empty answer on abstain (the prompt asks for "") -------------------------------------------------------------


def test_empty_answer_is_allowed_only_on_abstain():
    c = cx(FL.record_id)
    assert verify(ABSTAIN, c, FL, "What was the casing shoe depth on well 15/9-F-12 on 2014-03-26?").ok
    assert not verify({**ABSTAIN, "status": "answered", "cited_ids": [FLUID]}, c, FL, Q16).ok


@needs_data
def test_abstention_text_is_composed_from_the_absent_record_and_rationale(tmp_path, qtext, reports, located):
    reply = {"status": "abstain", "answer": "", "cited_ids": ["ABSENT-cost"], "rationale": "No cost line in the report."}
    a, models, _ = run(tmp_path, lambda s, u, m: reply, "T2-025", qtext["T2-025"], reports, located)
    assert models == ["m1", "m1"] and a.verified
    assert a.answer.startswith("Not answerable from the archive.") and "No cost field exists" in a.answer
    assert "No cost line in the report." in a.answer
