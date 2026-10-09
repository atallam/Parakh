"""LLM failure alerts (P4), prompt-pin rollback (P3) and the Anthropic 429 path (P5)."""

from __future__ import annotations

from typing import Any

import pytest

from parakh.agents.health import llm_health, render_llm_alert
from parakh.audit.events import AUD
from parakh.configs import load_all
from parakh.prompts import rollback as rb

CFG = load_all().agents.alerts


class Ev:
    def __init__(self, t: AUD) -> None:
        self.event_type = t


def events(**counts: int) -> Any:
    names = {"runs": AUD.AGENT_END, "invalid": AUD.LLM_VALIDATION_FAIL, "budget": AUD.LLM_BUDGET_STOP,
             "turns": AUD.AGENT_TURN_LIMIT, "inject": AUD.LLM_INJECTION_SUSPECTED, "cites": AUD.LLM_CITATION_UNVERIFIED}  # fmt: skip
    return [Ev(names[k]) for k, n in counts.items() for _ in range(n)]


@pytest.mark.ac("AC-F25.2")
def test_a_clean_run_sends_nothing() -> None:
    assert llm_health(events(runs=20, invalid=1), CFG) == []
    assert render_llm_alert([]) is None


@pytest.mark.ac("AC-F25.2")
@pytest.mark.parametrize("kind", ["budget", "turns", "inject"])
def test_one_hard_stop_alerts_immediately(kind) -> None:
    reasons = llm_health(events(runs=1, **{kind: 1}), CFG)
    assert len(reasons) == 1


@pytest.mark.ac("AC-F25.2")
def test_rates_alert_only_above_the_limit_and_with_enough_runs() -> None:
    assert llm_health(events(runs=10, invalid=1), CFG) == []  # exactly 10%
    assert any("validation" in r for r in llm_health(events(runs=10, invalid=2), CFG))
    assert llm_health(events(runs=2, invalid=2), CFG) == []  # too few runs to say
    assert any("quotes" in r for r in llm_health(events(runs=10, cites=3), CFG))


def test_the_alert_is_one_short_message() -> None:
    msg = render_llm_alert(["a", "b"])
    assert msg and msg.text.count("\n") <= 5 and "qualitative pending" in msg.text


# ---- prompt pins --------------------------------------------------------------------------------
@pytest.fixture
def registry(tmp_path, monkeypatch):
    (tmp_path / "qualitative").mkdir()
    for v in ("v1", "v2"):
        (tmp_path / "qualitative" / f"{v}.yaml").write_text("user: x\n", encoding="utf-8")
    reg = tmp_path / "registry.yaml"
    reg.write_text(
        "prompts:\n  qualitative:\n    active: v2\n    history:\n      - {version: v1, date: 2026-12-01, note: first}\n      - {version: v2, date: 2027-01-05, note: tighter quotes}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(rb, "REGISTRY", reg)
    monkeypatch.setattr("parakh.prompts.PROMPTS_DIR", tmp_path)
    monkeypatch.setattr(rb, "PROMPTS_DIR", tmp_path)
    return reg


def test_rollback_moves_the_pin_back_and_is_audited(registry) -> None:
    from parakh.audit.emit import get_sink

    assert rb.rollback("qualitative", reason="quotes failed 30% of checks") == "v1"
    assert "active: v1" in registry.read_text(encoding="utf-8")
    ev = [e for e in get_sink().events() if e.event_type == AUD.PROMPT_ROLLED_BACK]
    assert len(ev) == 1 and ev[0].before == {"active": "v2"} and ev[0].after == {"active": "v1"}
    assert "history" in registry.read_text(encoding="utf-8")  # history is kept, not rewritten


def test_rollback_needs_a_reason_and_an_earlier_version(registry) -> None:
    with pytest.raises(rb.PinError):
        rb.rollback("qualitative", reason=" ")
    rb.rollback("qualitative", reason="bad")
    with pytest.raises(rb.PinError):
        rb.rollback("qualitative", reason="again")  # v1 has nothing earlier
    assert rb.promote("qualitative", "v2", reason="fixed") == "v2"
    with pytest.raises(rb.PinError):
        rb.promote("qualitative", "v9", reason="no such version")
