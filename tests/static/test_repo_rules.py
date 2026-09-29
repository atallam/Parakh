"""L0 static gates run inside pytest too (plan 14 §2). T-L0-01…"""

from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path

import pytest

from parakh.config import REPO_ROOT
from parakh.registry.catalogue import generate
from tools import doclint, lint_rules, traceability


@pytest.mark.ac("AC-F22.1")
def test_no_hex_colour_outside_ui_tokens() -> None:
    """T-L0-01"""
    assert lint_rules.token_lint() == []


@pytest.mark.ac("AC-F22.1")
def test_token_lint_catches_a_stray_hex(tmp_path: Path) -> None:
    """T-L0-02"""
    stray = "#" + "16A34A"  # built at runtime so this file passes the lint itself
    (tmp_path / "page.py").write_text(f'COLOR = "{stray}"\n', encoding="utf-8")
    assert lint_rules.token_lint(tmp_path)


def test_mcp_and_app_never_import_analytics_lenses_or_adapters() -> None:
    """T-L0-03 (plan 15 §4.1: no business logic in src/parakh/mcp/)"""
    assert lint_rules.layering_lint() == []


@pytest.mark.ac("AC-F18.4", "AC-F24.1")
def test_generated_catalogues_are_fresh() -> None:
    """T-L0-04: docs/METRICS, SIGNALS, RULES, TOOLS, AUDIT_EVENTS match the registries."""
    assert generate(check=True) == []


@pytest.mark.ac("AC-F21.14")
def test_plan_docs_pass_the_doc_lint() -> None:
    """T-L0-05"""
    assert doclint.check() == []


@pytest.mark.ac("AC-F21.14")
def test_doc_lint_catches_a_stale_milestone_date(tmp_path: Path) -> None:
    """T-L0-06"""
    plan = tmp_path / "plan"
    shutil.copytree(REPO_ROOT / "docs" / "plan", plan)
    readme = plan / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + "\n| **15 Nov 2026** · M1 | late |\n", encoding="utf-8"
    )
    problems = doclint.check(plan)
    assert any("M1" in p and str(dt.date(2026, 11, 15)) in p for p in problems)


@pytest.mark.ac("AC-F21.15")
def test_every_due_acceptance_criterion_has_a_test() -> None:
    """T-L0-07"""
    _, problems = traceability.build()
    assert problems == []


def test_supabase_seed_matches_the_universe() -> None:
    """T-L0-08: supabase/seed.sql is generated from config/universe.yaml."""
    from tools import make_seed

    assert (REPO_ROOT / "supabase" / "seed.sql").read_text(encoding="utf-8") == make_seed.render()
