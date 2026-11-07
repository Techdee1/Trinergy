"""The frozen submission stays frozen: tracing and live asks change none of its files, outputs, cache keys or contexts."""

import csv
import os

from submission.archive_qa import answer as qa, config, write
from submission.archive_qa.route import route_question

from . import conftest as C
from .test_ask import UNCACHED, UNCACHED2


def _snapshot():
    """(path, size, mtime) of everything the submission ships, except bytecode."""
    out = {}
    root = config.SUBMISSION_DIR
    for p in list(root.glob("archive_qa/*.py")) + list(root.glob("indexes/*")) + [config.PREDICTIONS_PATH, root / "solution.ipynb"]:
        if p.is_file() and p.name != "llm_cache_runtime.json":       # the notebook's own git-ignored runtime cache
            st = p.stat()
            out[str(p)] = (st.st_size, st.st_mtime_ns)
    return out


def test_predictions_byte_identical_through_the_traced_path(engine, tmp_path):
    questions = [c for c in engine.catalog if c["set"] == "challenge"]
    import pandas as pd
    qdf = pd.DataFrame({"question_id": [c["id"] for c in questions], "question_text": [c["question"] for c in questions]})
    answers = qa.answer_all(qdf, engine.records, engine.reports, engine.replay_llm, dump=False, strict=True)    # wrappers are installed
    out = write.write_predictions(answers, engine.records, tmp_path / "predictions.csv")
    assert out.read_bytes() == config.PREDICTIONS_PATH.read_bytes()


def test_api_answers_equal_predictions_csv(engine):
    with config.PREDICTIONS_PATH.open(encoding="utf-8", newline="") as f:
        rows = {r["question_id"]: r for r in csv.DictReader(f)}
    for qid, r in rows.items():
        d = engine.replayed(qid)
        assert (d.answer, d.evidence, f"{d.confidence:.2f}") == (r["answer"], r["evidence"], r["confidence"]), qid


def test_cache_keys_and_contexts_unchanged(engine):
    """Same cache keys: every call of every challenge question is a hit in the committed cache, nothing is written, and the
    contexts built through the wrappers equal the contexts built by the original functions."""
    from submission.archive_qa import context as ctxmod
    for c in engine.catalog:
        if c["set"] != "challenge":
            continue
        d = engine.replayed(c["id"])
        assert all(m.outcome == "cache_hit" for m in d.trace.model_calls), c["id"]
        res = route_question(c["question"], engine.reports)
        if not res.early_abstain:
            orig = ctxmod.build_context(c["id"], c["question"], res, engine.records)
            assert d.trace.contexts[0].lines == orig.n_lines and {r.id for r in d.trace.contexts[0].records} == set(orig.ids), c["id"]
    assert not engine.runtime_cache.path.exists() or not engine.runtime_cache.entries


def test_live_ask_changes_no_committed_file(fake_engine, fake_client):
    before, snap = C.frozen_hashes(), _snapshot()
    ledger = config.COST_LEDGER_PATH
    ledger_before = (ledger.stat().st_size, ledger.stat().st_mtime_ns) if ledger.exists() else None
    d = fake_client.post("/ask", json={"question": UNCACHED}).json()
    assert d["source"] == "live" and d["trace"]["totals"]["live_calls"] >= 1
    fake_client.post("/ask", json={"question": UNCACHED2})
    q1 = fake_client.get("/questions/T2-001").json()["question"]
    fake_client.post("/ask", json={"question": q1})                      # a cached question through the same path
    assert C.frozen_hashes() == before, "a committed file changed"
    assert "missing" not in before.values() and len(before) == 4          # the four frozen files exist and are hashed
    assert _snapshot() == snap, "a file under submission/ changed"
    assert ((ledger.stat().st_size, ledger.stat().st_mtime_ns) if ledger.exists() else None) == ledger_before   # logs/cost_ledger.csv untouched
    # the live answer went to the RUNTIME cache, in the server's own directory
    assert fake_engine.runtime_cache.path.parent == fake_engine.s.runtime_dir
    assert fake_engine.runtime_cache.path.exists() and len(fake_engine.runtime_cache.entries) >= 2
    assert str(fake_engine.runtime_cache.path).startswith(str(fake_engine.s.runtime_dir)) and config.LLM_CACHE_PATH != fake_engine.runtime_cache.path
