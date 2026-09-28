"""CLI (exit gate: `run.py --help`, config validates, dummy run). T-CLI-01…"""

from __future__ import annotations

import subprocess
import sys

import pytest

from parakh.cli import main
from parakh.config import REPO_ROOT


def test_run_py_help_works() -> None:
    """T-CLI-01"""
    out = subprocess.run(
        [sys.executable, "run.py", "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    for command in ("doctor", "config", "run", "audit", "catalogue", "mcp"):
        assert command in out.stdout


def test_config_validate_and_dummy_run_and_verify(capsys: pytest.CaptureFixture[str]) -> None:
    """T-CLI-02"""
    assert main(["config", "validate"]) == 0
    assert "INE040A01034" in capsys.readouterr().out
    assert main(["run", "--mode", "dummy", "--asof", "2026-09-30"]) == 0
    assert "SUCCESS_AUDIT_PENDING" in capsys.readouterr().out
    assert main(["audit", "verify"]) == 0
    assert "chain OK" in capsys.readouterr().out


def test_later_modes_say_when_they_arrive(capsys: pytest.CaptureFixture[str]) -> None:
    """T-CLI-03"""
    assert main(["run", "--mode", "monthly"]) == 2
    assert "later phase" in capsys.readouterr().out
