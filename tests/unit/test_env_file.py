"""The .env is found through PARAKH_ENV_FILE, then ./.env, then the folder above the repo (D10, D19)."""

from __future__ import annotations

from pathlib import Path

import pytest

from parakh import config

# conftest stubs config.env_file in every test; keep the real one for these tests.
_real_env_file = config.env_file


def test_override_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "x.env"
    monkeypatch.setenv(config.ENV_FILE_VAR, str(target))
    assert _real_env_file() == target


def test_falls_back_to_parent_of_repo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = tmp_path / "parakh"
    repo.mkdir()
    (tmp_path / ".env").write_text("APP_ENV=test\n", encoding="utf-8")
    monkeypatch.delenv(config.ENV_FILE_VAR, raising=False)
    monkeypatch.setenv("DOTENV_PATH", str(tmp_path / "missing.env"))
    monkeypatch.setattr(config, "REPO_ROOT", repo)
    assert _real_env_file() == tmp_path / ".env"


def test_none_when_nothing_exists(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = tmp_path / "parakh"
    repo.mkdir()
    monkeypatch.delenv(config.ENV_FILE_VAR, raising=False)
    monkeypatch.setenv("DOTENV_PATH", str(tmp_path / "missing.env"))
    monkeypatch.setattr(config, "REPO_ROOT", repo)
    assert _real_env_file() is None
