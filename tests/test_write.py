import csv
import json
import shutil

import pytest

from submission.archive_qa import config
from submission.archive_qa.answer import Answer
from submission.archive_qa.route import load_questions
from submission.archive_qa.write import (build_evidence, record_evidence, run_validator, save_answers_json,
                                         template_order, write_predictions)
from tests.conftest import needs_data

pytestmark = needs_data


def placeholder(qid: str, cited=None) -> Answer:
    """Fixture row only: never written to the real predictions.csv."""
    return Answer(qid, "q", "answered", f"placeholder answer for {qid}", cited or [], "r", 0.5, ["note"], "single_report")


def test_record_evidence_format(located):
    row = located[located.record_id == "F1C-20140326-FLUID-01"].iloc[0]
    assert record_evidence(row) == "15_9_F_1_C_2014_03_26.pdf p.1 (Drilling Fluid); 15_9_F_1_C_2014_03_26.xml F1C-20140326-FLUID-01"
    # a record the PDF does not print is cited from the XML only
    row = located[(located.field == "mdPlanned")].iloc[0]
    assert record_evidence(row) == f"{row['source_file']} {row['record_id']}"
    assert ".pdf" not in record_evidence(row)


def test_evidence_joins_with_semicolons_and_drops_unknown_ids(located):
    a = placeholder("T2-016", ["F1C-20140326-FLUID-01", "F1C-20140326-ACT-01", "BOGUS-1"])
    ev = build_evidence(a, located)
    assert ev.count(".xml") == 2 and "BOGUS" not in ev and "; " in ev


def test_written_csv_passes_organiser_validator(tmp_path, located):
    order = template_order()
    assert len(order) == 32 and order[0] == "T2-001" and order[-1] == "T2-032"
    answers = [placeholder(q, ["F1C-20140326-FLUID-01"]) for q in order]
    sub = tmp_path / "submission"
    sub.mkdir()
    for f in ("README.md", "requirements.txt", "solution.ipynb"):
        shutil.copy(config.SUBMISSION_DIR / f, sub / f)
    path = write_predictions(answers, located, sub / "predictions.csv")
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert [r["question_id"] for r in rows] == order
    assert list(rows[0]) == ["question_id", "answer", "evidence", "confidence", "notes"]
    report = run_validator(sub)
    assert report is not None and report["valid"], report
    assert report["csv"]["rows"] == 32 and not report["csv"]["warnings"]


def test_all_32_required_unless_partial(tmp_path, located):
    few = [placeholder("T2-001"), placeholder("T2-016")]
    with pytest.raises(ValueError, match="30 question"):
        write_predictions(few, located, tmp_path / "p.csv")
    p = write_predictions(few, located, tmp_path / "p.csv", allow_partial=True)
    assert [r["question_id"] for r in csv.DictReader(p.open())] == ["T2-001", "T2-016"]


def test_answers_json_round_trip(tmp_path, located):
    p = save_answers_json([placeholder("T2-002"), placeholder("T2-001")], located, tmp_path / "a.json")
    data = json.loads(p.read_text())
    assert [d["question_id"] for d in data] == ["T2-001", "T2-002"] and "evidence" in data[0]
