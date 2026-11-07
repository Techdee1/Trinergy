"""The human key must never influence predictions: archive_qa must not import from eval."""
import ast
import os
from pathlib import Path

import pytest

from submission.archive_qa import config
from submission.archive_qa.context import build_context
from submission.archive_qa.llm import Cache, cache_key
from submission.archive_qa.answer import SYSTEM_PROMPT
from submission.archive_qa.route import discover_reports, load_questions, route_question
from tests.conftest import needs_data

PKG = Path(config.SUBMISSION_DIR) / "archive_qa"


def test_archive_qa_never_imports_eval():
    offenders = []
    for py in PKG.glob("*.py"):
        for node in ast.walk(ast.parse(py.read_text(encoding="utf-8"))):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods = [("." * node.level) + (node.module or "")] + [a.name for a in node.names]
            if any(part == "eval" for m in mods for part in m.replace("..", ".").split(".")):
                offenders.append(f"{py.name}: {mods}")
    assert not offenders, offenders


def test_archive_qa_never_reads_the_key_files():
    for py in PKG.glob("*.py"):
        src = py.read_text(encoding="utf-8")
        assert "key_template" not in src and "key.csv" not in src, py.name


@pytest.mark.skipif(os.environ.get("CHECK_CACHE") != "1", reason="set CHECK_CACHE=1 to check the committed cache")
@needs_data
def test_all_32_questions_are_in_the_cache(located):
    cache = Cache(config.LLM_CACHE_PATH)
    models = cache.meta.get("models", {})
    assert models.get("primary"), "cache has no recorded model names"
    reports = discover_reports(config.XML_DIR)
    missing = []
    for q in load_questions().itertuples(index=False):
        r = route_question(q.question_text, reports)
        if r.early_abstain:
            continue  # answered without an LLM call
        ctx = build_context(q.question_id, q.question_text, r, located)
        key = cache_key(SYSTEM_PROMPT, ctx.text, q.question_text, "", models["primary"], cache.meta["settings"])
        if cache.get(key) is None:
            missing.append(q.question_id)
    assert not missing, f"not in cache: {missing}"


# ---- the committed cache must be committable and offline misses must be loud ------------------------------


def test_llm_cache_is_not_gitignored():
    import shutil
    import subprocess

    if shutil.which("git") is None:
        pytest.skip("git not available")
    rel = "submission/indexes/llm_cache.json"
    r = subprocess.run(["git", "check-ignore", "-q", rel], cwd=config.REPO_ROOT)
    assert r.returncode == 1, f"{rel} is gitignored (check-ignore exit {r.returncode}); reviewers need it committed"
    # the other committed artefacts too; derived/raw-data files stay ignored
    for ok in ("submission/indexes/answers.json", "submission/indexes/cost_summary.csv", "submission/predictions.csv"):
        assert subprocess.run(["git", "check-ignore", "-q", ok], cwd=config.REPO_ROOT).returncode == 1, ok
    for ignored in ("submission/indexes/records.parquet", "logs/cost_ledger.csv", ".env"):
        assert subprocess.run(["git", "check-ignore", "-q", ignored], cwd=config.REPO_ROOT).returncode == 0, ignored


@needs_data
def test_offline_cache_miss_surfaces_as_cachemiss_not_a_silent_abstain(tmp_path, located):
    from submission.archive_qa import answer as A
    from submission.archive_qa.llm import LLM, CacheMiss, LLMConfig

    reports = discover_reports(config.XML_DIR)
    llm = LLM(LLMConfig(primary="m1", escalation="m2", live=False), None, Cache(tmp_path / "empty.json"), tmp_path / "l.csv")
    q = "What was the density of the NaCl brine sampled from the active pit on well 15/9-F-1-C on 2014-03-26?"
    with pytest.raises(CacheMiss) as e:
        A.answer_question("T2-016", q, located, reports, llm, dump=False)
    msg = str(e.value)
    assert "T2-016" in msg and "Offline mode" in msg and "llm_cache.json" in msg and "LIVE = True" in msg
    # early abstains never need the cache, so they still work offline
    q2 = "What did the report for well 15/9-F-14 on 2013-06-10 say?"
    assert A.answer_question("T2-027", q2, located, reports, llm, dump=False).early_abstain
