# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportReturnType=false, reportArgumentType=false, reportOperatorIssue=false, reportAssignmentType=false
# why: the pandas stubs infer ndarray/Series unions for indexing and sorting that are Series at run time; tests cover these paths
"""Signal-outcome tracker: what happened after each signal fired (F17; plan 04 §2).

    obs = observations_from_alerts(alerts_log_rows, directions) + observations_from_panel(panel)
    table = track(obs, book, bench, cfg.outcomes, baseline)

For every signal observation (a stock, a signal ID, a date) it looks up the stock's own forward 1-month
and 3-month return, and the same window for its benchmark, then summarises per signal: how many
have matured, the mean and median forward return, the share that moved the way the signal says it
should (up after an entry signal, down after an exit or warning), the excess over the benchmark, and
the lift over the average stock-month. A signal with fewer than `min_observations` matured outcomes is
shown but not concluded about: a hit rate on 8 observations is noise (UX-05, honest unknowns).

Horizons are in trading sessions of the stock's own series. A series that ends before the horizon
without the data having ended (a delisting) is valued at its last close and counted as delisted, so a
stock that collapsed after a signal cannot disappear from the statistics.
"""

from __future__ import annotations

import bisect
import datetime as dt
import statistics
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd

from parakh.calibration.backtest import PriceBook, series_from
from parakh.configs.calibration_models import OutcomesConfig

SIGNAL_KINDS = {"signal"}
DECISIONS_THAT_OCCURRED = {
    "sent",
    "shadow",
    "suppressed",
    "digest",
    "digest_sent",
    "failed",
    "digest_failed",
}
EXPECTED_UP = {"entry"}
EXPECTED_DOWN = {"exit", "warning"}


@dataclass(frozen=True)
class Observation:
    isin: str
    symbol: str
    code: str
    date: dt.date
    direction: str  # entry | exit | warning | info
    source: str  # live (alerts_log) | backtest (monthly panel)
    segment: str | None = None


@dataclass
class Forward:
    ret: float | None  # the stock's return over the horizon; None while it is still pending
    bench: float | None
    status: str  # matured | pending | delisted | no_data


def observations_from_alerts(
    rows: list[dict[str, Any]], directions: Mapping[str, str]
) -> list[Observation]:
    """One observation per (stock, signal, day); a cool-down or a failed delivery does not erase it."""
    seen: set[tuple[str, str, str]] = set()
    out: list[Observation] = []
    for r in rows:
        code = str(r.get("code") or "")
        if r.get("kind") not in SIGNAL_KINDS or code not in directions or not r.get("isin"):
            continue
        if r.get("decision") not in DECISIONS_THAT_OCCURRED:
            continue
        key = (r["isin"], code, str(r["asof"]))
        if key in seen:
            continue
        seen.add(key)
        out.append(
            Observation(
                r["isin"], str(r.get("symbol") or r["isin"]), code, _day(r["asof"]),
                directions[code], "live",
            )
        )  # fmt: skip
    return out


def observations_from_panel(
    panel: pd.DataFrame, directions: Mapping[str, str]
) -> list[Observation]:
    """Signals that newly appeared in a month's panel row, i.e. the same transition rule as the watcher.

    Month-end sampling sees only what is active on the last day, so this undercounts the daily
    watcher; it is a history to start from, labelled `backtest`, not a replacement for live alerts.
    """
    out: list[Observation] = []
    if panel.empty:
        return out
    prev: dict[str, set[str]] = {}
    for asof, day in panel.sort_values("asof").groupby("asof"):
        now: dict[str, set[str]] = {}
        for r in day.itertuples():
            codes = {c for c in str(r.signals or "").split(",") if c}
            now[r.isin] = codes
            for code in sorted(codes - prev.get(r.isin, set())):
                if code in directions:
                    out.append(
                        Observation(
                            r.isin,
                            r.symbol,
                            code,
                            _day(asof),
                            directions[code],
                            "backtest",
                            r.segment,
                        )  # fmt: skip
                    )
        prev = now
    return out


def _day(x: Any) -> dt.date:
    return (
        x
        if isinstance(x, dt.date) and not isinstance(x, dt.datetime)
        else dt.date.fromisoformat(str(x)[:10])
    )


