"""Market regime per segment (plan 02 §5, F16). Pure functions over the segment benchmark.

    Risk-On   benchmark > 200 DMA, 50 DMA > 200 DMA, breadth > 55%
    Risk-Off  benchmark < 200 DMA and breadth < 40%
    Neutral   everything else

Breadth needs the constituents' prices, which pilot mode does not have; then the regime uses the
benchmark's own trend and records that breadth was unavailable (never a guess). A VIX spike
(above its 1-year 80th percentile and rising) downgrades the regime one level (AC-F16.3).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from parakh.analytics.indicators import sma
from parakh.configs.lens_models import RegimeConfig

ORDER = ["Risk-Off", "Neutral", "Risk-On"]


@dataclass
class RegimeResult:
    regime: str
    reasons: list[str] = field(default_factory=list)
    breadth: float | None = None
    benchmark_pct_vs_200: float | None = None
    flags: list[str] = field(default_factory=list)
    known: bool = True


def segment_regime(
    bench: pd.Series | None,
    cfg: RegimeConfig,
    breadth: float | None = None,
    vix: pd.Series | None = None,
    fii_net_20d_cr: float | None = None,
    dii_absorbing: bool = False,
) -> RegimeResult:
    if bench is None or len(bench) < cfg.ma_long:
        return RegimeResult(
            "Neutral",
            [f"benchmark history under {cfg.ma_long} sessions; regime unknown, treated as Neutral"],
            known=False,
        )
    x = bench.to_numpy(float)
    x = x[np.isfinite(x)]
    m_long, m_short = sma(x, cfg.ma_long), sma(x, cfg.ma_short)
    assert m_long is not None and m_short is not None
    above = x[-1] > m_long
    golden = m_short > m_long
    out = RegimeResult("Neutral", breadth=breadth, benchmark_pct_vs_200=float(x[-1] / m_long - 1))
    if breadth is None:
        out.flags.append("breadth unavailable (no constituent prices): benchmark trend only")
        on = above and golden
        off = (not above) and (not golden)
    else:
        on = above and golden and breadth > cfg.risk_on_breadth_min
        off = (not above) and breadth < cfg.risk_off_breadth_max
    if on:
        out.regime, out.reasons = "Risk-On", ["benchmark above a rising 200 DMA structure"]
    elif off:
        out.regime, out.reasons = "Risk-Off", ["benchmark below its 200 DMA and trend rolling over"]
    else:
        out.reasons.append("mixed trend signals")
    if vix is not None and len(vix) >= 252:
        v = vix.to_numpy(float)
        v = v[np.isfinite(v)]
        pct = float((v[-252:] <= v[-1]).mean())
        rising = v[-1] > v[-1 - cfg.vix_rising_sessions]
        if pct >= cfg.vix_percentile_high and rising:
            out.regime = ORDER[max(0, ORDER.index(out.regime) - 1)]
            out.reasons.append(
                "India VIX above its 1-year 80th percentile and rising: downgraded one level"
            )
    if fii_net_20d_cr is not None and fii_net_20d_cr <= -cfg.flow_headwind_cr and not dii_absorbing:
        out.flags.append("flow headwind: heavy FII selling not absorbed by DIIs")
    return out


def mos_uplift_pp(index_pe_percentile: float | None, cfg: RegimeConfig) -> float:
    """Extra margin of safety (in percentage points) when the market sits in its top valuation decile."""
    if index_pe_percentile is not None and index_pe_percentile >= cfg.market_valuation_top_decile:
        return cfg.mos_uplift_pp
    return 0.0
