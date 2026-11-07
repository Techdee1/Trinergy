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
