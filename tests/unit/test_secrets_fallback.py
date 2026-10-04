"""Secrets: the environment wins; with no AWS role assumed, prod does not call SSM."""

from __future__ import annotations

from parakh import secrets


def test_prod_without_aws_credentials_returns_env_value_or_none(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.setenv("MAIL_TO", "me@example.com")
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    from parakh.config import get_settings

    get_settings.cache_clear()
    secrets.get_secret.cache_clear()
    try:
        assert secrets.get_secret("MAIL_TO") == "me@example.com"
        assert secrets.get_secret("NTFY_TOPIC") is None
    finally:
        get_settings.cache_clear()
        secrets.get_secret.cache_clear()
