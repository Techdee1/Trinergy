"""Paths, resolved in one place.

The Track 2 data root is the first of these candidates that contains
metadata/document_manifest.csv (relative paths are relative to the current directory):

  1. $NAPE_DATA_ROOT
  2. ./data/track_2
  3. ../data/track_2
  4. ../../data/track_2
  5. ../nape-aice-2026-hackathon/data/track_2
  6. external/nape-aice-2026-hackathon/data/track_2
  7. <repo root>/external/nape-aice-2026-hackathon/data/track_2   (so it also works from submission/)

If none qualifies, FileNotFoundError lists every path tried. Resolution is lazy: importing this
module never fails, but the first use of DATA_ROOT / XML_DIR / PDF_DIR / QUESTIONS_CSV does.
"""

from __future__ import annotations

import os
from pathlib import Path

SUBMISSION_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SUBMISSION_DIR.parent
INDEX_DIR = SUBMISSION_DIR / "indexes"
RECORDS_PATH = INDEX_DIR / "records.parquet"
ROUTING_REPORT_PATH = INDEX_DIR / "routing_report.csv"
LLM_CACHE_PATH = INDEX_DIR / "llm_cache.json"          # committed: lets reviewers run offline
COST_SUMMARY_PATH = INDEX_DIR / "cost_summary.csv"      # committed
ANSWERS_PATH = INDEX_DIR / "answers.json"               # committed: cited ids, status, rationale
PREDICTIONS_PATH = SUBMISSION_DIR / "predictions.csv"
LOGS_DIR = REPO_ROOT / "logs"                           # git-ignored
COST_LEDGER_PATH = LOGS_DIR / "cost_ledger.csv"
CONTEXT_DUMP_DIR = LOGS_DIR / "context_dumps"

# ---- LLM defaults (tools/llm_bench/RECOMMENDATION.md). Environment / .env variables override them (see .env.example).
LLM_MODEL_PRIMARY_DEFAULT = "anthropic/claude-haiku-5.5"
LLM_MODEL_ESCALATION_DEFAULT = "anthropic/claude-sonnet-5.5"
LLM_PRIMARY_MAX_TOKENS_DEFAULT = 400          # LLM_MAX_TOKENS
LLM_ESCALATION_MAX_TOKENS_DEFAULT = 1500      # LLM_ESCALATION_MAX_TOKENS
LLM_RETRY_MAX_TOKENS_DEFAULT = 1500           # LLM_RETRY_MAX_TOKENS: one primary-model retry after a truncated/invalid reply
LLM_PRIMARY_REASONING_DEFAULT = "none"        # LLM_REASONING  (Haiku accepts "none")
LLM_ESCALATION_REASONING_DEFAULT = "minimal"  # LLM_ESCALATION_REASONING (Sonnet/Opus reasoning is mandatory: "none" is HTTP 400)
LLM_PROVIDER_DEFAULT = "Anthropic"            # LLM_PROVIDER: comma list pinned via provider.order; "" = no pin
LLM_CONCURRENCY_DEFAULT = 8                   # LLM_CONCURRENCY

MARKER = Path("metadata") / "document_manifest.csv"
_EXTERNAL = Path("external") / "nape-aice-2026-hackathon" / "data" / "track_2"


def candidate_roots() -> list[Path]:
    cwd = Path.cwd()
    cands: list[Path] = []
    env = os.environ.get("NAPE_DATA_ROOT")
    if env:
        cands.append(Path(env))
    cands += [
        cwd / "data" / "track_2",
        cwd / ".." / "data" / "track_2",
        cwd / ".." / ".." / "data" / "track_2",
        cwd / ".." / "nape-aice-2026-hackathon" / "data" / "track_2",
        cwd / _EXTERNAL,
        REPO_ROOT / _EXTERNAL,
    ]
    return cands


def find_data_root() -> Path:
    tried = candidate_roots()
    for c in tried:
        if (c / MARKER).is_file():
            return c.resolve()
    raise FileNotFoundError(
        f"Cannot find the Track 2 data (no folder containing {MARKER.as_posix()}). Paths tried:\n"
        + "\n".join(f"  - {c}" for c in tried)
        + "\nSet NAPE_DATA_ROOT to the folder that contains documents/, metadata/ and open_test/."
    )


_cache: dict[str, Path] = {}


def _derived(name: str) -> Path:
    if "root" not in _cache:
        _cache["root"] = find_data_root()
    root = _cache["root"]
    reports = root / "documents" / "daily_drilling_reports"
    return {
        "DATA_ROOT": root,
        "REPORTS_DIR": reports,
        "XML_DIR": reports / "Daily_Drilling_Report___XML_Version",
        "PDF_DIR": reports / "Daily_Drilling_report___PDF_Version",
        "QUESTIONS_CSV": root / "open_test" / "open_test_questions.csv",
    }[name]


def __getattr__(name: str) -> Path:  # PEP 562: lazy DATA_ROOT, XML_DIR, ...
    if name in ("DATA_ROOT", "REPORTS_DIR", "XML_DIR", "PDF_DIR", "QUESTIONS_CSV"):
        return _derived(name)
    raise AttributeError(name)


def check() -> dict:
    """What exists; never raises (used by the notebook's config check)."""
    try:
        root = _derived("DATA_ROOT")
    except FileNotFoundError as e:
        return {"DATA_ROOT": None, "error": str(e), "xml_reports": 0, "pdf_reports": 0,
                "questions_csv": False, "records_parquet": RECORDS_PATH.exists()}
    return {
        "DATA_ROOT": str(root),
        "xml_reports": len(list(_derived("XML_DIR").glob("*.xml"))),
        "pdf_reports": len(list(_derived("PDF_DIR").glob("*.pdf"))),
        "questions_csv": _derived("QUESTIONS_CSV").exists(),
        "records_parquet": RECORDS_PATH.exists(),
    }
