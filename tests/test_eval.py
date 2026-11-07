import csv

import pytest

from submission.eval import evaluate, review
from submission.archive_qa.answer import Answer
from submission.archive_qa.route import load_questions
from submission.archive_qa.write import save_answers_json
from tests.conftest import needs_data


def test_evaluate_projected_score(tmp_path):
    key = tmp_path / "key.csv"
    rows = [("T2-001", "correct"), ("T2-002", "partial"), ("T2-003", "wrong"), ("T2-004", "correct-abstention"),
            ("T2-005", "")]
    with key.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["question_id", "question_text", "our_answer", "reviewer", "verdict", "notes"])
        for q, v in rows:
            w.writerow([q, "", "", "me", v, ""])
    r = evaluate.evaluate(key)
    assert r["counts"] == {"correct": 1, "partial": 1, "wrong": 1, "correct-abstention": 1}
    assert r["points"] == 2.5 and r["ungraded"] == 1 and r["projected_score"] == pytest.approx(2.5 / 32 * 40)
    key.write_text("question_id,verdict\nT2-001,maybe\n")
    with pytest.raises(ValueError, match="maybe"):
        evaluate.evaluate(key)


@needs_data
def test_review_pack_builds_with_highlighted_page(tmp_path, located):
    a = Answer("T2-016", "q", "answered", "1.03 g/cm3 <b>&", ["F1C-20140326-FLUID-01"], "r", 0.95, [], "single_report",
               verified=True)
    answers = [__import__("json").loads(open(save_answers_json([a], located, tmp_path / "a.json")).read())[0]]
    idx = review.build_review(located, load_questions(), answers, tmp_path / "rv", tmp_path / "key_template.csv")
    html = idx.read_text()
    assert "T2-016" in html and "&lt;b&gt;" in html and "<b>&" not in html.split("Answer:")[1].split("</p>")[0]
    assert (tmp_path / "rv" / "img" / "T2-016_1.png").stat().st_size > 1000
    key = list(csv.DictReader((tmp_path / "key_template.csv").open()))
    assert list(key[0]) == ["question_id", "question_text", "our_answer", "reviewer", "verdict", "notes"]
    assert key[0]["verdict"] == "" and key[0]["our_answer"].startswith("1.03")


@needs_data
def test_answers_for_review_has_exact_cited_lines_and_flags(tmp_path, located):
    import json
    from submission.archive_qa.write import save_answers_json
    from submission.archive_qa.answer import early_abstain_answer
    from submission.archive_qa.route import discover_reports, route_question
    from submission.archive_qa import config

    ok = Answer("T2-016", "q", "answered", "1.03 g/cm3", ["F1C-20140326-FLUID-01"], "one sample", 0.95, ["note"],
                "single_report", verified=True)
    bad = Answer("T2-017", "q", "answered", "x", ["F15D-20161019-SUM-SUM24HR"], "r", 0.2,
                 ["first answer: verifier failed (a); escalated to b", "REVIEW: runs disagree (run 1: x)"], "multi_report",
                 verified=False, failures=["numbers in the answer not found"], disagree=True)
    reports = discover_reports(config.XML_DIR)
    early = early_abstain_answer("T2-027", "q", route_question("On well 15/9-F-14 on 2013-06-10?", reports), reports)
    answers = json.loads(open(save_answers_json([ok, bad, early], located, tmp_path / "a.json")).read())
    md = review.write_answers_md(located, load_questions(), answers, reports, tmp_path / "a.md").read_text()
    assert review.flags_for(answers[0]) == [] and review.flags_for(answers[1]) == [
        "ESCALATED", "REVIEW: runs disagree", "VERIFIER FAILED"]
    assert review.flags_for({"notes": "runs disagreed (x); arbitrated by m2: its verified answer is committed",
                             "verified": True}) == ["ARBITRATED"]
    # words in the model's rationale must not raise flags
    assert review.flags_for({"notes": "status=answered | mode=single_report | rationale: ACT-03 gives md=2763 m, matching the "
                                      "status md; it was escalated to the crew and retried; arbitrated by hand",
                             "verified": True, "early_abstain": False}) == []
    assert review.flags_for({"notes": "status=answered | first answer: verifier failed (a); escalated to b | rationale: r",
                             "verified": True}) == ["ESCALATED"]
    assert "## T2-016" in md and "**Flags:** none" in md and "**Flags:** ESCALATED, REVIEW: runs disagree, VERIFIER FAILED" in md
    assert "[F1C-20140326-FLUID-01] fluid | density=1.03 g/cm3;" in md          # the exact line the model saw
    assert "sum24Hr=\"- Cut and pulled production riser - Skidded rig to F-14\"" in md
    assert "**Verifier:** numbers in the answer not found" in md
    assert "none (early abstain, no LLM call)" in md and "Checked document_manifest.csv" in md
