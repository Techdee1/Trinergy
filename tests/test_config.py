from pathlib import Path

import pytest

from submission.archive_qa import config


def make_root(base: Path) -> Path:
    root = base / "data" / "track_2"
    (root / "metadata").mkdir(parents=True)
    (root / "metadata" / "document_manifest.csv").write_text("document_id\n")
    return root


@pytest.fixture
def clean(monkeypatch, tmp_path):
    monkeypatch.delenv("NAPE_DATA_ROOT", raising=False)
    monkeypatch.setattr(config, "REPO_ROOT", tmp_path / "no_repo")  # hide the real external/ clone
    return tmp_path


def test_env_var_wins(monkeypatch, clean):
    env_root = make_root(clean / "elsewhere")
    cwd_root = make_root(clean / "cwd")
    monkeypatch.chdir(clean / "cwd")
    monkeypatch.setenv("NAPE_DATA_ROOT", str(env_root))
    assert config.find_data_root() == env_root.resolve()
    assert cwd_root.exists()


def test_invalid_env_falls_through_to_cwd(monkeypatch, clean):
    cwd_root = make_root(clean / "cwd")
    monkeypatch.chdir(clean / "cwd")
    monkeypatch.setenv("NAPE_DATA_ROOT", str(clean / "missing"))
    assert config.find_data_root() == cwd_root.resolve()


@pytest.mark.parametrize("sub, depth", [("a", 1), ("a/b", 2)])
def test_parent_directories(monkeypatch, clean, sub, depth):
    root = make_root(clean)  # <clean>/data/track_2
    work = clean / sub
    work.mkdir(parents=True)
    monkeypatch.chdir(work)
    assert config.find_data_root() == root.resolve()


def test_sibling_clone_and_external(monkeypatch, clean):
    sib = clean / "nape-aice-2026-hackathon" / "data" / "track_2"
    (sib / "metadata").mkdir(parents=True)
    (sib / "metadata" / "document_manifest.csv").write_text("x")
    work = clean / "mine"
    work.mkdir()
    monkeypatch.chdir(work)
    assert config.find_data_root() == sib.resolve()

    ext = clean / "other" / "proj" / "external" / "nape-aice-2026-hackathon" / "data" / "track_2"
    (ext / "metadata").mkdir(parents=True)
    (ext / "metadata" / "document_manifest.csv").write_text("x")
    monkeypatch.chdir(clean / "other" / "proj")
    assert config.find_data_root() == ext.resolve()


def test_marker_file_required(monkeypatch, clean):
    (clean / "data" / "track_2").mkdir(parents=True)  # folder exists, no manifest
    monkeypatch.chdir(clean)
    with pytest.raises(FileNotFoundError):
        config.find_data_root()


def test_error_lists_every_path_tried(monkeypatch, clean):
    monkeypatch.chdir(clean)
    monkeypatch.setenv("NAPE_DATA_ROOT", str(clean / "nope"))
    tried = config.candidate_roots()
    assert len(tried) == 7
    with pytest.raises(FileNotFoundError) as e:
        config.find_data_root()
    for c in tried:
        assert str(c) in str(e.value)
    assert "NAPE_DATA_ROOT" in str(e.value)


def test_check_never_raises(monkeypatch, clean):
    monkeypatch.chdir(clean)
    monkeypatch.setattr(config, "_cache", {})
    out = config.check()
    assert out["DATA_ROOT"] is None and "Paths tried" in out["error"]
