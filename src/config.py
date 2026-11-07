"""Settings loaded from .env / environment variables.

Call get_settings() where you need config; it re-reads the environment each
time so tests can override values with monkeypatch.setenv.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

load_dotenv(ROOT / ".env", override=False)


def _float(name: str, default: float) -> float:
    return float(os.getenv(name) or default)


def _int(name: str, default: int) -> int:
    return int(os.getenv(name) or default)


@dataclass(frozen=True)
class Settings:
    llm_provider: str
    llm_api_key: str
    llm_model: str
    llm_base_url: str | None
    price_input_per_1m: float
    price_output_per_1m: float
    max_output_tokens: int
    max_attempts: int
    retry_max_wait: float
    render_dpi: int
    image_max_side: int
    raw_dir: Path
    pages_dir: Path
    cache_dir: Path
    output_dir: Path
    ledger_path: Path


def get_settings() -> Settings:
    data_dir = Path(os.getenv("DATA_DIR") or DATA_DIR)
    return Settings(
        llm_provider=(os.getenv("LLM_PROVIDER") or "openai").strip().lower(),
        llm_api_key=os.getenv("LLM_API_KEY") or "",
        llm_model=os.getenv("LLM_MODEL") or "",
        llm_base_url=os.getenv("LLM_BASE_URL") or None,
        price_input_per_1m=_float("LLM_PRICE_INPUT_PER_1M", 0.0),
        price_output_per_1m=_float("LLM_PRICE_OUTPUT_PER_1M", 0.0),
        max_output_tokens=_int("LLM_MAX_OUTPUT_TOKENS", 1024),
        max_attempts=_int("LLM_MAX_ATTEMPTS", 4),
        retry_max_wait=_float("LLM_RETRY_MAX_WAIT", 30.0),
        render_dpi=_int("RENDER_DPI", 150),
        image_max_side=_int("IMAGE_MAX_SIDE", 1600),
        raw_dir=data_dir / "raw",
        pages_dir=data_dir / "pages",
        cache_dir=data_dir / "cache",
        output_dir=data_dir / "output",
        ledger_path=Path(os.getenv("LEDGER_PATH") or ROOT / "cost_ledger.csv"),
    )
