"""Nothing private reaches the logs (AC-F21.11; plan 13 P6). T-AUD-10…"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
import structlog

from parakh.observability.logging import configure_logging
from parakh.privacy import redact_pii

CAS = Path(__file__).resolve().parents[1] / "fixtures" / "cas" / "synthetic_cas_2026-09.json"


def _log_output(monkeypatch: pytest.MonkeyPatch, **fields: object) -> str:
    buf = io.StringIO()
    monkeypatch.setattr("sys.stderr", buf)
    configure_logging()
    structlog.get_logger("test").info("holding.seen", **fields)
    return buf.getvalue()


@pytest.mark.ac("AC-F21.11")
def test_cas_identifiers_never_reach_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    """T-AUD-10: PAN, e-mail, mobile, DP/client and BO IDs from the synthetic CAS."""
    cas = json.loads(CAS.read_text(encoding="utf-8"))
    inv = cas["investor_info"]
    nsdl, _, cdsl = cas["accounts"]
    text = (
        f"statement for {inv['pan']} {inv['email']} {inv['mobile']} "
        f"DP {nsdl['dp_id']} client {nsdl['dp_id']}{nsdl['client_id']} BO {cdsl['bo_id']}"
    )
    out = _log_output(monkeypatch, note=text, nested={"line": text})
    for secret in (
        inv["pan"],
        inv["email"],
        inv["mobile"],
        nsdl["dp_id"],
        nsdl["client_id"],
        cdsl["bo_id"],
    ):
        assert secret not in out


@pytest.mark.ac("AC-F21.11")
def test_holdings_quantities_and_amounts_never_reach_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    """T-AUD-11: fields named like quantities or rupee amounts are masked, at any depth."""
    out = _log_output(
        monkeypatch,
        isin="INE040A01034",
        quantity=120,
        cost_basis=1650.5,
        nested={"qty": 777, "value_inr": 198060},
    )
    record = json.loads(out.strip().splitlines()[-1])
    assert record["isin"] == "INE040A01034"  # ISINs are not private
    assert record["quantity"] == record["cost_basis"] == "[REDACTED]"
    assert record["nested"] == {"qty": "[REDACTED]", "value_inr": "[REDACTED]"}
    assert "777" not in out and "198060" not in out


@pytest.mark.ac("AC-F21.11")
def test_secrets_never_reach_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    """T-AUD-12"""
    token = "123456789:" + "A" * 35
    out = _log_output(monkeypatch, telegram_bot_token=token, note=f"sent with {token}")
    assert token not in out


def test_isins_survive_redaction() -> None:
    """T-AUD-13: redaction must not eat the security key."""
    assert redact_pii("INE646L01027 INE0HOQ01053") == "INE646L01027 INE0HOQ01053"
