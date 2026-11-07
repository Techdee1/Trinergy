"""Decimal commas, 'Part (1):' enumerators, short record ids, and the 'nothing found for well X' rule."""
import json

import pandas as pd
import pytest

from submission.archive_qa.context import Context
from submission.archive_qa.match import match_score, norm_text, question_tokens
from submission.archive_qa.verify import _candidates, claimed_missing_but_present, enumerator_spans, short_id_rx, verify

W1B, W11, WF1 = "15/9-F-1-B", "15/9-F-11-T2", "15/9-F-15-D"


def rec(rid, well, body, day="2013-11-11", section="activity"):
    return {"record_id": rid, "well": well, "report_date": day, "section": section, "field": "comments", "value": body,
            "value_num": float("nan"), "unit": None, "attrs": None, "missing": False,
            "text": f"{well} | report {day} | activity | comments={body}", "period_start": None, "period_end": None}


def frame(*rows):
    return pd.DataFrame(list(rows))


def run(df, cited, answer, question="What happened?", ids=None, status="answered"):
    ctx = Context("T", "", frozenset(ids if ids is not None else df["record_id"]))
    reply = {"status": status, "answer": answer, "cited_ids": list(cited), "rationale": "r"}
    return verify(reply, ctx, df, question)


def msgs(r):
    return " | ".join(r.failures)


# ---- 1. decimal comma ---------------------------------------------------------------------------------------------------


def test_candidates_decimal_comma_is_strict():
    assert _candidates("144,3") == [144.3]                    # decimal comma only: NOT 1443
    assert _candidates("0,05") == [0.05] and _candidates("12,5") == [12.5]
    assert _candidates("1234,567") == [1234.567]              # more than 3 digits before the comma: a decimal
    assert sorted(_candidates("1,420")) == [1.42, 1420.0]     # ambiguous: either reading
    assert sorted(_candidates("12,345")) == [12.345, 12345.0]
    assert _candidates("1,234,567") == [1234567.0] and _candidates("1,420.5") == [1420.5]
    assert _candidates("13,") == [13.0] and _candidates("2800") == [2800.0] and _candidates("22.6") == [22.6]


def test_decimal_comma_in_a_record_and_the_answer():
    df = frame(rec("F15D-20131111-ACT-02", WF1, '"Drilled with 144,3 kNm, ECD 1,420 sg. Max gas 0,05 %"'))
    cited = ["F15D-20131111-ACT-02"]
    for ok in ("The torque was 144.3 kNm.", "The torque was 144,3 kNm.", "Max gas was 0.05 %.", "Max gas was 0,05 %.",
               "ECD was 1.420 sg.", "ECD was 1,420 sg.", "ECD was 1420 sg.", "ECD was 1.42 sg."):
        assert run(df, cited, ok).ok, ok
    for bad in ("The torque was 1443 kNm.", "The torque was 144,4 kNm.", "The torque was 14.43 kNm.",
                "Max gas was 0.5 %.", "ECD was 1.43 sg.", "ECD was 1430 sg."):
        assert not run(df, cited, bad).ok, bad


def test_a_number_never_includes_a_trailing_comma():
    from submission.archive_qa.verify import numbers_in
    assert [t for t, _ in numbers_in("at ACT-13, 2800 m, then 14, 15")] == ["13", "2800", "14", "15"]


# ---- 1b (i). "Part (1):" / "Part 1:" / "Step 2:" ----------------------------------------------------------------------


def test_worded_enumerators_follow_the_same_run_from_one_rule():
    assert len(enumerator_spans("Part (1): a. Part (2): b.")) == 2
    assert len(enumerator_spans("Part 1: a; Part 2: b; Part 3: c")) == 3
    assert len(enumerator_spans("Step 1: a. Step 2: b.")) == 2
    assert len(enumerator_spans("part (1): a\nPART (2): b")) == 2                        # case-insensitive
    assert enumerator_spans("Step 2: only the second.") == []                            # a run must start at 1
    assert enumerator_spans("Part (1): a. Part (3): c.") == []                           # and be consecutive
    assert enumerator_spans("See Part 1: it is long") == []                              # not at an item start
    assert enumerator_spans("The Part (7) is lost") == []


def test_part_enumerators_are_ignored_but_wrong_numbers_are_not():
    df = frame(rec("F15D-20131111-ACT-02", WF1, "Drilled to 1484 m", ), rec("F15D-20131111-ACT-03", WF1, "Tested to 345 bar"))
    cited = ["F15D-20131111-ACT-02", "F15D-20131111-ACT-03"]
    assert run(df, cited, "Part (1): drilled to 1484 m. Part (2): tested to 345 bar.").ok
    assert run(df, cited, "Part 1: drilled to 1484 m; Part 2: tested to 345 bar").ok
    r = run(df, cited, "Part (1): drilled to 1485 m. Part (2): tested to 345 bar.")
    assert not r.ok and "1485" in msgs(r) and "'1'" not in msgs(r)                       # the wrong value is still caught
    assert not run(df, cited, "Part (7): drilled to 1484 m.").ok                         # a lone (7) is a number
    assert not run(df, cited, "Step 2: drilled to 1484 m.").ok


# ---- 1b (ii). record id forms present in the context -----------------------------------------------------------------------


def test_short_ids_are_ignored_only_when_such_an_id_is_in_the_context():
    df = frame(rec("F15D-20131111-ACT-02", WF1, "Drilled to 1484 m"), rec("F15D-20131111-SUM-SUM24HR", WF1, "Drilled to 1484 m",
                                                                         section="summary_24h"))
    cited = list(df["record_id"])
    assert short_id_rx(["F15D-20131111-ACT-02", "F15D-20131111-SUM-SUM24HR", "ABSENT-cost"]).findall("ACT-02 and SUM-SUM24HR") \
        == ["ACT-02", "SUM-SUM24HR"]
    assert run(df, cited, "Per ACT-02, drilled to 1484 m (see also SUM-SUM24HR).").ok
    assert run(df, cited, "Per ACT-02, then ACT-02, drilled to 1484 m.").ok
    assert run(df, cited, "(act-02) drilled to 1484 m").ok                                # case-insensitive


