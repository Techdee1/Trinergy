"""XML-only evidence, derived XML-vs-PDF discrepancy notes, repeated-container parsing, question-gated NOTE context."""
import json
import re
from collections import Counter
import xml.etree.ElementTree as ET

import pandas as pd
import pymupdf
import pytest

from submission.archive_qa import config
from submission.archive_qa.answer import Answer
from submission.archive_qa.context import build_context
from submission.archive_qa.discrepancy import NOTE_CONCEPTS, discrepancy_notes, note_line
from submission.archive_qa.parse import NS, _leaves
from submission.archive_qa.route import route_question
from submission.archive_qa.write import build_evidence
from submission.archive_qa.xmlonly import XML_ONLY_ATTRS, xml_only_paths
from tests.conftest import needs_data
from tests.test_answer import make
from tests.test_retry import go


@pytest.fixture(scope="module")
def with_notes(located):
    notes = discrepancy_notes(located, config.PDF_DIR)
    return pd.concat([located, notes], ignore_index=True)


def ans(question, text, cited, **kw):
    return Answer("TX", question, "answered", text, cited, "r", 0.9, [], "single_report", verified=True, **kw)


# ---- parse: repeated sibling containers -----------------------------------------------------------------------------------


def test_repeated_container_blocks_keep_every_leaf():
    root = ET.fromstring(f'<r xmlns="{NS[1:-1]}"><bit><nozzle><n>4</n><d>14</d></nozzle><nozzle><n>2</n><d>15</d></nozzle></bit></r>')
    keys = [k for k, *_ in _leaves(root.find(f"{NS}bit"), seen=Counter())]
    assert keys == ["nozzle/n", "nozzle/d", "nozzle/n#2", "nozzle/d#2"]
    legacy = [k for k, *_ in _leaves(root.find(f"{NS}bit"))]               # field-style sections: per-block counting, ids unchanged
    assert legacy == ["nozzle/n", "nozzle/d", "nozzle/n", "nozzle/d"]


@needs_data
def test_the_f1_bit_keeps_both_nozzle_blocks(located):
    a = json.loads(located[located.record_id == "F1-20130824-BIT-01"].iloc[0]["attrs"])
    assert (a["nozzle/numNozzle"]["value"], a["nozzle/diaNozzle"]["value"]) == (4, 14)
    assert (a["nozzle/numNozzle#2"]["value"], a["nozzle/diaNozzle#2"]["value"]) == (2, 15)


# ---- C1. evidence for XML-only fields ---------------------------------------------------------------------------------------


@needs_data
def test_not_printed_fields_say_xml_only_and_cite_no_page(located):
    ev = build_evidence(ans("What was the wellhead elevation?", "138.9 m", ["F1C-20140326-STATUS-WELLHEADELEVATION"]), located)
    assert ev == "XML only: wellhead" + "Elevation; not printed in the PDF (15_9_F_1_C_2014_03_26.xml F1C-20140326-STATUS-WELLHEADELEVATION)"
    assert ".pdf" not in ev
    npd = build_evidence(ans("NPD number?", "7405", ["F1C-20140326-HDR-WELLBOREALIAS-02"]), located)
    assert npd.startswith("XML only: wellboreAlias; not printed in the PDF") and ".pdf" not in npd
    rig = build_evidence(ans("Rig NPD code?", "369304", ["F1C-20140326-WELL-RIGALIAS_NAME-02"]), located)
    assert rig.startswith("XML only: rigAlias/name; not printed in the PDF") and ".pdf" not in rig
    days = build_evidence(ans("Days behind?", "35", ["19A-19970829-WELL-DAYSBEHIND"]), located)
    assert days.startswith("XML only: daysBehind; not printed in the PDF") and ".pdf" not in days


@needs_data
def test_a_flag_whose_pdf_value_conflicts_is_labelled_as_such(located):
    ev = build_evidence(ans("Is it a tight well?", "No (XML 0)", ["F1C-20140326-STATUS-TIGHTWELL"]), located)
    assert ev.startswith("XML only: tightWell; the PDF prints a conflicting value") and ".pdf" not in ev


