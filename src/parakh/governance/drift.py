# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportReturnType=false, reportArgumentType=false, reportOperatorIssue=false, reportAssignmentType=false
# why: the pandas stubs infer ndarray/Series unions for indexing and sorting that are Series at run time; tests cover these paths
"""Drift monitoring: has the monthly output shifted in a way no rule change explains? (plan 10 §5, §8)

    report = drift_report(rows, cfg.drift, period="2026-10")

`rows` is one line per stock-month (the shape of `history.csv`). The latest month is compared with the
`baseline_months` before it on three things: the score distribution (population stability index, PSI),
each verdict's share of the month, and the number of fired signals per stock. A check on fewer than
`min_stocks` names is reported as "not enough stocks" and never as stable, because a PSI on the 7-stock
pilot says nothing. Drift is a prompt to look, not an error: the response is a human reading the month.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from parakh.configs.calibration_models import DriftConfig

OK, WARN, ALERT, SKIPPED = "ok", "warn", "alert", "not enough stocks"
RANK = {OK: 0, SKIPPED: 0, WARN: 1, ALERT: 2}


@dataclass
class Check:
    name: str
    status: str
    value: float | None = None
    detail: str = ""


@dataclass
class DriftReport:
    period: str
    baseline: list[str]
    stocks: int
    checks: list[Check] = field(default_factory=list)

    @property
    def status(self) -> str:
        return max((c.status for c in self.checks), key=lambda s: RANK[s], default=OK)

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "status": self.status}


def psi(base: np.ndarray, now: np.ndarray, bins: int) -> float:
    """Population stability index of `now` against `base`, with bin edges from the baseline quantiles."""
    edges = np.unique(np.quantile(base, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return 0.0
    edges[0], edges[-1] = -np.inf, np.inf
    b = np.histogram(base, edges)[0] / len(base)
    n = np.histogram(now, edges)[0] / len(now)
    b, n = np.clip(b, 1e-4, None), np.clip(n, 1e-4, None)
    return float(np.sum((n - b) * np.log(n / b)))


def _grade(value: float, cfg: DriftConfig) -> str:
    return ALERT if value >= cfg.psi_alert else WARN if value >= cfg.psi_warn else OK


def _n_signals(s: Any) -> int:
    return len([c for c in str(s or "").split(",") if c])


def drift_report(rows: pd.DataFrame, cfg: DriftConfig, *, period: str | None = None) -> DriftReport:
    periods = sorted(rows["period"].unique()) if len(rows) else []
    now_p = period or (periods[-1] if periods else "")
    earlier = [p for p in periods if p < now_p][-cfg.baseline_months :]
    now = rows[rows["period"] == now_p]
    base = rows[rows["period"].isin(earlier)]
    rep = DriftReport(now_p, earlier, len(now))
    if not earlier or now.empty:
        rep.checks.append(Check("history", SKIPPED, None, "needs at least one earlier month"))
        return rep
    enough = len(now) >= cfg.min_stocks
    for col in ("value_score", "momentum_score"):
        a, b = base[col].dropna().to_numpy(float), now[col].dropna().to_numpy(float)
        name = f"PSI of {col}"
        if not enough or len(a) < cfg.min_stocks or len(b) < cfg.min_stocks:
            rep.checks.append(
                Check(name, SKIPPED, None, f"{len(b)} scored; {cfg.min_stocks} needed")
            )
            continue
        v = psi(a, b, cfg.bins)
        rep.checks.append(
            Check(name, _grade(v, cfg), round(v, 4), "0.10 shifting, 0.25 real shift")
        )
    mix_b = base["verdict"].value_counts(normalize=True) * 100
    mix_n = now["verdict"].value_counts(normalize=True) * 100
    shifts = (mix_n.reindex(mix_b.index.union(mix_n.index)).fillna(0)
              - mix_b.reindex(mix_b.index.union(mix_n.index)).fillna(0))  # fmt: skip
    if enough:
        worst = shifts.abs().idxmax()
        move = float(shifts[worst])
        rep.checks.append(
            Check(
                "verdict mix",
                WARN if abs(move) > cfg.verdict_mix_shift_pct else OK,
                round(move, 1),
                f"largest move: {worst} {move:+.1f} points",
            )  # fmt: skip
        )
    else:
        rep.checks.append(
            Check("verdict mix", SKIPPED, None, f"{len(now)} stocks; {cfg.min_stocks} needed")
        )
    rate_b = (
        base.groupby("period")["signals"]
        .apply(lambda s: sum(_n_signals(x) for x in s) / len(s))
        .mean()
    )
    rate_n = sum(_n_signals(x) for x in now["signals"]) / len(now)
    if not enough:
        rep.checks.append(
            Check("signal rate", SKIPPED, None, f"{len(now)} stocks; {cfg.min_stocks} needed")
        )
    elif rate_b == 0:
        rep.checks.append(Check("signal rate", OK, None, "no signals fired in the baseline"))
    else:
        ratio = float(rate_n / rate_b)
        bad = ratio < cfg.signal_rate_ratio_low or ratio > cfg.signal_rate_ratio_high
        rep.checks.append(
            Check("signal rate", WARN if bad else OK, round(ratio, 2), "this month ÷ baseline")
        )
    return rep
