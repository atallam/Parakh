"""T-REG-01…: the segment regime (AC-F16.1–3)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from parakh.analytics.regime import mos_uplift_pp, segment_regime
from parakh.configs import load_file
from parakh.configs.lens_models import RegimeConfig

CFG = load_file("regime.yaml", RegimeConfig)


def _idx(slope: float, n: int = 300) -> pd.Series:
    return pd.Series(1000 * np.exp(slope * np.arange(n)))


@pytest.mark.ac("AC-F16.1")
def test_regime_is_computed_per_segment_benchmark() -> None:
    """T-REG-01: a rising small-cap index and a falling mid-cap index get different regimes."""
    assert segment_regime(_idx(0.002), CFG).regime == "Risk-On"
    assert segment_regime(_idx(-0.002), CFG).regime == "Risk-Off"


def test_unknown_breadth_is_recorded_not_guessed() -> None:
    """T-REG-02"""
    r = segment_regime(_idx(0.002), CFG)
    assert any("breadth unavailable" in f for f in r.flags)
    low = segment_regime(_idx(0.002), CFG, breadth=0.3)
    assert (
        low.regime == "Neutral"
    )  # not Risk-On: breadth is weak, but the benchmark is above its 200 DMA


@pytest.mark.ac("AC-F16.3")
def test_a_vix_spike_downgrades_one_level() -> None:
    """T-REG-03"""
    vix = pd.Series(np.concatenate([np.full(300, 13.0), [13, 14, 15, 17, 19, 22]]))
    r = segment_regime(_idx(0.002), CFG, vix=vix)
    assert r.regime == "Neutral" and any("VIX" in x for x in r.reasons)


@pytest.mark.ac("AC-F16.2")
def test_top_decile_market_raises_required_mos_by_5_points() -> None:
    """T-REG-04"""
    assert mos_uplift_pp(0.95, CFG) == 5
    assert mos_uplift_pp(0.5, CFG) == 0
    assert mos_uplift_pp(None, CFG) == 0


def test_short_history_is_neutral_and_unknown() -> None:
    """T-REG-05"""
    r = segment_regime(_idx(0.002, 100), CFG)
    assert r.regime == "Neutral" and not r.known