def test_a_lone_wrong_number_next_to_a_short_id_still_fails():
    df = frame(rec("F15D-20131111-ACT-02", WF1, "Drilled to 1484 m"))
    r = run(df, ["F15D-20131111-ACT-02"], "Per ACT-02, drilled to 1485 m.")
    assert not r.ok and "1485" in msgs(r) and "'02'" not in msgs(r)


def test_a_short_id_the_context_does_not_have_is_not_ignored():
    df = frame(rec("F15D-20131111-ACT-02", WF1, "Drilled to 1484 m"))
    r = run(df, ["F15D-20131111-ACT-02"], "Per ACT-13, drilled to 1484 m.")
    assert not r.ok and "13" in msgs(r)                                                   # ACT-13 is not a record here
    r = run(df, ["F15D-20131111-ACT-02"], "Per ACT-13, drilled to 1484 m.", ids=["F15D-20131111-ACT-02"])
    assert not r.ok


def test_short_id_rx_ignores_ids_of_the_wrong_shape():
    assert short_id_rx(["X-ACT-16", "ABSENT-cost", "16"]) is None                         # no real record ids -> no mask


# ---- 2. "nothing found for well X" while a matching record exists ----------------------------------------------------------

Q = "Across the F-11-T2 and F-1-B sidetracks, at what depths was 50% formation in returns confirmed during kick-off?"


def two_wells():
    return frame(
        rec("F11T2-20130515-ACT-07", W11, "Kicked off to F-11 A. 50% cement / formation in returns verified at 2586m MD."),
        rec("F1B-20140222-ACT-13", W1B, "Commenced time drilling from 1355 m to 1364 m. At 14:30 hrs, 50 % formation in returns at 1364 m.",
            day="2014-02-22"),
        rec("F1B-20140222-ACT-14", W1B, "Drilled to 1400 m with 3000 lpm.", day="2014-02-22"))


def test_claiming_nothing_found_for_a_well_with_a_matching_record_fails():
    df = two_wells()
    answer = "F-11-T2: 50% formation in returns at 2586 m MD. F-1-B: no 50% formation confirmation found in evidence."
    r = run(df, ["F11T2-20130515-ACT-07"], answer, Q)
    assert not r.ok
    assert "15/9-F-1-B" in msgs(r) and "F1B-20140222-ACT-13" in msgs(r) and "nothing was found" in msgs(r)
    assert "15/9-F-11-T2" not in msgs(r)                                                    # F-11-T2 was answered


def test_the_rule_sees_50_percent_with_a_space_and_without():
    for spelling in ("At 14:30 hrs, 50 % formation in returns at 1364 m.", "At 14:30 hrs, 50% formation in returns at 1364 m.",
                     "AT 14:30 HRS, 50  %   FORMATION IN RETURNS at 1364 m."):
        df = frame(rec("F11T2-20130515-ACT-07", W11, "50% formation in returns at 2586 m"),
                   rec("F1B-20140222-ACT-13", W1B, spelling, day="2014-02-22"))
        r = run(df, ["F11T2-20130515-ACT-07"], "F-11-T2: 2586 m. F-1-B: none found.", Q)
        assert not r.ok and "F1B-20140222-ACT-13" in msgs(r), spelling


def test_a_real_absence_is_still_accepted():
    df = frame(rec("F11T2-20130515-ACT-07", W11, "50% formation in returns at 2586 m"),
               rec("F1B-20140222-ACT-14", W1B, "Drilled to 1400 m with 3000 lpm.", day="2014-02-22"))   # nothing for F-1-B
    answer = "F-11-T2: 50% formation in returns at 2586 m. F-1-B: no 50% formation confirmation found in evidence."
    assert run(df, ["F11T2-20130515-ACT-07"], answer, Q).ok


def test_answering_the_well_with_its_record_passes():
    df = two_wells()
    answer = "F-11-T2: 2586 m MD. F-1-B: 1364 m."
    assert run(df, ["F11T2-20130515-ACT-07", "F1B-20140222-ACT-13"], answer, Q).ok


def test_the_rule_only_looks_at_wells_the_question_names():
    df = two_wells()
    q = "At what depth was 50% formation in returns confirmed on well F-11-T2 during kick-off?"
    answer = "F-11-T2: 2586 m. F-1-B: nothing was found."          # F-1-B is not what was asked about
    ctx = Context("T", "", frozenset(df["record_id"]))
    assert claimed_missing_but_present(answer, q, ctx, df) == []
    assert [w for w, _ in claimed_missing_but_present(answer, Q, ctx, df)] == [W1B]      # but it is when the question names F-1-B


def test_match_helpers():
    assert norm_text("At 50 %  Formation,  0,05 % and 2586 m") == "at 50% formation, 0.05% and 2586m"
    qt = question_tokens(Q)
    assert qt.num_units == {"50%"} and "formation" in qt.words and "return" in qt.words
    assert not any("f-1" in w or "2013" in w for w in qt.words)                                 # wells/dates removed
    assert match_score("50 % return of formation at 1380m", qt) > 0
    assert match_score("pull over 50 % of cable strength", qt) == 0                              # number alone is not enough
    assert match_score("formation in returns confirmed", qt) == 0                                # words alone are not enough
    assert match_score("anything", question_tokens("")) == 0
