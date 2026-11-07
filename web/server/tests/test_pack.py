"""The server runs from the data pack only. (The physical proof, with the organiser files absent, is in web/DEPLOY.md / the report:
the whole suite is run in a clean clone that has no external/ folder.)"""

import builtins
import json
import os
import pathlib
import random

import pandas as pd
import pymupdf
import pytest

from submission.archive_qa import config
from web.server import build_data
from web.server.app import create_app
from web.server.engine import Engine

from . import conftest as C

RAW_MARKERS = ("daily_drilling_reports", "open_test_questions", "nape-aice-2026-hackathon")


def _raw(p) -> bool:
    s = str(p).replace("\\", "/").lower()
    return any(m in s for m in RAW_MARKERS)


@pytest.fixture
def no_raw_access(monkeypatch):
    """Any attempt to open/list/read a path inside the organiser data raises. Active while the engine is built and used."""
    hits = []

    def guard(real):
        def f(*a, **k):
            p = a[0] if a else next((k[n] for n in ("file", "filename", "path", "stream") if n in k), "")
            if isinstance(p, (str, bytes, os.PathLike)) and _raw(p):
                hits.append(str(p))
                raise AssertionError(f"raw organiser file touched: {p}")
            return real(*a, **k)
        return f
    monkeypatch.setattr(builtins, "open", guard(builtins.open))
    monkeypatch.setattr(pymupdf, "open", guard(pymupdf.open))
    for name in ("read_bytes", "read_text", "open", "glob", "iterdir", "rglob"):
        real = getattr(pathlib.Path, name)
        monkeypatch.setattr(pathlib.Path, name, guard(real))      # first argument is `self`, a Path: checked like a path string
    yield hits


def test_server_never_touches_raw_files(tmp_path, no_raw_access):
    e = Engine(C.make_settings(tmp_path))
    try:
        from fastapi.testclient import TestClient
        with TestClient(create_app(engine=e)) as c:
            e.warm()
            assert c.get("/questions").json()["count"] == 72
            assert c.get("/questions/T2-017").status_code == 200
            assert c.get("/archive").json()["reports"][0]["pages"] >= 1
            assert c.get("/trajectories").status_code == 200 and c.get("/costs").status_code == 200
            g = c.get("/generalisation").json()
            assert g["available"] and len(g["questions"]) == 40
            assert c.get("/pages/19A-19970829-ACT-04.png").status_code == 200
            assert c.get("/pages/19A-19970829-ACT-04/boxes").json()["boxes"]
            early = c.post("/ask", json={"question": "What was the measured depth in the report for well F-99 on 2013-08-12?"}).json()
            assert early["status"] == "abstain" and "document_manifest.csv" in early["evidence"]       # manifest read from the pack's copy
        assert str(config.DATA_ROOT).startswith(str(e.pack.root)), "the pipeline's data root must be the pack's manifest-only root"
    finally:
        e.close()
    assert no_raw_access == []


def test_pack_replays_every_catalog_question_from_caches(engine):
    for c in engine.catalog:
        d = engine.replayed(c["id"])
        assert d.status != "not_evaluated", c["id"]
        assert all(m.outcome == "cache_hit" for m in d.trace.model_calls), c["id"]


def test_pack_size_and_manifest(engine):
    m = engine.pack.manifest
    assert m["records"] == len(engine.records) and m["reports"] == 32 and m["pages"] == 54 and m["boxes"] == len(engine.pack.boxes)
    assert m["total_bytes"] < 25_000_000 and m["attribution"] == "Data: Equinor Volve dataset"
    total = sum(p.stat().st_size for p in engine.pack.root.rglob("*") if p.is_file())
    assert total < 25_000_000


# ---- consistency of the pack with its sources (needs the organiser files: skipped where they are absent, e.g. a clean clone)
def _raw_root():
    """The organiser data root on this machine, found without config (which the engine has pointed at the pack)."""
    for c in config.candidate_roots():
        if (c / config.MARKER).is_file() and "web/server/data" not in str(c.resolve()).replace("\\", "/"):
            return c.resolve()
    return None


RAW = _raw_root()


@pytest.mark.skipif(RAW is None or not config.RECORDS_PATH.exists(), reason="organiser data not on this machine (the pack is what a deployment uses)")
def test_pack_matches_its_sources(engine):
    from web.server.highlight import HighlightBuilder, PageError
    pdf_dir = RAW / "documents" / "daily_drilling_reports" / "Daily_Drilling_report___PDF_Version"
    src = pd.read_parquet(config.RECORDS_PATH)
    assert src.equals(engine.records)
    hb = HighlightBuilder(src, pdf_dir)
    for rid in random.Random(7).sample(list(src["record_id"]), 60):
        try:
            assert hb.boxes(rid) == engine.pack.boxes[rid], rid
        except PageError as e:
            assert engine.pack.boxes[rid]["error"]["code"] == e.code
    from web.server.costs_view import generalisation
    gen_dir = config.SUBMISSION_DIR / "eval" / "generalisation"
    if (gen_dir / "results.json").exists():
        assert generalisation(gen_dir) == engine.pack.generalisation()
