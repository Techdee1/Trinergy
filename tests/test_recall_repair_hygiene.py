"""Recall for multi-report questions, the partial policy, LLM_MULTI_MAX_TOKENS, citation repair and output hygiene."""
import csv
import json

import pandas as pd
import pytest

from submission.archive_qa import answer as A
from submission.archive_qa import llm as L
from submission.archive_qa.answer import Answer
from submission.archive_qa.context import FORCE_ALL, Context, build_context
from submission.archive_qa.llm import LLM, Cache, FakeLLM, LLMConfig, load_config
from submission.archive_qa.repair import repair_citations
from submission.archive_qa.route import RouteResult, load_questions, route_question
from submission.archive_qa.write import (build_evidence, prediction_note, save_answers_json, write_predictions)
from tests.conftest import needs_data
from tests.test_answer import FLUID, good, make
from tests.test_retry import go

NAN = float("nan")
W1B, W11, WF15 = "15/9-F-1-B", "15/9-F-11-T2", "15/9-F-15-D"


def srec(rid, well, day, section, field, value, src, page=1, sec="Operations"):
    return {"record_id": rid, "well": well, "report_date": day, "period_start": f"{day}T00:00:00", "period_end": f"{day}T00:00:00",
            "section": section, "field": field, "value": value, "value_num": NAN, "unit": None, "missing": False,
            "timestamp": None, "text": f"{well} | report {day} | {section} | {field}={value}", "attrs": None,
            "source_file": src, "pdf_file": src.replace(".xml", ".pdf"), "pdf_page": page, "pdf_section": sec, "pdf_match": "exact"}


S1B, S11 = "15_9_F_1_B_2014_02_22.xml", "15_9_F_11_T2_2013_05_15.xml"
QUESTION = "Across the F-11-T2 and F-1-B sidetracks, at what depths was 50% formation in returns confirmed during kick-off?"


def synthetic_records(spelling="At 14:30 hrs, 50 % formation in returns at 1364 m."):
    rows = [srec("F1B-20140222-LITH-01", W1B, "2014-02-22", "lithology", "lithology", spelling, S1B, sec="Lithology Information"),
            srec("F11T2-20130515-ACT-07", W11, "2013-05-15", "activity", "comments", "Kicked off. 50% cement / formation in returns at 2586 m", S11)]
    # filler activity records that share the question's words, so a tight token cap has to drop something
    for i in range(1, 40):
        rows.append(srec(f"F1B-20140222-ACT-{i:02d}", W1B, "2014-02-22", "activity", "comments",
                         f"Drilled and circulated while monitoring returns and formation behaviour, step {i}, kick off preparation", S1B))
        rows.append(srec(f"F11T2-20130515-ACT-{i + 20:02d}", W11, "2013-05-15", "activity", "comments",
                         f"Circulated returns and checked formation, step {i}", S11))
    return pd.DataFrame(rows)


def multi_route(wells):
    return RouteResult(wells=wells, dates=[], candidate_files=[S1B[:-4], S11[:-4]], mode="multi_report", sections=["activity"])


# ---- 2. recall -------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("spelling", ["At 14:30 hrs, 50 % formation in returns at 1364 m.", "At 14:30, 50% formation in returns at 1364 m.",
                                      "AT 14:30, 50  %  FORMATION in RETURNS at 1364 m."])
def test_a_matching_record_in_a_section_not_normally_included_is_forced_in_even_under_a_tight_cap(spelling):
    df = synthetic_records(spelling)
    ctx = build_context("T", QUESTION, multi_route([W1B, W11]), df, token_cap=500)
    assert ctx.truncated                                                    # the cap really did drop records
    assert "F1B-20140222-LITH-01" in ctx.ids                                # lithology is not a narrative/topic section
    assert "F11T2-20130515-ACT-07" in ctx.ids
    assert any(n.startswith("RECALL") for n in ctx.notes)
    assert 0 < sum(1 for i in ctx.ids if "-ACT-" in i) < 78                  # and the filler was cut


