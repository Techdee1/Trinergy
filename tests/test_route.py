from datetime import date
from pathlib import Path

import pytest

from submission.archive_qa.route import find_dates, route_all, route_question, topic_sections
from submission.archive_qa.wells import Report
from tests.conftest import needs_data


def rep(well_stem: str, well: str, iso: str) -> Report:
    y, m, d = map(int, iso.split("-"))
    return Report(f"{well_stem}_{y}_{m:02d}_{d:02d}", well, date(y, m, d), Path("x.xml"))


ARCHIVE = [
    rep("15_9_F_1", "15/9-F-1", "2013-07-30"),
    rep("15_9_F_11_B", "15/9-F-11-B", "2013-07-30"),
    rep("15_9_F_1_B", "15/9-F-1-B", "2014-02-22"),
    rep("15_9_F_1_C", "15/9-F-1-C", "2014-02-22"),
    rep("15_9_F_1_C", "15/9-F-1-C", "2014-03-26"),
    rep("15_9_F_12", "15/9-F-12", "2008-01-16"),   # only D+1 exists for 2008-01-15
    rep("15_9_19_A", "15/9-19-A", "1980-01-01"),
    rep("15_9_19_A", "15/9-19-A", "1997-08-29"),
    rep("15_9_19_A", "15/9-19-A", "1997-10-05"),
    rep("15_9_F_15_D", "15/9-F-15-D", "2016-10-19"),
    rep("15_9_F_12", "15/9-F-12", "2016-10-21"),
]


def stems(res):
    return res.candidate_files


def test_well_and_date_not_in_archive_abstains():
    res = route_question("On well 15/9-F-14 on 2013-06-10 what happened?", ARCHIVE)
    assert res.early_abstain and not res.candidate_files
    assert "15/9-F-14" in res.reason and "not in the archive" in res.reason


def test_known_well_but_no_report_that_day_abstains_with_reason():
    res = route_question("What was the weather on 15/9-F-1-C on 2014-03-01?", ARCHIVE)
    assert res.early_abstain
    assert "no report for 15/9-F-1-C on 2014-03-01" in res.reason and "2014-02-22" in res.reason


def test_exact_date_does_not_add_next_day():
    res = route_question("For 15/9-F-1-C on 2014-02-22, what was the depth?", ARCHIVE)
    assert stems(res) == ["15_9_F_1_C_2014_02_22"]
    assert res.mode == "single_report" and not res.early_abstain


def test_d_plus_1_only_as_fallback_and_recorded():
    res = route_question("Who was on duty for well 15/9-F-12 on 2008-01-15?", ARCHIVE)
    assert stems(res) == ["15_9_F_12_2008_01_16"]
    assert "FALLBACK D+1" in res.reason and "2008-01-16" in res.reason and not res.early_abstain


def test_well_filtered_before_date():
    # F-1-B and F-1-C both have 2014-02-22
    res = route_question("On F-1-B on 2014-02-22 what was done?", ARCHIVE)
    assert stems(res) == ["15_9_F_1_B_2014_02_22"]


def test_f1_does_not_route_to_f11_or_f1b():
    res = route_question("For well F-1 on 2013-07-30 what was the casing ID?", ARCHIVE)
    assert stems(res) == ["15_9_F_1_2013_07_30"]


def test_each_date_pairs_with_its_own_well():
    q = "Compare F-1-B (2014-02-22) and F-1-C (2014-03-26)."
    res = route_question(q, ARCHIVE)
    assert stems(res) == ["15_9_F_1_B_2014_02_22", "15_9_F_1_C_2014_03_26"]
    assert res.mode == "multi_report"


def test_one_date_applies_to_all_named_wells():
    res = route_question("On F-1 and F-11-B on 2013-07-30 what was drilled?", ARCHIVE)
    assert set(stems(res)) == {"15_9_F_1_2013_07_30", "15_9_F_11_B_2013_07_30"}


def test_no_well_no_date_is_archive_wide():
    res = route_question("On which completion days did the crew land the BOP?", ARCHIVE)
    assert res.mode == "archive_wide" and len(res.candidate_files) == len(ARCHIVE)
    assert not res.early_abstain


def test_year_selects_all_that_year_for_the_well():
    res = route_question("On which report dates in 1997 were operations on well 15/9-19-A suspended?", ARCHIVE)
    assert stems(res) == ["15_9_19_A_1997_08_29", "15_9_19_A_1997_10_05"]


def test_month_year_without_well():
    res = route_question("What happened during the October 2016 campaign?", ARCHIVE)
    assert set(stems(res)) == {"15_9_F_15_D_2016_10_19", "15_9_F_12_2016_10_21"}


def test_date_range_spans_wells():
    q = "In what order did the rig move, from the 15/9-F-15-D report on 2016-10-19 to the 15/9-F-12 report on 2016-10-21?"
    res = route_question(q, ARCHIVE)
    assert res.date_range == ("2016-10-19", "2016-10-21")
    assert set(stems(res)) == {"15_9_F_15_D_2016_10_19", "15_9_F_12_2016_10_21"}


def test_partial_match_does_not_abstain_but_says_so():
    res = route_question("Compare F-1-C (2014-03-26) and F-14 (2013-06-10).", ARCHIVE)
    assert not res.early_abstain and stems(res) == ["15_9_F_1_C_2014_03_26"]
    assert "UNMATCHED" in res.reason and "F-14" in res.reason


def test_depth_is_not_read_as_a_year():
    q = "What was the pore pressure at 2000 mMD for 15/9-19-A on 1997-08-29?"
    assert [d.iso for d in find_dates(q)] == ["1997-08-29"]


def test_textual_dates():
    isos = [d.iso for d in find_dates("on 19 October 2016, in March 2014 and on May 5, 2013")]
    assert isos == ["2016-10-19", "2014-03", "2013-05-05"]


def test_topic_does_not_cause_abstain():
    # a topic that cannot exist in the data still routes to the report
    res = route_question("What was the total daily spread cost for well 15/9-F-1-C on 2014-03-26?", ARCHIVE)
    assert not res.early_abstain and "cost" in res.sections


def test_topics():
    assert "pore_pressure" in topic_sections("estimated pore pressure equivalent mud weight at 3600 mMD")
    assert "fluid" not in topic_sections("estimated pore pressure equivalent mud weight at 3600 mMD")
    assert "fluid" in topic_sections("density of the NaCl brine sampled from the active pit")
    assert "gas" in topic_sections("mud logging service company recorded the gas readings")


@needs_data
def test_all_32_questions_resolve(reports):
    out = route_all(reports=reports)
    assert len(out) == 32
    assert out["mode"].isin(["single_report", "multi_report", "archive_wide"]).all()
    abst = out[out.early_abstain]
    assert (abst.reason.str.startswith("EARLY ABSTAIN")).all() and (abst.candidate_files == "").all()
    assert (out[~out.early_abstain].candidate_files != "").all()
