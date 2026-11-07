import json
import math
from pathlib import Path

import pandas as pd

from submission.archive_qa.parse import SENTINEL, parse_report
from submission.archive_qa.wells import Report
from tests.conftest import needs_data

MINI = """<?xml version="1.0" encoding="ISO-8859-1"?>
<witsml:drillReports version="1.4.0.0" xmlns:witsml="http://www.witsml.org/schemas/1series">
<witsml:documentInfo><witsml:documentName>x</witsml:documentName></witsml:documentInfo>
<witsml:drillReport>
<witsml:nameWell>NO 15/9-F-1 C</witsml:nameWell><witsml:nameWellbore>NO 15/9-F-1 C</witsml:nameWellbore>
<witsml:name>name</witsml:name>
<witsml:dTimStart>2014-03-25T00:00:00+01:00</witsml:dTimStart><witsml:dTimEnd>2014-03-26T00:00:00+01:00</witsml:dTimEnd>
<witsml:wellboreInfo><witsml:operator>Statoil</witsml:operator>
<witsml:rigAlias><witsml:name>M\xc6RSK INSPIRER</witsml:name><witsml:namingSystem>NPD Name</witsml:namingSystem></witsml:rigAlias></witsml:wellboreInfo>
<witsml:statusInfo><witsml:md uom="m">4094</witsml:md><witsml:distDrill uom="m">-999.99</witsml:distDrill>
<witsml:sum24Hr>None</witsml:sum24Hr><witsml:forecast24Hr>Run risers.</witsml:forecast24Hr></witsml:statusInfo>
<witsml:fluid><witsml:type>NaCl brine</witsml:type><witsml:dTim>2014-03-25T21:00:00+01:00</witsml:dTim>
<witsml:density uom="g/cm3">.5</witsml:density><witsml:visFunnel uom="s">-999.99</witsml:visFunnel></witsml:fluid>
</witsml:drillReport></witsml:drillReports>""".encode("latin-1")


def mini_rows(tmp_path: Path):
    p = tmp_path / "15_9_F_1_C_2014_03_26.xml"
    p.write_bytes(MINI)
    rep = Report("15_9_F_1_C_2014_03_26", "15/9-F-1-C", pd.Timestamp("2014-03-26").date(), p)
    rows, stats = parse_report(rep)
    return pd.DataFrame(rows), stats


def test_sentinel_becomes_missing_never_a_value(tmp_path):
    df, stats = mini_rows(tmp_path)
    dist = df[df.field == "distDrill"].iloc[0]
    assert pd.isna(dist.value) and bool(dist.missing) and math.isnan(dist.value_num)
    assert stats.sentinels_dropped == 2  # distDrill + visFunnel
    assert not df["value"].eq(SENTINEL).any()
    assert not df["text"].str.contains("999.99").any()
    assert not df["attrs"].fillna("").str.contains("999.99").any()


def test_none_string_in_summary_is_missing_and_counted(tmp_path):
    df, stats = mini_rows(tmp_path)
    s = df[df.field == "sum24Hr"].iloc[0]
    assert pd.isna(s.value) and bool(s.missing)
    assert stats.none_strings_converted == 1
    assert df[df.field == "forecast24Hr"].iloc[0].value == "Run risers."


def test_iso_8859_1_decoding_and_wallclock_times(tmp_path):
    df, _ = mini_rows(tmp_path)
    rig = df[df.field == "rigAlias/name"].iloc[0]
    assert rig.value == "MÆRSK INSPIRER"
    fluid = df[df.section == "fluid"].iloc[0]
    assert fluid.timestamp == "2014-03-25T21:00:00"  # offset dropped
    assert (fluid.period_start, fluid.period_end) == ("2014-03-25T00:00:00", "2014-03-26T00:00:00")
    assert fluid.record_id == "F1C-20140326-FLUID-01"
    # numeric parse kept next to the raw text; ".5" keeps its raw form
    d = fluid
    assert d.field == "density" and d.value == ".5" and d.value_num == 0.5 and d.unit == "g/cm3"
    attrs = json.loads(d["attrs"])
    assert attrs["visFunnel"] == {"value": None, "unit": "s"}


@needs_data
def test_f1c_20140326_nacl_brine_sample(parsed):
    df, _ = parsed
    fl = df[(df.well == "15/9-F-1-C") & (df.report_date == "2014-03-26") & (df.section == "fluid")]
    assert len(fl) == 1
    r = fl.iloc[0]
    assert r.record_id == "F1C-20140326-FLUID-01"
    assert r.field == "density" and r.value_num == 1.03 and r.unit == "g/cm3"
    a = json.loads(r["attrs"])
    assert a["type"]["value"] == "NaCl brine" and a["locationSample"]["value"] == "Active pit"
    assert r.timestamp == "2014-03-25T21:00:00"  # sample taken the day BEFORE the report date
    assert (r.period_start, r.period_end) == ("2014-03-25T00:00:00", "2014-03-26T00:00:00")


@needs_data
def test_19a_1980_kickoff_depth(parsed):
    df, _ = parsed
    k = df[(df.well == "15/9-19-A") & (df.report_date == "1980-01-01") & (df.field == "mdKickoff")]
    assert len(k) == 1
    assert k.iloc[0].value_num == 2178 and k.iloc[0].unit == "m"
    assert k.iloc[0].section == "status"


@needs_data
def test_no_sentinel_anywhere_in_real_store(parsed):
    df, stats = parsed
    assert stats.sentinels_dropped == 174
    assert not df["value"].eq(SENTINEL).any()
    for col in ("text", "attrs"):
        assert not df[col].fillna("").str.contains("999.99", regex=False).any()
    assert stats.none_strings_converted == 5
    assert stats.date_mismatches == [] and stats.well_mismatches == []


@needs_data
def test_record_ids_unique_and_report_window(parsed):
    df, _ = parsed
    assert df.record_id.is_unique
    assert (df.period_end.str[:10] == df.report_date).all()
    assert set(df.section) >= {"status", "activity", "fluid", "survey", "casing", "gas", "pore_pressure"}
