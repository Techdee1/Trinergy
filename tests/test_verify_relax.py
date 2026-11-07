"""Verifier relaxations: dates/times as whole tokens, list enumerators, 24:00. Positive AND negative cases."""
import pandas as pd
import pytest

from submission.archive_qa.context import Context
from submission.archive_qa.verify import (enumerator_spans, mask_temporal, temporal_supported, verify)

LINE_A = ('[X-ACT-16] activity | dTimEnd=2013-12-13T23:45:00; md=0 m; comments="Moved BOP to well center and landed same '
          'onto riser. Made up NT2 connector." | report 2013-12-14 | at 2013-12-13T19:15:00')
LINE_B = ('[X-ACT-08] activity | dTimEnd=2013-06-28T00:00:00; md=0 m; comments="Landed BOP, made up NT2 connector." '
          '| report 2013-06-28 | at 2013-06-27T18:00:00')


def rec(rid, text, report_date, start=None, end=None, value="x"):
    return {"record_id": rid, "well": "15/9-F-15-D", "report_date": report_date, "section": "activity", "field": "comments",
            "value": value, "value_num": float("nan"), "unit": None, "attrs": None, "text": text, "missing": False,
            "period_start": start, "period_end": end}


RECS = pd.DataFrame([
    rec("X-ACT-16", LINE_A.split("] ", 1)[1], "2013-12-14", "2013-12-13T00:00:00", "2013-12-14T00:00:00"),
    rec("X-ACT-08", LINE_B.split("] ", 1)[1], "2013-06-28", "2013-06-27T00:00:00", "2013-06-28T00:00:00"),
    rec("X-ACT-99", "activity | md=1484 m; comments=\"Drilled\" | report 2013-11-11 | at 2013-11-10T19:00:00", "2013-11-11",
        "2013-11-10T00:00:00", "2013-11-11T00:00:00"),
])
CTX = Context("T", "", frozenset({"X-ACT-16", "X-ACT-08", "X-ACT-99"}))
Q = "On which days was the BOP landed?"


def check(answer, cited=("X-ACT-16",), question=Q, status="answered"):
    return verify({"status": status, "answer": answer, "cited_ids": list(cited), "rationale": "r"}, CTX, RECS, question)


def msgs(res):
    return " | ".join(res.failures)


# ---- 1a. times and ISO dates are whole tokens -----------------------------------------------------------------


def test_mask_temporal_keeps_tokens_whole():
    masked, toks = mask_temporal("from 1997-10-04T00:00 to 17:00 on 2013-12-13 and 23:30-00:00, md 1484")
    assert toks == ["1997-10-04T00:00", "2013-12-13", "17:00", "23:30", "00:00"]
    assert "1484" in masked and "17" not in masked and "1997" not in masked


def test_time_and_date_present_in_a_cited_line_pass():
    assert check("The BOP was landed between 19:15 and 23:45 on 2013-12-13 (report 2013-12-14).").ok
    assert check("Landed at 2013-12-13T19:15 (the record has seconds).").ok          # prefix of 19:15:00
    assert check("Landed at 2013-12-13 19:15:00.").ok                                 # space instead of T


def test_time_not_in_any_cited_line_still_fails():
    r = check("The BOP was landed at 19:20.")
    assert not r.ok and "dates/times" in msgs(r) and "19:20" in msgs(r)
    r = check("Landed between 19:15 and 23:50.")
    assert not r.ok and "23:50" in msgs(r) and "19:15" not in msgs(r)


def test_wrong_date_still_fails():
    r = check("Landed on 2013-12-12.")
    assert not r.ok and "2013-12-12" in msgs(r)
    r = check("Landed on 2013-12-13T19:16.")                                         # right date, wrong time
    assert not r.ok and "2013-12-13T19:16" in msgs(r)


def test_bare_wrong_number_still_fails():
    r = check("Drilled to 1485 m.", cited=("X-ACT-99",))
    assert not r.ok and "numbers in the answer not found" in msgs(r) and "1485" in msgs(r)
    assert check("Drilled to 1484 m.", cited=("X-ACT-99",)).ok


