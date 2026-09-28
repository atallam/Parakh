"""PII never reaches the model (C6.3); credentials never reach the logs (C6.2, C6.5)."""

from parakh.observability.logging import redact_credentials, scrub_secrets
from parakh.privacy import contains_pii, redact_pii


def test_redacts_common_pii() -> None:
    text = "Mail a.b@example.com, call +91 98765 43210 or 9876543210, PAN ABCDE1234F."
    clean = redact_pii(text)
    assert "example.com" not in clean
    assert "9876543210" not in clean
    assert "ABCDE1234F" not in clean
    assert not contains_pii(clean)


def test_plain_text_is_untouched() -> None:
    text = "Revenue grew 12% to 4,500 crore in FY26."
    assert redact_pii(text) == text


def test_credential_fields_are_redacted() -> None:
    event = {"event": "x", "api_key": "sk-ant-123", "telegram_bot_token": "1:abc", "n": 1}
    out = redact_credentials(None, "info", dict(event))
    assert out["api_key"] == "[REDACTED]"
    assert out["telegram_bot_token"] == "[REDACTED]"
    assert out["n"] == 1


def test_secret_values_are_scrubbed_anywhere() -> None:
    event = {
        "event": "oops",
        "message": "key sk-ant-api03-abcdefghijklmnop leaked",
        "nested": {"note": "bot 1234567890:AAHabcdefghijklmnopqrstuvwxyz0123456"},
    }
    out = scrub_secrets(None, "info", event)
    assert "sk-ant" not in out["message"]
    assert "AAH" not in out["nested"]["note"]
