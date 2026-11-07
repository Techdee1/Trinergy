import pytest

from src import llm


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Point all data/ledger paths at tmp and use known prices. Blocks real API clients."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LEDGER_PATH", str(tmp_path / "cost_ledger.csv"))
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_BASE_URL", "")
    monkeypatch.setenv("LLM_PRICE_INPUT_PER_1M", "2.0")
    monkeypatch.setenv("LLM_PRICE_OUTPUT_PER_1M", "8.0")
    monkeypatch.setenv("LLM_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("LLM_RETRY_MAX_WAIT", "0")

    def no_real_clients(*args, **kwargs):
        raise AssertionError("Tests must not create real LLM clients")

    monkeypatch.setattr(llm, "_get_client", no_real_clients)
    return tmp_path
