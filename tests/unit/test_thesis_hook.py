"""THESIS.md template and the immutable-original hook (F23)."""

from __future__ import annotations

from pathlib import Path

import pytest

from parakh.registry import REGISTRY, discover
from parakh.thesis.model import parse_text
from parakh.thesis.status import validate_rules, variable_names
from tools import check_thesis_original as hook

TEMPLATE = Path(__file__).resolve().parents[2] / "docs" / "templates" / "THESIS.template.md"


def test_the_template_is_a_valid_thesis() -> None:
    parsed = parse_text(TEMPLATE.read_text(encoding="utf-8"))
    assert parsed.errors == [] and parsed.front is not None
    discover()
    assert validate_rules(parsed, variable_names(REGISTRY.metrics.keys())) == []


def test_hook_blocks_edits_to_the_original_but_not_to_the_rest(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    f = tmp_path / "THESIS.md"
    original = parse_text(text).raw_original
    monkeypatch.setattr(hook, "committed_original", lambda p: original)
    f.write_text(text.replace("thesis_version: 1", "thesis_version: 2"), encoding="utf-8")
    assert hook.problems([f]) == []
    f.write_text(text.replace("This block never changes.", "Edited later."), encoding="utf-8")
    assert len(hook.problems([f])) == 1
    monkeypatch.setattr(hook, "committed_original", lambda p: None)  # a brand-new file
    assert hook.problems([f]) == []
