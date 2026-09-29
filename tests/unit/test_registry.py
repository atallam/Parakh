"""Metric, signal, rule and lens registries (plan 04 §3.1). T-REG-01…"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from parakh.registry import (
    REGISTRY,
    RegistryError,
    register_lens,
    register_metric,
    register_rule,
    register_signal,
)
from tests.fakes.sample_lens import GOOD_DOC


@pytest.fixture
def clean_registry() -> Iterator[None]:
    before = {k: dict(v) for k, v in vars(REGISTRY).items()}
    yield
    for k, v in before.items():
        getattr(REGISTRY, k).clear()
        getattr(REGISTRY, k).update(v)


@pytest.mark.parametrize("bad", ["pe_vs_5y", "MET.value", "MET.Value.pe", "met.value.pe"])
def test_metric_ids_follow_the_pattern(bad: str) -> None:
    """T-REG-01"""
    with pytest.raises(RegistryError):
        register_metric(id=bad, unit="ratio", inputs=[], used_by=[])


def test_metric_docstring_needs_formula_meaning_pitfalls_source(clean_registry: None) -> None:
    """T-REG-02 (plan 04 §3.2)"""
    with pytest.raises(RegistryError, match="docstring"):

        @register_metric(id="MET.test.no_doc", unit="ratio", inputs=[], used_by=[])
        def no_doc() -> float:
            """Just a summary."""
            return 0.0


def test_duplicate_ids_are_refused(clean_registry: None) -> None:
    """T-REG-03"""

    def fn() -> float:
        return 1.0

    fn.__doc__ = GOOD_DOC
    register_metric(id="MET.test.dupe", unit="ratio", inputs=[], used_by=[])(fn)
    with pytest.raises(RegistryError, match="twice"):
        register_metric(id="MET.test.dupe", unit="ratio", inputs=[], used_by=[])(fn)


def test_signal_rule_and_lens_ids(clean_registry: None) -> None:
    """T-REG-04"""
    with pytest.raises(RegistryError):
        register_signal(id="M3", name="x", lens="momentum", severity="Low")
    with pytest.raises(RegistryError):
        register_rule(id="veto.pledge", kind="veto")
    with pytest.raises(RegistryError):
        register_lens("Value")
    with pytest.raises(RegistryError, match="subclass"):
        register_lens("not_a_lens")(object)  # type: ignore[arg-type]
