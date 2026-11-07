import re

import pytest

from submission.archive_qa.context import build_context, header_line
from submission.archive_qa.route import load_questions, route_question
from tests.conftest import needs_data

pytestmark = needs_data


@pytest.fixture(scope="module")
def qtext():
    return load_questions().set_index("question_id")["question_text"]


def ctx_for(qid, qtext, reports, records):
    return build_context(qid, qtext[qid], route_question(qtext[qid], reports), records)


def test_context_is_deterministic(qtext, reports, located):
    for qid in ("T2-016", "T2-017", "T2-020"):
        a = ctx_for(qid, qtext, reports, located)
        b = ctx_for(qid, qtext, reports, located.sample(frac=1, random_state=3))  # row order must not matter
        assert a.text == b.text and a.ids == b.ids


def test_context_has_no_paths_timestamps_or_machine_state(qtext, reports, located):
    for qid in ("T2-016", "T2-020", "T2-031"):
        t = ctx_for(qid, qtext, reports, located).text
        assert "/workspaces" not in t and "external/" not in t and "\\" not in t
        assert not re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+", t)  # no run-time stamps


def test_line_format_header_and_missing_values(qtext, reports, located):
    c = ctx_for("T2-016", qtext, reports, located)
    lines = c.text.splitlines()
    assert lines[0] == header_line("15/9-F-1-C", "2014-03-26", "2014-03-25T00:00:00", "2014-03-26T00:00:00",
                                   "15_9_F_1_C_2014_03_26")
    fluid = next(l for l in lines if l.startswith("[F1C-20140326-FLUID-01]"))
    assert re.fullmatch(r"\[F1C-20140326-FLUID-01\] fluid \| density=1.03 g/cm3; .* \| report 2014-03-26 \| at 2014-03-25T21:00:00", fluid)
    assert "visFunnel=missing" in fluid and "999.99" not in c.text
    assert "F1C-20140326-FLUID-01" in c.ids


def test_survey_stations_ascending_by_depth(qtext, reports, located):
    c = ctx_for("T2-003", qtext, reports, located)
    mds = [float(re.search(r"\bmd=([\d.]+) m", l).group(1)) for l in c.text.splitlines() if " survey | " in l]
    assert len(mds) > 3 and mds == sorted(mds)


def test_absent_topic_adds_citeable_pseudo_record(qtext, reports, located):
    c = ctx_for("T2-025", qtext, reports, located)  # cost
    assert "ABSENT-cost" in c.ids and c.absent["ABSENT-cost"]["kind"] == "cost"
    line = next(l for l in c.text.splitlines() if l.startswith("[ABSENT-cost]"))
    assert re.search(r"Searched 1 report\(s\) and \d+ record\(s\): no cost field exists", line)
    # a topic the archive does have gets no pseudo-record
    assert not ctx_for("T2-016", qtext, reports, located).absent


def test_multi_report_cap_and_truncation_recorded(qtext, reports, located):
    c = ctx_for("T2-020", qtext, reports, located)  # archive_wide
    assert c.truncated and any("TRUNCATED" in n for n in c.notes) and c.est_tokens <= 12_500
    small = ctx_for("T2-021", qtext, reports, located)
    assert not small.truncated and small.est_tokens < 12_000


def test_fallback_is_flagged_to_the_model(reports, located):
    q = "Who was the supervisor for well 15/9-F-12 on 2008-01-14?"  # no report on 01-14; D+1 (01-15) exists
    r = route_question(q, reports)
    c = build_context("TX", q, r, located)
    assert c.text.startswith("ROUTING NOTE:") and "FALLBACK D+1" in c.text


def test_mud_logging_question_gets_an_absent_record_and_keeps_the_wireline_line_visible(qtext, reports, located):
    from submission.archive_qa.route import topic_sections

    assert topic_sections("which mud logging service company recorded the gas readings")[0] == "mud_logging"
    assert "gas" in topic_sections("mud logging service company recorded the gas readings")
    c = ctx_for("T2-032", qtext, reports, located)
    assert "ABSENT-mud_logging" in c.ids and c.absent["ABSENT-mud_logging"]["kind"] == "mud_logging"
    absent = next(l for l in c.text.splitlines() if l.startswith("[ABSENT-mud_logging]"))
    assert "no mud logging field exists" in absent
    assert "serviceCompany=Western Atlas" in c.text      # the model sees it, and the ABSENT record says it is not mud logging
    # an ordinary gas question does not get the pseudo-record
    q = "What was the highest trip gas reading for well 15/9-19-A on 1997-08-29?"
    assert "ABSENT-mud_logging" not in build_context("TX", q, route_question(q, reports), located).ids