def forward(
    book: PriceBook,
    isin: str,
    day: dt.date,
    sessions: int,
    bench: tuple[list[dt.date], list[float]] | None,
    gap_days: int,
) -> Forward:
    s = book.series.get(isin)
    if s is None:
        return Forward(None, None, "no_data")
    dates, vals = s
    i = bisect.bisect_right(dates, day) - 1
    if i < 0 or vals[i] <= 0:
        return Forward(None, None, "no_data")
    data_end = book.days[-1]
    j = i + sessions
    if j < len(dates):
        end_day, end_px, status = dates[j], vals[j], "matured"
    else:
        last = dates[-1]
        if (data_end - last).days > gap_days:  # the series stopped while the data kept going
            end_day, end_px, status = last, vals[-1], "delisted"
        else:
            return Forward(None, None, "pending")
    b = None
    if bench is not None:
        bd, bv = bench
        k0, k1 = bisect.bisect_right(bd, day) - 1, bisect.bisect_right(bd, end_day) - 1
        if k0 >= 0 and k1 >= 0 and bv[k0] > 0:
            b = bv[k1] / bv[k0] - 1
    return Forward(end_px / vals[i] - 1, b, status)


@dataclass
class HorizonStats:
    horizon: str
    matured: int = 0
    pending: int = 0
    delisted: int = 0
    mean_pct: float | None = None
    median_pct: float | None = None
    hit_rate_pct: float | None = None  # moved the way the signal says
    mean_excess_pct: float | None = None
    lift_pct: float | None = None  # mean forward return minus the average stock-month
    evidence: str = "not enough yet"


@dataclass
class SignalOutcome:
    code: str
    direction: str
    source: str
    observations: int
    horizons: dict[str, HorizonStats] = field(default_factory=dict)


def _summarise(
    label: str, fwds: list[Forward], direction: str, cfg: OutcomesConfig, baseline: float | None
) -> HorizonStats:
    st = HorizonStats(label)
    st.pending = sum(1 for f in fwds if f.status == "pending")
    done = [f for f in fwds if f.ret is not None]
    st.matured = len(done)
    st.delisted = sum(1 for f in done if f.status == "delisted")
    if not done:
        return st
    rets = [f.ret * 100 for f in done]  # type: ignore[operator]
    st.mean_pct = statistics.fmean(rets)
    st.median_pct = statistics.median(rets)
    if direction in EXPECTED_UP:
        st.hit_rate_pct = 100 * sum(1 for r in rets if r > 0) / len(rets)
    elif direction in EXPECTED_DOWN:
        st.hit_rate_pct = 100 * sum(1 for r in rets if r < 0) / len(rets)
    ex = [(f.ret - f.bench) * 100 for f in done if f.bench is not None]  # type: ignore[operator]
    st.mean_excess_pct = statistics.fmean(ex) if ex else None
    if baseline is not None:
        st.lift_pct = st.mean_pct - baseline * 100
    st.evidence = (
        "enough to read"
        if st.matured >= cfg.min_observations
        else f"not enough yet ({st.matured} of {cfg.min_observations})"
    )
    return st


def track(
    observations: list[Observation],
    book: PriceBook,
    bench_by_segment: Mapping[str, pd.Series | None],
    default_segment: Mapping[str, str],
    cfg: OutcomesConfig,
    baseline: Mapping[str, float | None] | None = None,
) -> list[SignalOutcome]:
    """Outcome table per (signal, source). `default_segment` maps an ISIN to its current cap bucket."""
    bench = {k: series_from(v) for k, v in bench_by_segment.items()}
    groups: dict[tuple[str, str], list[Observation]] = {}
    for o in observations:
        groups.setdefault((o.code, o.source), []).append(o)
    out: list[SignalOutcome] = []
    for (code, source), obs in sorted(groups.items()):
        row = SignalOutcome(code, obs[0].direction, source, len(obs))
        for label, sessions in cfg.horizons_trading_days.items():
            fwds = [
                forward(
                    book, o.isin, o.date, sessions,
                    bench.get(o.segment or default_segment.get(o.isin, "")), cfg.delisted_gap_days,
                )
                for o in obs
            ]  # fmt: skip
            row.horizons[label] = _summarise(
                label, fwds, obs[0].direction, cfg, (baseline or {}).get(label)
            )
        out.append(row)
    return out


def unconditional(
    panel: pd.DataFrame, book: PriceBook, cfg: OutcomesConfig
) -> dict[str, float | None]:
    """Mean forward return of every scored stock-month: what "no signal at all" earns."""
    out: dict[str, float | None] = {}
    if panel.empty:
        return {k: None for k in cfg.horizons_trading_days}
    for label, sessions in cfg.horizons_trading_days.items():
        vals = []
        for r in panel.itertuples():
            f = forward(book, r.isin, _day(r.asof), sessions, None, cfg.delisted_gap_days)
            if f.ret is not None:
                vals.append(f.ret)
        out[label] = statistics.fmean(vals) if vals else None
    return out


def to_dict(outcomes: list[SignalOutcome]) -> list[dict[str, Any]]:
    return [asdict(o) for o in outcomes]