def test_recall_only_forces_records_of_the_named_wells():
    df = synthetic_records()
    df = pd.concat([df, pd.DataFrame([srec("F15D-20131111-LITH-01", WF15, "2013-11-11", "lithology", "lithology",
                                           "50 % return of formation at 1380m", "15_9_F_15_D_2013_11_11.xml")])])
    route = RouteResult(wells=[W1B], dates=[], candidate_files=[S1B[:-4], S11[:-4], "15_9_F_15_D_2013_11_11"],
                        mode="multi_report", sections=["activity"])
    ctx = build_context("T", QUESTION, route, df, token_cap=500)
    assert "F1B-20140222-LITH-01" in ctx.ids and "F15D-20131111-LITH-01" not in ctx.ids   # F-15-D not named


def test_without_named_wells_the_best_matches_over_all_routed_reports_are_forced():
    df = synthetic_records()
    q = "At what depth was 50% formation in returns confirmed?"
    route = RouteResult(wells=[], dates=[], candidate_files=[S1B[:-4], S11[:-4]], mode="archive_wide", sections=["activity"])
    ctx = build_context("T", q, route, df, token_cap=500)
    assert {"F1B-20140222-LITH-01", "F11T2-20130515-ACT-07"} <= ctx.ids
    assert FORCE_ALL >= 2


def test_single_report_contexts_are_unchanged_by_recall():
    df = synthetic_records()
    single = RouteResult(wells=[W1B], dates=[], candidate_files=[S1B[:-4]], mode="single_report", sections=["activity"])
    ctx = build_context("T", QUESTION, single, df)
    assert "F1B-20140222-LITH-01" not in ctx.ids and not any(n.startswith("RECALL") for n in ctx.notes)


@needs_data
def test_real_t2_019_context_contains_the_f1b_and_f15d_fifty_percent_lines(located, reports):
    q = load_questions().set_index("question_id")["question_text"]["T2-019"]
    ctx = build_context("T2-019", q, route_question(q, reports), located)
    assert {"F1B-20140222-ACT-13", "F15D-20131111-ACT-01", "F11T2-20130515-ACT-07", "F1-20130824-ACT-03"} <= ctx.ids
    assert ctx.est_tokens <= 12_500


# ---- 3. LLM_MULTI_MAX_TOKENS --------------------------------------------------------------------------------------------------