def test_times_are_not_matched_by_substring_or_digits():
    assert not check("Landed at 9:15.").ok                 # "19:15" contains "9:15" but it is a different time
    assert not check("Landed at 3:45.").ok                 # "23:45" contains "3:45"
    assert not check("Landed at 15 and 19.").ok            # the digits of 19:15 alone do not make 15 / 19 valid numbers


def test_dates_and_times_from_the_report_window_and_the_question_pass():
    # the report window is a cited-record timestamp even if the line itself does not show it
    assert check("This is the report window starting 2013-12-13T00:00 and ending 2013-12-14.").ok
    assert check("Report dated 2013-12-14.").ok
    # echoing the question is fine, as numbers always were
    q = "What was done on well F-15-D from 19:00 to 23:45 on 2013-11-10?"
    assert check("From 19:00 to 23:45 on 2013-11-10 drilling reached 1484 m.", cited=("X-ACT-99",), question=q).ok
    assert not check("From 19:00 to 23:45 on 2013-11-10 drilling reached 1484 m.", cited=("X-ACT-99",)).ok  # no echo -> 23:45 missing


def test_temporal_supported_unit():
    blob = "report 2013-12-14 at 2013-12-13 19:15:00 dTimEnd=2013-12-13 23:45:00"
    for ok in ("19:15", "19:15:00", "2013-12-13", "2013-12-13T19:15", "2013-12-13 23:45", "2013-12-14"):
        assert temporal_supported(ok, blob), ok
    for bad in ("9:15", "19:16", "2013-12-12", "2013-12-13T19:16", "2013-12-1"):
        assert not temporal_supported(bad, blob), bad


# ---- 1b. list enumerators ------------------------------------------------------------------------------------------


def test_enumerators_are_ignored():
    ans = ("Landed on two days. (1) On 2013-12-13 between 19:15 and 23:45. (2) On 2013-06-27 report 2013-06-28 "
           "between 18:00 and 24:00.")
    assert check(ans, cited=("X-ACT-16", "X-ACT-08")).ok
    assert check("1. Landed at 19:15; 2. made up NT2 at 23:45.").ok
    assert check("(1) Landed at 19:15\n(2) NT2 at 23:45").ok


def test_enumerator_spans_need_a_run_from_one_at_item_starts():
    assert len(enumerator_spans("Two days. (1) a. (2) b.")) == 2
    assert len(enumerator_spans("1. a; 2. b; 3. c")) == 3
    assert enumerator_spans("Landed (7) times.") == []                       # not at an item start
    assert enumerator_spans("Days. (2) only the second.") == []              # a run must start at 1
    assert enumerator_spans("Days. (1) a. (3) c.") == []                     # and be consecutive


def test_a_wrong_number_cannot_hide_as_an_enumerator():
    r = check("Landed. (7) On 2013-12-13 at 19:15.")
    assert not r.ok and "7" in msgs(r)
    r = check("(1) Drilled to 1485 m. (2) done.", cited=("X-ACT-99",))
    assert not r.ok and "1485" in msgs(r) and "'1'" not in msgs(r) and "'2'" not in msgs(r)


# ---- 1c. 24:00 -----------------------------------------------------------------------------------------------------


def test_24_00_accepted_only_when_00_00_is_cited():
    assert check("Landed between 18:00 and 24:00 (report 2013-06-28).", cited=("X-ACT-08",)).ok     # dTimEnd=...T00:00:00
    r = check("Landed until 24:00.", cited=("X-ACT-16",))                                           # no 00:00 in this record
    assert not r.ok and "24:00" in msgs(r)
    assert not check("Landed until 25:00.", cited=("X-ACT-08",)).ok                                  # only 24:00 is special
    assert temporal_supported("24:00", "dTimEnd=2013-06-28 00:00:00") and not temporal_supported("24:00", "at 19:15:00")
    # the report window always starts at 00:00, so it must not make 24:00 acceptable on its own
    assert not temporal_supported("24:00", "window 2013-12-13 00:00:00", midnight_blob="at 19:15:00")
