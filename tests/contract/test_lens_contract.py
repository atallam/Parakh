"""Lens contract tests: run automatically for every registered lens (AC-F18.2; plan 04 §1.5).

Until the value and momentum lenses land (Phase 2), the harness runs on a sample lens so the
contract itself is tested. A new lens needs no new test to be held to these rules.
"""

from __future__ import annotations

import datetime as dt
import time
from collections.abc import Iterator

import pytest

from parakh.lenses.base import Lens, LensConfig, StockContext
from parakh.registry import REGISTRY, discover, register_lens, register_metric
from tests.fakes.sample_lens import GOOD_DOC, SAMPLE_METRIC, SampleLens

MAX_EVALUATE_MS = 50  # why: 500 stocks × lenses must fit the NFR-07 run-time target


@pytest.fixture(scope="module")
def lenses() -> Iterator[dict[str, type[Lens]]]:
    discover()
    added = []
    if "sample" not in REGISTRY.lenses:
        register_lens("sample")(SampleLens)
        added.append("sample")

    def metric() -> float:
        return 0.0

    metric.__doc__ = GOOD_DOC
    if SAMPLE_METRIC not in REGISTRY.metrics:
        register_metric(
            id=SAMPLE_METRIC, unit="ratio", inputs=["fundamentals.eps_ttm"], used_by=["LENS.sample"]
        )(metric)
    yield dict(REGISTRY.lenses)
    for name in added:
        REGISTRY.lenses.pop(name, None)
    REGISTRY.metrics.pop(SAMPLE_METRIC, None)


def _ctx(metrics: dict[str, float | None]) -> StockContext:
    return StockContext(
        isin="INE040A01034",
        symbol="HDFCBANK",
        asof=dt.date(2026, 10, 30),
        profile="bank",
        metrics=metrics,
    )


def _cases(lens: type[Lens]) -> list[dict[str, float | None]]:
    full = dict.fromkeys(lens.required_metrics, 0.05)
    return [full, dict.fromkeys(lens.required_metrics), {}]


@pytest.mark.ac("AC-F18.2")
def test_every_lens_honours_the_contract(lenses: dict[str, type[Lens]]) -> None:
    """T-LNS-01: score 0–100 or None, subscores 0–1, known metric IDs, survives missing data, fast."""
    assert lenses, "no lens registered"
    cfg = LensConfig(lens_version="0.0.1")
    for lens_id, cls in lenses.items():
        lens = cls()
        unknown = [m for m in cls.required_metrics if m not in REGISTRY.metrics]
        assert not unknown, f"LENS.{lens_id} requires unregistered metrics {unknown}"
        for metrics in _cases(cls):
            lens.evaluate(_ctx(metrics), cfg)  # warm-up: first call loads lazily-read config
            times = []
            for _ in range(
                3
            ):  # best of three: a slow disk or a busy machine must not fail the contract
                start = time.perf_counter()
                result = lens.evaluate(_ctx(metrics), cfg)
                times.append((time.perf_counter() - start) * 1000)
            elapsed_ms = min(times)
            assert result.lens_id == lens_id
            assert result.score is None or 0 <= result.score <= 100
            assert all(0 <= v <= 1 for v in result.subscores.values())
            assert set(result.metrics_used) <= set(REGISTRY.metrics)
            assert elapsed_ms < MAX_EVALUATE_MS, f"LENS.{lens_id} took {elapsed_ms:.1f} ms"
            if not any(v is not None for v in metrics.values()):
                assert result.confidence == "Low" or result.score is None, (
                    "missing data must not look confident"
                )
