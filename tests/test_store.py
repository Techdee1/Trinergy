import pandas as pd

from submission.archive_qa.locate import PdfText, locate_stats, norm
from submission.archive_qa.store import has_field, text_mentions
from tests.conftest import needs_data


def make_pdf(path):
    import pymupdf

    doc = pymupdf.open()
    p1 = doc.new_page()
    p1.insert_text((50, 60), "Summar y of activities (24 Hours)")
    p1.insert_text((50, 80), "Pulled riser to 12 m")
    p2 = doc.new_page()
    p2.insert_text((50, 60), "Operations")
    p2.insert_text((50, 80), "00:00")
    p2.insert_text((50, 100), "Waited on integrity tes")
    p2.insert_text((50, 120), "t crane")
    doc.save(path)
    doc.close()


def test_pdf_text_ignores_whitespace_and_split_words(tmp_path):
    pdf = tmp_path / "a.pdf"
    make_pdf(pdf)
    t = PdfText(pdf)
    assert [h for _, h in t.headings] == ["Summary of activities (24 Hours)", "Operations"]
    off = t.find(norm("integrity test crane"))  # the PDF wrapped "tes" / "t"
    assert off is not None and t.page_at(off) == 2 and t.heading_at(off) == "Operations"
    off1 = t.text.find(norm("Pulled riser"))
    assert t.page_at(off1) == 1 and t.heading_at(off1) == "Summary of activities (24 Hours)"


def test_repeated_rows_claim_successive_occurrences(tmp_path):
    import pymupdf

    doc = pymupdf.open()
    pg = doc.new_page()
    for y in (60, 80, 100):
        pg.insert_text((50, y), "00:00 12 same remark")
    doc.save(tmp_path / "r.pdf")
    t = PdfText(tmp_path / "r.pdf")
    a, b, c = (t.find(norm("00:00 12 same remark")) for _ in range(3))
    assert len({a, b, c}) == 3 and t.find(norm("00:00 12 same remark")) is None


def fake_records():
    return pd.DataFrame([
        {"well": "15/9-F-1", "report_date": "2014-03-26", "section": "fluid", "field": "density",
         "missing": False, "attrs": '{"type": {"value": "x"}}', "text": "fluid sample"},
        {"well": "15/9-F-1", "report_date": "2014-03-26", "section": "activity", "field": "comments",
         "missing": False, "attrs": '{"proprietaryCode": {"value": "x"}}',
         "text": "Waited on weather. Cranes down due to wind"},
        {"well": "15/9-F-1", "report_date": "2014-03-26", "section": "status", "field": "distDrill",
         "missing": True, "attrs": None, "text": "distDrill = (no value reported)"},
    ])


def test_has_field_is_structural_not_textual():
    df = fake_records()
    assert has_field(df, "fluid", well="15/9-F-1", report_date="2014-03-26")
    assert not has_field(df, "fluid", well="15/9-F-1", report_date="2014-03-27")
    assert not has_field(df, "survey")
    # a remark mentioning weather/wind is NOT a weather field...
    assert not has_field(df, "weather")
    # ...but narrative search finds it
    assert len(text_mentions(df, r"weather|wind")) == 1


def test_has_field_require_value():
    df = fake_records()
    assert has_field(df, "activity", require_value=True)
    df.loc[df.section == "activity", "missing"] = True
    assert not has_field(df, "activity", require_value=True)


@needs_data
def test_real_archive_has_no_cost_personnel_supervisor_weather_fields(located):
    for kind in ("cost", "personnel", "supervisor", "weather"):
        assert not has_field(located, kind), kind
    for kind in ("fluid", "activity", "summary", "forecast"):
        assert has_field(located, kind)
    assert has_field(located, "fluid", well="15/9-F-1-C", report_date="2014-03-26")
    assert has_field(located, "kickoff", well="15/9-19-A", report_date="1980-01-01")
    # free-text mentions of weather exist even though no structured weather field does
    assert len(text_mentions(located, r"waited on weather")) > 0


@needs_data
def test_locator_coverage_and_kickoff_page(located):
    s = locate_stats(located, show_unlocated=False)
    assert s["share_table_rows"] >= 0.95
    assert s["share_printable"] >= 0.90
    k = located[(located.well == "15/9-19-A") & (located.report_date == "1980-01-01")
                & (located.field == "mdKickoff")].iloc[0]
    assert (k.pdf_file, int(k.pdf_page), k.pdf_section, k.pdf_match) == (
        "15_9_19_A_1980_01_01.pdf", 1, "Summary report", "exact")
    # XML is authoritative for flags: tightWell/HPHT are never given a PDF location
    flags = located[located.field.isin(["tightWell", "hpht"])]
    assert (flags.pdf_match == "excluded").all() and flags.pdf_page.isna().all()


@needs_data
def test_located_page_actually_contains_the_value(located):
    import pymupdf
    from submission.archive_qa import config

    row = located[located.record_id == "F1C-20140326-FLUID-01"].iloc[0]
    page = pymupdf.open(config.PDF_DIR / row.pdf_file)[int(row.pdf_page) - 1].get_text()
    assert "NaCl brine" in page and row.pdf_section == "Drilling Fluid"