@needs_data
@pytest.mark.parametrize("rid, question, answer, path", [
    ("F15D-20150810-ACT-14", "Which operations were an equipment failure?", "The tractor trouble was logged as an equipment failure.", "activity/stateDetailActivity"),
    ("F15D-20150810-ACT-14", "What phase was it?", "The phase was wire line.", "activity/phase"),
    ("F1C-20140326-FLUID-01", "What was the mud class?", "water based", "fluid/mudClass"),
    ("F1C-20140326-FLUID-01", "What was the BOP pressure rating at the sample?", "345 bar", "fluid/presBopRating"),
    ("F19A-19970829-GAS-01".replace("F19A", "19A"), "What was the n-butane reading?", "10 ppm", "gas/nbut"),
    ("F11T2-20130428-BIT-01", "What was the bit dull grading?", "1-3-CT-G-E-I-NO-TD", "bit/condFinalDull"),
    ("F1-20130824-BIT-01", "How many nozzles did the bit have?", "4 x 14 and 2 x 15", "bit/nozzle/numNozzle"),
    ("19A-19800101-SURVEY-01", "What was the timestamp of the first survey station?", "1980-01-01T00:00", "survey/dTim"),
])
def test_xml_only_attributes_are_labelled_when_the_question_is_about_them(located, rid, question, answer, path):
    row = located[located.record_id == rid].iloc[0]
    paths = [p for p, _ in xml_only_paths(row, question, answer)]
    assert path in paths, (rid, paths)
    ev = build_evidence(ans(question, answer, [rid]), located)
    assert f"XML only: {path}; not printed in the PDF" in ev and ".pdf p." not in ev


@needs_data
def test_printed_content_still_cites_its_pdf_page(located):
    """Same records, but the question is about the printed content: the PDF page is cited, nothing is marked XML-only."""
    for rid, q, a in [("F15D-20150810-ACT-14", "What happened with the tractor at 13:10?", "The tractor could not be activated."),
                      ("F1C-20140326-FLUID-01", "What was the density of the brine?", "1.03 g/cm3"),
                      ("F11T2-20130428-BIT-01", "What size was the bit?", "12.25 in")]:
        ev = build_evidence(ans(q, a, [rid]), located)
        assert ".pdf p." in ev and "XML only" not in ev, rid


@needs_data
def test_a_success_state_is_never_an_informative_xml_only_value(located):
    row = located[located.record_id == "F15D-20150810-ACT-01"].iloc[0]                 # stateDetailActivity = equipment failure
    ok = located[(located.section == "activity") & located["attrs"].map(
        lambda a: isinstance(a, str) and json.loads(a).get("stateDetailActivity", {}).get("value") == "success")].iloc[0]
    q, a = "Was there an equipment failure?", "failure"
    assert xml_only_paths(row, q, a) and not xml_only_paths(ok, q, a)


@needs_data
def test_xml_only_and_printed_records_can_be_cited_together(located):
    ev = build_evidence(ans("What was the density and the mud class?", "1.03 g/cm3, water based",
                            ["F1C-20140326-FLUID-01", "F1C-20140326-ACT-01"]), located)
    assert "15_9_F_1_C_2014_03_26.xml F1C-20140326-ACT-01" in ev and "XML only: fluid/mudClass" in ev
    assert ev.count(".pdf p.") == 1 and "(Operations)" in ev                            # only the printed activity row has a page


@needs_data
def test_the_xml_only_list_is_true_the_pdfs_print_none_of_these_labels_or_values():
    import glob
    texts = []
    for p in glob.glob(f"{config.PDF_DIR}/*.pdf"):
        with pymupdf.open(p) as d:
            lines = [ln.strip().lower() for pg in d for ln in pg.get_text().splitlines()]
            texts.append((lines, re.sub(r"\s+", "", "".join(lines))))
    all_lines = {l for lines, _ in texts for l in lines}
    flat = "".join(t for _, t in texts)
    for label in ("mud class", "phase", "bop pressure rating", "pressure rating", "nc4", "nbut", "dull", "nozzle", "state detail"):
        assert not any(label == l or l.startswith(label + ":") or l.startswith(label + " (") for l in all_lines), label
    for value in ("waterbased", "oilbased", "operationfailed", "mudloss"):              # XML mudClass / stateDetailActivity values
        assert value not in flat, value
    assert "ic4" in flat                                                                  # the gas table prints IC4 but no nC4 column
    assert {s for s, _, _, _ in XML_ONLY_ATTRS} >= {"activity", "fluid", "gas", "bit"}


