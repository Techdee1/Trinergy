"""Server configuration, all from environment variables (never from code). The OpenRouter key is NOT read here:
it is found by the submission's own `llm.find_key`, and only its presence is ever reported."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VERSION = "0.1.0"


def _f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def _i(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass
class Settings:
    runtime_dir: Path = field(default_factory=lambda: Path(os.environ.get("RUNTIME_CACHE_DIR") or REPO_ROOT / "web" / "server" / ".runtime"))
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("SERVER_DATA_DIR") or REPO_ROOT / "web" / "server" / "data"))
    server_budget_usd: float = field(default_factory=lambda: _f("SERVER_BUDGET_USD", 2.00))
    allowed_origins: list[str] = field(default_factory=lambda: [
        o.strip() for o in (os.environ.get("ALLOWED_ORIGINS") or "http://localhost:3000,http://localhost:5173").split(",") if o.strip()])
    rate_per_min: int = field(default_factory=lambda: _i("RATE_LIMIT_PER_MIN", 6))
    rate_per_day: int = field(default_factory=lambda: _i("RATE_LIMIT_PER_DAY", 40))
    max_question_chars: int = field(default_factory=lambda: _i("MAX_QUESTION_CHARS", 400))
    ask_timeout_s: float = field(default_factory=lambda: _f("ASK_TIMEOUT_S", 120.0))
    max_concurrent_asks: int = field(default_factory=lambda: _i("MAX_CONCURRENT_ASKS", 4))
    trusted_proxy_hops: int = field(default_factory=lambda: max(1, _i("TRUSTED_PROXY_HOPS", 1)))
    trust_proxy: bool = field(default_factory=lambda: os.environ.get("TRUST_PROXY", "0") == "1")
    trajectory_min_stations: int = field(default_factory=lambda: _i("TRAJECTORY_MIN_STATIONS", 3))
    warm_on_start: bool = field(default_factory=lambda: os.environ.get("WARM_ON_START", "1") != "0")
