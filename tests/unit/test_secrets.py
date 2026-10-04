"""Secrets come from the environment; on scheduled runs SSM is loaded into it first (ADR-009)."""

from __future__ import annotations

from typing import Any

import pytest

from parakh import config, secrets


class FakeSSM:
    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self.pages = pages
        self.calls: list[dict[str, Any]] = []

    def get_parameters_by_path(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return self.pages[len(self.calls) - 1]


def _param(name: str, value: str) -> dict[str, str]:
    return {"Name": name, "Value": value}


@pytest.fixture(autouse=True)
def _fresh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(secrets, "_loaded_paths", set())
    for name in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "NTFY_TOPIC"):
        # set, then delete: monkeypatch then removes whatever the loader writes
        monkeypatch.setenv(name, "placeholder")
        monkeypatch.delenv(name)


def test_no_path_means_no_aws_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(secrets.SSM_PATH_VAR, raising=False)
    fake = FakeSSM([])
    assert secrets.load_ssm_environment(fake) == []
    assert fake.calls == []


def test_loads_every_page_into_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(secrets.SSM_PATH_VAR, "/parakh/prod/")
    fake = FakeSSM(
        [
            {"Parameters": [_param("/parakh/prod/TELEGRAM_BOT_TOKEN", "t-1")], "NextToken": "n"},
            {"Parameters": [_param("/parakh/prod/TELEGRAM_CHAT_ID", "42")]},
        ]
    )
    assert secrets.load_ssm_environment(fake) == ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]
    assert fake.calls[0] == {"Path": "/parakh/prod", "WithDecryption": True, "Recursive": False}
    assert fake.calls[1]["NextToken"] == "n"
    monkeypatch.setattr(config, "env_file", lambda: None)
    config.get_settings.cache_clear()
    token = config.get_settings().telegram_bot_token
    assert token is not None and token.get_secret_value() == "t-1"
    assert secrets.get_secret("TELEGRAM_CHAT_ID") == "42"
    # an optional secret that was never stored is None, not an error
    assert secrets.get_secret("NTFY_TOPIC") is None


def test_set_variable_wins_and_load_runs_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(secrets.SSM_PATH_VAR, "/parakh/prod")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "local")
    fake = FakeSSM([{"Parameters": [_param("/parakh/prod/TELEGRAM_CHAT_ID", "42")]}])
    assert secrets.load_ssm_environment(fake) == []
    assert secrets.get_secret("TELEGRAM_CHAT_ID") == "local"
    assert secrets.load_ssm_environment(fake) == []
    assert len(fake.calls) == 1


def test_odd_names_are_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(secrets.SSM_PATH_VAR, "/parakh/prod")
    fake = FakeSSM([{"Parameters": [_param("/parakh/prod/bad-name", "x")]}])
    assert secrets.load_ssm_environment(fake) == []