def _clean(monkeypatch, tmp_path):
    for n in ("LLM_MULTI_MAX_TOKENS", "LLM_MAX_TOKENS", "OpenRouter_Key", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(n, raising=False)
    monkeypatch.setattr(L.config, "LLM_CACHE_PATH", tmp_path / "none.json")
    return tmp_path / "none.env"


def test_multi_max_tokens_default_env_validation_and_cache_metadata(monkeypatch, tmp_path):
    env = _clean(monkeypatch, tmp_path)
    cfg = load_config(dotenv_path=env)
    assert (cfg.max_tokens, cfg.multi_max_tokens) == (400, 3000) and cfg.describe()["multi_max_tokens"] == 3000
    monkeypatch.setenv("LLM_MULTI_MAX_TOKENS", "4000")
    assert load_config(dotenv_path=env).multi_max_tokens == 4000
    monkeypatch.setenv("LLM_MULTI_MAX_TOKENS", "0")
    with pytest.raises(ValueError, match="LLM_MULTI_MAX_TOKENS"):
        load_config(dotenv_path=env)
    monkeypatch.delenv("LLM_MULTI_MAX_TOKENS")
    llm = LLM(LLMConfig(primary="m1", escalation="m2", live=True, multi_max_tokens=3500), FakeLLM(),
              Cache(tmp_path / "c.json"), tmp_path / "l.csv")
    llm.ask("S", "c", "q", "m1", question_id="T")
    assert json.loads((tmp_path / "c.json").read_text())["_meta"]["settings"]["multi"] == {"max_tokens": 3500}
    monkeypatch.setattr(L.config, "LLM_CACHE_PATH", tmp_path / "c.json")
    assert load_config(dotenv_path=env).multi_max_tokens == 3500        # offline replay reads it from the cache metadata


@needs_data
def test_multi_questions_call_the_primary_with_the_multi_cap_and_single_ones_do_not(tmp_path, reports, located):
    qs = load_questions().set_index("question_id")["question_text"]
    llm, fake = make(tmp_path, lambda s, u, m: good())
    llm.cfg.multi_max_tokens = 2500
    A.answer_question("T2-024", qs["T2-024"], located, reports, llm, dump=False)
    assert [c["max_tokens"] for c in fake.calls[:2]] == [2500, 2500]
    assert A.start_cap(llm, "single_report") is None


# ---- 4. partial policy ---------------------------------------------------------------------------------------------------------

PARTIAL = {"status": "partial", "answer": "Only the density: 1.03 g/cm3.", "cited_ids": [FLUID], "rationale": "part missing"}
FULL = good(answer="The NaCl brine density was 1.03 g/cm3 (active pit).")


def by_model(m1, m2):
    return lambda s, u, m: m2 if m == "m2" else m1


@needs_data
def test_a_final_partial_is_escalated_once_and_a_verified_answer_is_kept(tmp_path, reports, located):
    qs = load_questions().set_index("question_id")["question_text"]
    a, fake, _ = go(tmp_path, by_model(PARTIAL, FULL), "T2-016", qs, reports, located)
    assert [c["model"] for c in fake.calls] == ["m1", "m1", "m2"] and a.model == "m2" and a.status == "answered"
    assert "PARTIAL:" in fake.calls[2]["user"] and "Only the density" in fake.calls[2]["user"]
    assert fake.calls[2]["max_tokens"] == 1500 and fake.calls[2]["reasoning"] == "minimal"
    assert any("partial answer: escalated" in n and "committed (status answered)" in n for n in a.notes)


@needs_data
def test_the_status_is_not_forced_a_verified_partial_stays_partial(tmp_path, reports, located):
    qs = load_questions().set_index("question_id")["question_text"]
    still = {**PARTIAL, "rationale": "the other part is not in the report"}
    a, fake, _ = go(tmp_path, by_model(PARTIAL, still), "T2-016", qs, reports, located)
    assert [c["model"] for c in fake.calls] == ["m1", "m1", "m2"]                       # one escalation, no more
    assert a.status == "partial" and a.model == "m2" and "(status partial)" in " ".join(a.notes)


@needs_data
def test_an_escalated_answer_that_fails_verification_keeps_the_partial(tmp_path, reports, located):
    qs = load_questions().set_index("question_id")["question_text"]
    a, fake, _ = go(tmp_path, by_model(PARTIAL, good(answer="The density was 9.99 g/cm3.")), "T2-016", qs, reports, located)
    assert a.status == "partial" and a.model == "m1" and "Only the density" in a.answer
    assert any("kept the partial answer" in n for n in a.notes)


@needs_data
def test_no_second_big_model_call_when_one_was_already_made(tmp_path, reports, located):
    qs = load_questions().set_index("question_id")["question_text"]
    # runs disagree -> arbiter (m2) returns a verified partial: that is the one allowed big-model call
    seq = iter([good(), PARTIAL])
    script = lambda s, u, m: PARTIAL if m == "m2" else next(seq)                        # noqa: E731
    a, fake, _ = go(tmp_path, script, "T2-016", qs, reports, located)
    assert [c["model"] for c in fake.calls] == ["m1", "m1", "m2"] and a.status == "partial"


@needs_data
def test_non_partial_answers_never_trigger_the_partial_escalation(tmp_path, reports, located):
    qs = load_questions().set_index("question_id")["question_text"]
    a, fake, _ = go(tmp_path, lambda s, u, m: good(), "T2-016", qs, reports, located)
    assert [c["model"] for c in fake.calls] == ["m1", "m1"]


# ---- 5. citation repair ---------------------------------------------------------------------------------------------------------


def repair_ctx():
    bodies = {"R1-20160101-ACT-01": "comments=Installed hatches and hole covers in moonpool; phase=fixed",
              "R1-20160101-ACT-02": "comments=Skidded cantilever to well F-1 C; phase=fixed",
              "R1-20160101-ACT-03": "comments=Held toolbox talk; phase=fixed",
              "R1-20160101-SUM-SUM24HR": 'sum24Hr="Skidded to well F-1 C. Installed hatches"',
              "R2-20160102-ACT-01": "comments=Ran in hole with BHA; phase=fixed"}
    for i in range(4, 30):                                  # filler so that rare tokens are rare
        bodies[f"R1-20160101-ACT-{i:02d}"] = f"comments=Routine step {i} circulation; phase=fixed"
    recs = pd.DataFrame({"record_id": list(bodies), "source_file": ["r1.xml" if k.startswith("R1") else "r2.xml" for k in bodies]})
    return Context("T", "", frozenset(bodies), bodies=bodies), recs


def test_a_weak_citation_is_dropped_only_if_another_from_the_same_report_remains():
    ctx, recs = repair_ctx()
    cited = ["R1-20160101-ACT-01", "R1-20160101-SUM-SUM24HR"]
    out, notes = repair_citations(cited, "The rig skidded to well F-1 C.", "skid per the summary", ctx, recs,
                                  mode="single_report", status="answered")
    assert out == ["R1-20160101-SUM-SUM24HR"] and notes and "dropped" in notes[0]       # hatches row has no overlap
    out, _ = repair_citations(["R1-20160101-ACT-01"], "The rig skidded to well F-1 C.", "r", ctx, recs,
                              mode="single_report", status="answered")
    assert out == ["R1-20160101-ACT-01"]                                                 # the only citation of its report stays


def test_supplement_only_for_answered_multi_report_and_at_most_two():
    ctx, recs = repair_ctx()
    kw = dict(ctx=ctx, records=recs)
    args = (["R1-20160101-ACT-01"], "The rig skidded cantilever to well F-1 C then installed hatches.", "skid")
    out, notes = repair_citations(*args, **kw, mode="multi_report", status="answered")
    assert "R1-20160101-ACT-02" in out and out[0] == "R1-20160101-ACT-01" and len(out) - 1 <= 2
    assert "added" in " ".join(notes)
    for mode, status in (("single_report", "answered"), ("multi_report", "partial"), ("archive_wide", "abstain")):
        out, _ = repair_citations(*args, **kw, mode=mode, status=status)
        assert "R1-20160101-ACT-02" not in out, (mode, status)


def test_a_good_answer_is_left_alone():
    ctx, recs = repair_ctx()
    cited = ["R1-20160101-ACT-02", "R1-20160101-SUM-SUM24HR"]
    out, notes = repair_citations(cited, "Skidded cantilever to well F-1 C.", "r", ctx, recs, mode="multi_report", status="answered")
    assert out == cited and notes == []


T2_017_ANSWER = ("The rig moved from well 15/9-F-15-D (its 2016-10-19 report: cut and pulled production riser, skidded rig to F-14) "
                 "to F-14, then to F-12 (cut and pulled riser on F-12 per forecast), then to F-11 B (skidded rig to F-11 B per F-12 "
                 "report of 2016-10-21), then to F-1 C (skidded to F-1 C per F-11 B and F-1 C reports on 2016-10-22), with the "
                 "forecast for the 2016-10-22 F-1 C report stating the next moves are to F-7 and then F-9 A.")
T2_017_CITED = ["F15D-20161019-SUM-SUM24HR", "F15D-20161019-FCST-FORECAST24HR", "F12-20161021-SUM-SUM24HR",
                "F12-20161021-FCST-FORECAST24HR", "F11B-20161022-ACT-07", "F1C-20161022-SUM-SUM24HR", "F1C-20161022-FCST-FORECAST24HR"]


@needs_data
def test_t2_017_hatches_row_is_supplemented_by_the_f1c_skid_row(located, reports):
    q = load_questions().set_index("question_id")["question_text"]["T2-017"]
    ctx = build_context("T2-017", q, route_question(q, reports), located)
    assert set(T2_017_CITED) <= ctx.ids
    out, notes = repair_citations(T2_017_CITED, T2_017_ANSWER, "sequence from the summaries and forecasts", ctx, located,
                                  mode="multi_report", status="answered")
    assert out[:7] == T2_017_CITED                                  # F-11-B has only ACT-07 cited, so it cannot be dropped
    assert "F1C-20161022-ACT-02" in out and len(out) <= 9           # "Skidded cantilever to well F-1 C" is supplemented
    assert any("added" in n and "ACT-02" in n for n in notes)


@needs_data
def test_repair_is_applied_in_the_pipeline_and_reaches_the_evidence(tmp_path, reports, located):
    q = load_questions().set_index("question_id")["question_text"]
    reply = {"status": "answered", "answer": T2_017_ANSWER, "cited_ids": T2_017_CITED, "rationale": "from the reports"}
    a, fake, _ = go(tmp_path, lambda s, u, m: reply, "T2-017", q, reports, located)
    assert "F1C-20161022-ACT-02" in a.cited_ids and set(T2_017_CITED) <= set(a.cited_ids)
    assert any(n.startswith("citation repair: added") for n in a.notes)
    assert "15_9_F_1_C_2016_10_22.xml F1C-20161022-ACT-02" in build_evidence(a, located)


# ---- 6. output hygiene -----------------------------------------------------------------------------------------------------------


def answer_with(notes, rationale="Short reason.", cited=None, absent=None, early=False, candidates=None):
    return Answer("T2-016", "q", "answered", "1.03 g/cm3", cited or [], rationale, 0.9, notes, "single_report",
                  candidates=candidates or [], absent=absent or {}, verified=True, early_abstain=early)


@needs_data
def test_predictions_notes_hold_only_the_rationale_and_flags_stay_in_answers_json(tmp_path, located):
    flags = ["run 1 reply truncated; retried m1", "first answer: verifier failed (m1); escalated to m2",
             "REVIEW: runs disagree (x)", "VERIFIER FAILED: numbers", "runs disagreed; arbitrated by m2"]
    a = answer_with(flags, rationale="The density is in the sample record.", cited=["F1C-20140326-FLUID-01"])
    path = write_predictions([a], located, tmp_path / "p.csv", order=["T2-016"])
    (row,) = list(csv.DictReader(path.open(encoding="utf-8")))
    assert row["notes"] == "The density is in the sample record."
    for word in ("retried", "escalated", "disagree", "VERIFIER", "arbitrated", "status=", "mode="):
        assert word not in row["notes"]
    saved = json.loads(save_answers_json([a], located, tmp_path / "a.json").read_text())[0]
    assert "REVIEW: runs disagree" in saved["notes"] and "retried" in saved["notes"]
    assert prediction_note(answer_with([], rationale="EARLY ABSTAIN: well X is not in the archive", early=True)) == \
        "well X is not in the archive"


@needs_data
def test_evidence_collapses_duplicate_file_and_page_references(located):
    ids = ["F1C-20140326-ACT-01", "F1C-20140326-ACT-02", "F1C-20140326-ACT-03", "F1C-20140326-SUM-SUM24HR"]
    ev = build_evidence(answer_with([], cited=ids), located)
    pdf_refs = [p for p in ev.split("; ") if ".pdf p." in p]
    assert len(pdf_refs) == len(set(pdf_refs)) == 1                                  # one reference for the one page
    assert pdf_refs[0].startswith("15_9_F_1_C_2014_03_26.pdf p.1 (") and "Operations" in pdf_refs[0] \
        and "Summary of activities (24 Hours)" in pdf_refs[0]
    assert ev.count(".xml F1C-20140326-") == 4                                       # every record still cited
    assert len(ev.split("; ")) == 1 + 4


@needs_data
def test_abstention_evidence_names_the_files_searched(tmp_path, located):
    qs = load_questions().set_index("question_id")["question_text"]
    reply = {"status": "abstain", "answer": "", "cited_ids": [], "rationale": "There is no cost line."}
    reports = __import__("submission.archive_qa.route", fromlist=["x"]).discover_reports(__import__("submission.archive_qa.config", fromlist=["x"]).XML_DIR)
    a, _, _ = go(tmp_path, lambda s, u, m: reply, "T2-025", qs, reports, located)
    ev = build_evidence(a, located)
    assert ev == "15_9_F_1_C_2014_03_26.pdf: all sections checked, no cost field"
    row = list(csv.DictReader(write_predictions([a], located, tmp_path / "p.csv", order=["T2-025"]).open()))[0]
    assert row["notes"].startswith("There is no cost line.") and "Searched 1 report(s)" in row["notes"] and "ABSENT" not in row["notes"]


@needs_data
def test_mud_logging_abstention_states_what_was_considered_and_rejected(tmp_path, located):
    from submission.archive_qa import config, route
    qs = load_questions().set_index("question_id")["question_text"]
    reports = route.discover_reports(config.XML_DIR)
    reply = {"status": "abstain", "answer": "", "cited_ids": [], "rationale": "No mud logging company is named."}
    a, _, _ = go(tmp_path, lambda s, u, m: reply, "T2-032", qs, reports, located)
    assert "Considered and rejected" in a.answer and "Western Atlas" in a.answer and "not a mud-logging service" in a.answer
    ev = build_evidence(a, located)
    assert ev.startswith("15_9_19_A_1997_08_29.pdf: all sections checked, no mud logging field")
    assert "considered and rejected" in ev and "Western Atlas" in ev and "ABSENT" not in ev
