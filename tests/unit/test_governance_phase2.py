"""Explain tree, model docs, override CLI, run manifest (F21; AC-F21.7, AC-F21.12)."""

from __future__ import annotations

import datetime as dt
import shutil

import pytest

from parakh import config
from parakh.cli_analysis import override_add
from parakh.configs import load_all
from parakh.governance.models import write_model_docs
from parakh.orchestration.analysis import run_monthly
from parakh.services.explain import explain_verdict, render_tree
from tests.helpers.pilot import END, pilot_data
from tests.unit.test_reports import HOLD


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    bundle = load_all()
    res = run_monthly(bundle, pilot_data(bundle), END, out_root=tmp_path_factory.mktemp("gov"))
    return res


@pytest.mark.ac("AC-F21.7")
def test_explain_tree_walks_from_verdict_to_inputs(run) -> None:
    for s in run.snapshots:
        snap = s.model_dump(mode="json")
        tree = explain_verdict(snap, None)
        text = render_tree(tree)
        assert snap["symbol"] in text and tree["policy"]["rule_id"] in text
        assert tree["policy"]["version"] and snap["run_id"] in text
        assert "value" in text.lower() and "momentum" in text.lower()


def test_manifest_names_lens_and_policy_versions(run) -> None:
    assert run.ctx.lens_versions and run.ctx.policy_version


@pytest.mark.ac("AC-F21.12")
def test_override_add_validates_and_rolls_back(tmp_path, monkeypatch) -> None:
    cfg = tmp_path / "config"
    shutil.copytree(config.REPO_ROOT / "config", cfg)
    monkeypatch.setenv("PARAKH_CONFIG_DIR", str(cfg))
    config.get_settings.cache_clear()
    try:
        before = (cfg / "overrides.yaml").read_text(encoding="utf-8")
        assert (
            override_add(HOLD, "thesis_status", "WATCH", "short", 30) == 2
        )  # reason under 10 characters
        assert (
            override_add(HOLD, "verdict", "HOLD", "Merger integration year", 400) == 2
        )  # life over 366 days
        assert (cfg / "overrides.yaml").read_text(encoding="utf-8") == before
        assert override_add(HOLD, "verdict", "HOLD", "Merger integration year", 90) == 0
        ov = load_all().overrides.overrides
        assert len(ov) == 1 and ov[0].expires_on == dt.date.today() + dt.timedelta(days=90)
    finally:
        config.get_settings.cache_clear()


def test_generated_model_docs_are_current() -> None:
    assert write_model_docs(check=True) == [], (
        "run `parakh catalogue` to regenerate docs/MODELS.md and docs/lenses/"
    )
