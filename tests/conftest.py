"""Shared fixtures. Tests that need the organiser data skip when it is not on disk."""

import pytest

from submission.archive_qa import config
from submission.archive_qa.locate import locate_all
from submission.archive_qa.parse import parse_all
from submission.archive_qa.wells import discover_reports

def _data_available() -> bool:
    try:
        return config.XML_DIR.exists() and config.PDF_DIR.exists()
    except FileNotFoundError:
        return False


@pytest.fixture(autouse=True)
def _no_ambient_api_key(monkeypatch):
    """Tests never see a developer's real key: no key variables, no .env files (tests that need either set them)."""
    from submission.archive_qa import llm
    for n in llm.KEY_ENV_NAMES:
        monkeypatch.delenv(n, raising=False)
    monkeypatch.setattr(llm, "env_files", lambda: [])


needs_data = pytest.mark.skipif(
    not _data_available(), reason="organiser Track 2 data not found (set NAPE_DATA_ROOT)")


@pytest.fixture(scope="session")
def reports():
    return discover_reports(config.XML_DIR)


@pytest.fixture(scope="session")
def parsed():
    df, stats = parse_all(config.XML_DIR)
    return df, stats


@pytest.fixture(scope="session")
def located(parsed):
    return locate_all(parsed[0], config.PDF_DIR)