# ---- C2. derived discrepancy notes --------------------------------------------------------------------------------------------


@needs_data
def test_notes_are_derived_for_exactly_the_documented_disagreements(with_notes):
    n = with_notes[with_notes.section == "note"]
    assert n.field.value_counts().to_dict() == {"tightWell": 32, "hpht": 32, "daysBehind": 11, "bitRun/mdHoleStop": 1}
    tw = n[(n.field == "tightWell") & (n.well == "15/9-F-1-C") & (n.report_date == "2014-03-26")].iloc[0]
    assert tw.record_id == "F1C-20140326-NOTE-TIGHTWELL" and tw.value == "XML 0; PDF prints Y"
    assert "[NOTE-DISCREPANCY] tightWell: XML 0; PDF prints Y" in tw.text and int(tw.pdf_page) == 1
    d = n[n.record_id == "19A-19970829-NOTE-DAYSBEHIND"].iloc[0]
    assert d.value == "XML 35; PDF prints (blank)"
    b = n[n.field == "bitRun/mdHoleStop"].iloc[0]
    assert (b.record_id, b.value, b.pdf_section) == ("F11T2-20130428-NOTE-BITRUN_MDHOLESTOP", "XML 2577; PDF prints 2574", "Bit Record")
    assert not (n.field == "daysAhead").any()                                              # the 13 daysAhead values match: no note


@needs_data
def test_note_ids_are_unique_and_notes_are_not_located_evidence(with_notes):
    assert with_notes.record_id.is_unique
    from submission.archive_qa.locate import locate_stats
    s = locate_stats(with_notes, show_unlocated=False)
    assert s["records"] == len(with_notes[with_notes.section != "note"])                  # notes are derived, not located


def synthetic_pdf(path, tw, hp, days):
    doc = pymupdf.open()
    pg = doc.new_page()
    y = 40
    for line in ["Summary report", "Tight well:", tw, "HPHT:", hp, "Temperature ():", "Days Ahead/Behind (+/-):", days, "Operator:", "Statoil"]:
        if line:
            pg.insert_text((40, y), line)
            y += 14
    doc.save(path)
    doc.close()


def synthetic_records(tw, hp, ahead=None, behind=None):
    def row(section, field, value):
        return {"record_id": f"S-20200101-{field}", "well": "15/9-F-1", "report_date": "2020-01-01", "period_start": "2019-12-31T00:00:00",
                "period_end": "2020-01-01T00:00:00", "section": section, "field": field, "value": value, "value_num": float("nan"),
                "unit": None, "missing": False, "timestamp": None, "text": "", "attrs": None, "source_file": "s.xml",
                "pdf_file": "s.pdf", "pdf_page": 1, "pdf_section": "Summary report", "pdf_match": "exact"}
    rows = [row("status", "tightWell", tw), row("status", "hpht", hp)]
    if ahead: rows.append(row("wellbore", "daysAhead", ahead))
    if behind: rows.append(row("wellbore", "daysBehind", behind))
    return pd.DataFrame(rows)


def test_the_comparison_is_generic_notes_only_when_the_pdf_disagrees(tmp_path):
    synthetic_pdf(tmp_path / "s.pdf", "Y", "N", "3.5")
    agree = discrepancy_notes(synthetic_records("1", "0", ahead="3.5"), tmp_path)             # Y=1, N=0, 3.5=3.5
    assert len(agree) == 0
    off = discrepancy_notes(synthetic_records("0", "1", ahead="4.5"), tmp_path)
    assert sorted(off.field) == ["daysAhead", "hpht", "tightWell"]
    assert set(off.value) == {"XML 0; PDF prints Y", "XML 1; PDF prints N", "XML 4.5; PDF prints 3.5"}
    synthetic_pdf(tmp_path / "s.pdf", "Y", "N", "")
    blank = discrepancy_notes(synthetic_records("1", "0", behind="12"), tmp_path)
    assert list(blank.field) == ["daysBehind"] and blank.iloc[0]["value"] == "XML 12; PDF prints (blank)"


