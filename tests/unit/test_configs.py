"""Config schemas (plan 04 §3.2). T-CFG-01…"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from parakh.config import REPO_ROOT
from parakh.configs import ConfigError, load_all
from parakh.configs.models import AgentConfig, isin_check_digit_ok


def test_repo_config_validates() -> None:
    """T-CFG-01: the exit-gate check 'config validates'."""
    bundle = load_all()
    assert bundle.universe.mode == "pilot"
    assert len(bundle.universe.pilot) == 7
    assert {s.symbol for s in bundle.universe.golden} == {"HDFCBANK", "INDIGO", "M&M"}  # D18
    assert bundle.flags.alerts.dry_run is True


@pytest.mark.parametrize(
    ("isin", "ok"),
    [
        ("INE040A01034", True),
        ("INE101A01026", True),
        ("INE0HOQ01053", True),
        ("US0378331005", True),
        ("INE040A01035", False),  # wrong check digit
        ("INE040A0103", False),  # too short
        ("ine040a01034", False),
    ],
)
def test_isin_check_digit(isin: str, ok: bool) -> None:
    """T-CFG-02"""
    assert isin_check_digit_ok(isin) is ok


def test_a_typo_in_an_isin_stops_the_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """T-CFG-03"""
    cfg = tmp_path / "config"
    shutil.copytree(REPO_ROOT / "config", cfg)
    universe = cfg / "universe.yaml"
    universe.write_text(
        universe.read_text(encoding="utf-8").replace("INE040A01034", "INE040A01035"),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError) as err:
        load_all(cfg)
    assert any("INE040A01035" in p for p in err.value.problems)


@pytest.mark.parametrize("tool", ["Bash", "WebFetch", "Read", "some_other_server__tool"])
def test_agents_can_never_be_given_non_parakh_tools(tool: str) -> None:
    """T-CFG-04 (AG-01)"""
    with pytest.raises(ValidationError):
        AgentConfig(
            description="x", first_phase=3, allowed_tools=["mcp__parakh__audit_get_run", tool]
        )


def test_an_enabled_agent_needs_a_pinned_prompt() -> None:
    """T-CFG-05 (P3)"""
    with pytest.raises(ValidationError):
        AgentConfig(description="x", first_phase=3, enabled=True, allowed_tools=[])