# ---- C2. context: notes only when the question mentions the field ---------------------------------------------------------------


@needs_data
def test_a_note_is_in_the_context_only_when_the_question_mentions_its_field(with_notes, reports):
    def ids(q):
        return build_context("T", q, route_question(q, reports), with_notes).ids
    tight = "Was well 15/9-F-1-C a tight well on 2014-03-26?"
    c = build_context("T", tight, route_question(tight, reports), with_notes)
    assert "F1C-20140326-NOTE-TIGHTWELL" in c.ids and "F1C-20140326-NOTE-HPHT" not in c.ids
    assert "F1C-20140326-STATUS-TIGHTWELL" in c.ids                                          # router topic pulls the status fields in
    line = next(l for l in c.text.splitlines() if l.startswith("[F1C-20140326-NOTE-TIGHTWELL]"))
    assert line == ("[F1C-20140326-NOTE-TIGHTWELL] note | tightWell: the XML value is 0 (authoritative); the PDF prints Y "
                    "| report 2014-03-26 | at -")
    assert "F1C-20140326-NOTE-HPHT" in ids("Was 15/9-F-1-C an HPHT well on 2014-03-26?")
    assert not any("-NOTE-" in i for i in ids("What was the density of the NaCl brine sampled from the active pit on well 15/9-F-1-C on 2014-03-26?"))
    behind = "How many days behind schedule was well 15/9-19-A in its 1997-08-29 report?"
    assert "19A-19970829-NOTE-DAYSBEHIND" in ids(behind)
    assert set(NOTE_CONCEPTS) == {"tightWell", "hpht", "daysBehind", "daysAhead", "bitRun/eTimOpBit", "bitRun/mdHoleStart", "bitRun/mdHoleStop"}


@needs_data
def test_an_answer_can_cite_the_note_and_state_both_values(tmp_path, with_notes, reports):
    q = "Was well 15/9-F-1-C a tight well on 2014-03-26?"
    reply = {"status": "answered", "cited_ids": ["F1C-20140326-NOTE-TIGHTWELL", "F1C-20140326-STATUS-TIGHTWELL"], "rationale": "r",
             "answer": "No. The XML records tightWell as 0, although the PDF prints Y; the XML is authoritative."}
    llm, fake = make(tmp_path, lambda s, u, m: reply)
    from submission.archive_qa import answer as A
    a = A.answer_question("TX", q, with_notes, reports, llm, dump=False)
    assert a.verified and a.status == "answered" and len(fake.calls) == 2
    assert "F1C-20140326-NOTE-TIGHTWELL" in a.cited_ids
    ev = build_evidence(a, with_notes)
    assert "15_9_F_1_C_2014_03_26.pdf p.1 (Summary report)" in ev and "NOTE-TIGHTWELL" in ev
    assert "XML only: tightWell; the PDF prints a conflicting value" in ev


def test_note_line_format():
    row = pd.Series({"record_id": "X-20200101-NOTE-HPHT", "field": "hpht", "report_date": "2020-01-01",
                     "attrs": json.dumps({"xml": {"value": "0"}, "pdf": {"value": "Y"}})})
    assert note_line(row) == "[X-20200101-NOTE-HPHT] note | hpht: the XML value is 0 (authoritative); the PDF prints Y | report 2020-01-01 | at -"


@needs_data
def test_absent_record_counts_archive_records_not_derived_notes(with_notes, located, reports):
    q = "What was the total daily spread cost for well 15/9-F-1-C on 2014-03-26?"
    a = build_context("T", q, route_question(q, reports), located)
    b = build_context("T", q, route_question(q, reports), with_notes)
    assert a.text == b.text                                   # the same context with or without the derived NOTE rows
    assert b.absent["ABSENT-cost"]["records"] == len(located[located.source_file == "15_9_F_1_C_2014_03_26.xml"])
