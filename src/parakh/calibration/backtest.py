# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportReturnType=false, reportArgumentType=false, reportOperatorIssue=false, reportAssignmentType=false
# why: the pandas stubs infer ndarray/Series unions for indexing and sorting that are Series at run time; tests cover these paths
"""Price-only momentum backtest with costs, tax and a walk-forward (F17; AC-F17.1, AC-F17.2).

    book = PriceBook.from_frames(prices)
    sim = simulate(panel, book, cfg, schedule, costs=True, tax=True)
    result = run_backtest(panel, book, bench, cfg, tax_rates)

The strategy is the one the momentum lens describes: each month-end, rank the stocks that are index
members that day by momentum score, hold the top `top_pct` with a score of at least `min_score`, keep a
holder while it stays inside the rank buffer, trade at the next session's close. Three runs of the same
path give the three figures AC-F17.2 asks for: gross (no costs, no tax), after costs, and after costs
and tax (realised gains taxed at the Indian short- and long-term rates, losses set off by the usual
rules, tax paid from the book when the financial year closes).

Honesty rules the code enforces:
- eligibility comes from the panel, which only contains stocks that were members on that date
  (AC-F17.1); a stock whose price series ends while held is sold at its last price and counted;
- walk-forward: each test year uses the parameters that scored best on the five years before it, never
  on the year itself, and the stitched out-of-sample path is run as one continuous book;
- the headline is refused (status `refused`) when membership history does not cover the window, unless
  the caller passes `allow_proxy`, in which case every figure is labelled as survivorship-biased.
"""

from __future__ import annotations

import bisect
import datetime as dt
import itertools
import math
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from parakh.configs.calibration_models import BacktestConfig, CalibrationConfig, PortfolioRules
from parakh.configs.lens_models import TaxRates


@dataclass(frozen=True)
class Params:
    top_pct: float
    min_score: float
    buffer_pct: float
    min_names: int
    band_pct: float

    @classmethod
    def from_rules(cls, r: PortfolioRules, **over: float) -> Params:
        base = {
            "top_pct": r.top_pct,
            "min_score": r.min_score,
            "buffer_pct": r.buffer_pct,
            "min_names": r.min_names,
            "band_pct": r.rebalance_band_pct,
        }
        base.update(over)
        top = float(base["top_pct"])
        return cls(
            top, float(base["min_score"]), max(float(base["buffer_pct"]), top),
            int(base["min_names"]), float(base["band_pct"]),
        )  # fmt: skip


# -- prices ---------------------------------------------------------------------------------------
class PriceBook:
    """Adjusted closes by ISIN with fast "price on or before a date" lookups."""

    def __init__(self, series: dict[str, tuple[list[dt.date], list[float]]]) -> None:
        self.series = series
        days: set[dt.date] = set()
        for ds, _ in series.values():
            days.update(ds)
        self.days = sorted(days)

    @classmethod
    def from_frames(cls, frames: dict[str, pd.DataFrame]) -> PriceBook:
        out: dict[str, tuple[list[dt.date], list[float]]] = {}
        for isin, f in frames.items():
            if f is None or f.empty:
                continue
            g = f.copy()
            g["trade_date"] = pd.to_datetime(g["trade_date"]).dt.date
            col = g["adj_close"].where(g["adj_close"].notna(), g["close"])
            g = g.assign(px=col.astype(float)).dropna(subset=["px"])
            g = g[g["px"] > 0].sort_values("trade_date").drop_duplicates("trade_date", keep="last")
            if len(g):
                out[isin] = (list(g["trade_date"]), [float(x) for x in g["px"]])
        return cls(out)

    def price(self, isin: str, day: dt.date) -> float | None:
        s = self.series.get(isin)
        if s is None:
            return None
        i = bisect.bisect_right(s[0], day) - 1
        return s[1][i] if i >= 0 else None

    def last_date(self, isin: str) -> dt.date | None:
        s = self.series.get(isin)
        return s[0][-1] if s else None

    def first_date(self, isin: str) -> dt.date | None:
        s = self.series.get(isin)
        return s[0][0] if s else None

    def trade_day(self, asof: dt.date, lag: int) -> dt.date | None:
        """The session `lag` sessions after `asof`, or None when the data ends first."""
        i = bisect.bisect_left(self.days, asof)
        j = i + lag
        return self.days[j] if j < len(self.days) else None


def series_from(s: pd.Series | None) -> tuple[list[dt.date], list[float]] | None:
    if s is None or len(s) == 0:
        return None
    t = s.dropna().sort_index()
    return [pd.Timestamp(i).date() for i in t.index], [float(x) for x in t.to_numpy()]


# -- tax ------------------------------------------------------------------------------------------
def fy_of(day: dt.date) -> int:
    """Indian financial year as its starting year: April 2026 to March 2027 is 2026."""
    return day.year if day.month >= 4 else day.year - 1


def tax_due(stcg: float, ltcg: float, rates: TaxRates) -> float:
    """Tax on one year's realised gains.

    Short-term losses set off short- then long-term gains; long-term losses set off only long-term
    gains; nothing carries forward (conservative: a carry-forward would only lower the tax). The
    long-term exemption applies once a year; cess is added on the tax.
    """
    s, lg = stcg, ltcg
    if s < 0:
        lg += s
        s = 0.0
    lg = max(lg, 0.0)
    taxable_l = max(0.0, lg - rates.ltcg_exempt_inr)
    base = s * rates.stcg_pct / 100 + taxable_l * rates.ltcg_pct / 100
    return base * (1 + rates.cess_pct / 100)


# -- the simulation ------------------------------------------------------------------------------
@dataclass
class Lot:
    qty: float
    date: dt.date
    price: float


@dataclass
class Position:
    lots: list[Lot]
    segment: str

    @property
    def qty(self) -> float:
        return sum(lot.qty for lot in self.lots)


@dataclass
class SimResult:
    dates: list[dt.date] = field(default_factory=list)
    equity: list[float] = field(default_factory=list)  # after trading on each date
    names: list[int] = field(default_factory=list)
    turnover: list[float] = field(default_factory=list)  # one-way traded value ÷ equity
    cost_inr: float = 0.0
    tax_inr: float = 0.0
    tax_by_fy: dict[int, float] = field(default_factory=dict)
    realised: dict[int, tuple[float, float]] = field(default_factory=dict)
    delisted: list[tuple[str, dt.date]] = field(default_factory=list)
    cash_months: int = 0
    liquidation_tax_inr: float = 0.0
    liquidation_cost_inr: float = 0.0
    start_inr: float = 0.0


Schedule = Callable[[dt.date], Params]


def _rank(panel_day: pd.DataFrame, min_history: int) -> list[tuple[str, float, str]]:
    f = panel_day[
        panel_day["score"].notna()
        & (~panel_day["informational"].astype(bool))
        & (panel_day["sessions"] >= min_history)
    ]
    f = f.sort_values(["score", "isin"], ascending=[False, True])
    return [(r.isin, float(r.score), str(r.segment)) for r in f.itertuples()]


def select_targets(
    ranked: list[tuple[str, float, str]], held: set[str], p: Params
) -> list[tuple[str, str]]:
    """The names to hold after this rebalance, as (isin, segment). Pure: no prices, no state."""
    n = len(ranked)
    if n == 0:
        return []
    want = max(1, round(n * p.top_pct / 100))
    buffer_n = max(want, math.ceil(n * p.buffer_pct / 100))
    chosen: list[tuple[str, str]] = [
        (isin, seg)
        for rank, (isin, score, seg) in enumerate(ranked, start=1)
        if isin in held and rank <= buffer_n and score >= p.min_score
    ][:want]  # holders inside the rank buffer stay, best-ranked first
    seen = {i for i, _ in chosen}
    for isin, score, seg in ranked:  # then the best of the rest, down to the target count
        if len(chosen) >= want:
            break
        if isin not in seen and score >= p.min_score:
            chosen.append((isin, seg))
            seen.add(isin)
    return chosen if len(chosen) >= p.min_names else []


def simulate(
    panel: pd.DataFrame,
    book: PriceBook,
    cfg: BacktestConfig,
    schedule: Schedule,
    rates: TaxRates,
    *,
    costs: bool,
    tax: bool,
    start: dt.date | None = None,
    end: dt.date | None = None,
    delisted_gap_days: int = 15,
) -> SimResult:
    rules = cfg.portfolio
    rebalances = sorted({d for d in panel["asof"]})
    by_day = {d: g for d, g in panel.groupby("asof")}
    cash = rules.initial_capital_inr
    positions: dict[str, Position] = {}
    out = SimResult(start_inr=cash)
    realised: dict[int, list[float]] = {}  # fy → [stcg, ltcg]

    def value(day: dt.date) -> float:
        total = cash
        for isin, pos in positions.items():
            px = book.price(isin, day)
            total += pos.qty * (px or 0.0)
        return total

    def bps(side: str, seg: str) -> float:
        if not costs:
            return 0.0
        c = cfg.costs
        stat = c.statutory_buy_bps if side == "buy" else c.statutory_sell_bps
        return (stat + c.impact_bps.get(seg, 0.0)) / 1e4  # type: ignore[call-overload]

    def sell(isin: str, qty: float, day: dt.date, px: float) -> float:
        """Sell `qty` FIFO at `px`; returns cash received after costs and records the gain."""
        nonlocal cash
        pos = positions[isin]
        left, gain_s, gain_l = qty, 0.0, 0.0
        while left > 1e-12 and pos.lots:
            lot = pos.lots[0]
            take = min(lot.qty, left)
            gain = take * (px - lot.price)
            if (day - lot.date).days > rates.long_term_days:
                gain_l += gain
            else:
                gain_s += gain
            lot.qty -= take
            left -= take
            if lot.qty <= 1e-12:
                pos.lots.pop(0)
        gross = qty * px
        fee = gross * bps("sell", pos.segment)
        out.cost_inr += fee
        r = realised.setdefault(fy_of(day), [0.0, 0.0])
        r[0] += gain_s
        r[1] += gain_l
        cash += gross - fee
        if not pos.lots:
            del positions[isin]
        return gross

    def assess(day: dt.date) -> None:
        """Pay the tax for every financial year that ended before `day`, from the book."""
        nonlocal cash
        if not tax:
            return
        for f in sorted(f for f in realised if f < fy_of(day) and f not in out.tax_by_fy):
            t = tax_due(realised[f][0], realised[f][1], rates)
            out.tax_by_fy[f] = t
            out.tax_inr += t
            if t <= 0:
                continue
            if cash >= t:
                cash -= t
            else:  # raise the rest by trimming every holding pro rata (not itself taxed: an approximation)
                short = t - cash
                cash = 0.0
                total = value(day)
                if total > 0:
                    keep = max(0.0, 1 - short / total)
                    for pos in positions.values():
                        for lot in pos.lots:
                            lot.qty *= keep

    started = False
    for asof in rebalances:
        day = book.trade_day(asof, rules.execution_lag_sessions)
        if day is None or (start and day < start) or (end and day > end):
            continue
        pre = value(day)
        traded = 0.0
        if not started:  # the series starts at the capital before the first purchase
            out.dates.append(day)
            out.equity.append(pre)
        assess(day)
        # a holding whose series ended long ago is gone: take it out at its last price
        for isin in list(positions):
            last = book.last_date(isin)
            if last is not None and (day - last).days > delisted_gap_days:
                px = book.price(isin, last) or 0.0
                traded += sell(isin, positions[isin].qty, last, px)
                out.delisted.append((isin, last))
        p = schedule(asof)
        ranked = _rank(by_day[asof], cfg.min_history_sessions)
        targets = select_targets(ranked, set(positions), p)
        if not targets:
            out.cash_months += 1
        target_ids = {i for i, _ in targets}
        seg_of = dict(targets)
        for isin in list(positions):  # sell what is not wanted
            if isin not in target_ids:
                px = book.price(isin, day)
                if px is None:
                    continue
                traded += sell(isin, positions[isin].qty, day, px)
        equity = value(day)
        if targets and equity > 0:
            want_value = equity / len(targets)
            for isin in target_ids & set(positions):  # trim or top up drifted holders
                px = book.price(isin, day)
                if px is None:
                    continue
                have = positions[isin].qty * px
                if have > want_value and (have - want_value) / want_value > p.band_pct / 100:
                    traded += sell(isin, (have - want_value) / px, day, px)
            buys = []
            for isin in target_ids:
                px = book.price(isin, day)
                if px is None:
                    continue
                have = positions[isin].qty * px if isin in positions else 0.0
                gap = want_value - have
                if gap > 0 and (isin not in positions or gap / want_value > p.band_pct / 100):
                    buys.append((isin, px, gap))
            need = sum(g for _, _, g in buys)
            scale = min(1.0, cash / need) if need > 0 else 1.0
            for isin, px, gap in buys:
                spend = gap * scale
                if spend <= 0:
                    continue
                seg = positions[isin].segment if isin in positions else seg_of[isin]
                fee_rate = bps("buy", seg)
                qty = spend / (px * (1 + fee_rate))
                out.cost_inr += qty * px * fee_rate
                cash -= spend
                traded += qty * px
                pos = positions.setdefault(isin, Position([], seg))
                pos.lots.append(Lot(qty, day, px))
        post = value(day)
        out.names.append(len(positions))
        if started:
            out.dates.append(day)
            out.equity.append(post)
            out.turnover.append(traded / pre if pre > 0 else 0.0)  # the first build is not turnover
        started = True

    # mark the book on the last data day so the final holding period counts
    if out.dates:
        last_day = min(book.days[-1], end) if end else book.days[-1]
        if last_day > out.dates[-1]:
            out.dates.append(last_day)
            out.equity.append(value(last_day))
        # what liquidation on that day would cost: sell fees and the tax on the open year
        if tax or costs:
            lo_s, lo_l = 0.0, 0.0
            fee = 0.0
            for isin, pos in positions.items():
                px = book.price(isin, last_day) or 0.0
                fee += pos.qty * px * bps("sell", pos.segment)
                for lot in pos.lots:
                    g = lot.qty * (px - lot.price)
                    if (last_day - lot.date).days > rates.long_term_days:
                        lo_l += g
                    else:
                        lo_s += g
            out.liquidation_cost_inr = fee
            if tax:
                cur = realised.get(fy_of(last_day), [0.0, 0.0])
                unpaid = sum(
                    tax_due(v[0], v[1], rates)
                    for f, v in realised.items()
                    if f not in out.tax_by_fy and f != fy_of(last_day)
                )
                out.liquidation_tax_inr = unpaid + tax_due(cur[0] + lo_s, cur[1] + lo_l, rates)
    out.realised = {f: (v[0], v[1]) for f, v in realised.items()}
    return out


# -- performance ---------------------------------------------------------------------------------
@dataclass
class Perf:
    start: str | None = None
    end: str | None = None
    months: int = 0
    start_inr: float = 0.0
    end_inr: float = 0.0
    cagr_pct: float | None = None
    vol_pct: float | None = None
    sharpe: float | None = None
    max_drawdown_pct: float | None = None
    avg_names: float | None = None
    turnover_pct_per_month: float | None = None
    cost_inr: float = 0.0
    tax_inr: float = 0.0
    cash_months: int = 0
    delisted: int = 0
    beta: float | None = None
    alpha_pct: float | None = None
    excess_cagr_pct: float | None = None
    hit_rate_pct: float | None = None  # months the book beat the benchmark


def monthly_returns(equity: list[float]) -> np.ndarray:
    e = np.asarray(equity, dtype=float)
    if len(e) < 2:
        return np.array([])
    return e[1:] / e[:-1] - 1


def perf_of(
    dates: list[dt.date],
    equity: list[float],
    risk_free_pct: float,
    bench_equity: list[float] | None = None,
    sim: SimResult | None = None,
    end_override: float | None = None,
) -> Perf:
    p = Perf()
    if len(dates) < 2 or len(equity) != len(dates):
        return p
    eq = list(equity)
    if end_override is not None:
        eq[-1] = end_override
    p.start, p.end = dates[0].isoformat(), dates[-1].isoformat()
    p.start_inr, p.end_inr = eq[0], eq[-1]
    p.months = len(eq) - 1
    years = (dates[-1] - dates[0]).days / 365.25
    if years > 0 and eq[0] > 0 and eq[-1] > 0:
        p.cagr_pct = ((eq[-1] / eq[0]) ** (1 / years) - 1) * 100
    r = monthly_returns(eq)
    if len(r) >= 2:
        sd = float(r.std(ddof=1))
        p.vol_pct = sd * math.sqrt(12) * 100
        if sd > 0:
            p.sharpe = (float(r.mean()) - risk_free_pct / 100 / 12) / sd * math.sqrt(12)
    peak, worst = eq[0], 0.0
    for v in eq:
        peak = max(peak, v)
        worst = min(worst, v / peak - 1)
    p.max_drawdown_pct = worst * 100
    if sim is not None:
        p.avg_names = float(np.mean(sim.names)) if sim.names else None
        p.turnover_pct_per_month = float(np.mean(sim.turnover)) * 100 if sim.turnover else None
        p.cost_inr, p.tax_inr = sim.cost_inr, sim.tax_inr
        p.cash_months, p.delisted = sim.cash_months, len(sim.delisted)
    if bench_equity is not None and len(bench_equity) == len(eq):
        b = monthly_returns(bench_equity)
        if len(b) == len(r) and len(r) >= 6:
            var = float(np.var(b, ddof=1))
            if var > 0:
                p.beta = float(np.cov(r, b, ddof=1)[0, 1] / var)
                p.alpha_pct = (float(r.mean()) - p.beta * float(b.mean())) * 12 * 100
            p.hit_rate_pct = float(np.mean(r > b)) * 100
        if bench_equity[0] > 0 and years > 0 and p.cagr_pct is not None:
            bc = ((bench_equity[-1] / bench_equity[0]) ** (1 / years) - 1) * 100
            p.excess_cagr_pct = p.cagr_pct - bc
    return p


def bench_at(
    bench: tuple[list[dt.date], list[float]] | None, dates: list[dt.date]
) -> list[float] | None:
    if bench is None:
        return None
    ds, vs = bench
    out = []
    for d in dates:
        i = bisect.bisect_right(ds, d) - 1
        if i < 0:
            return None
        out.append(vs[i])
    return out


# -- walk-forward ---------------------------------------------------------------------------------
@dataclass
class Window:
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    chosen: dict[str, float]
    train_score: float | None
    test_score: float | None  # the chosen parameters on the test year, for the stability check
    default_test_score: float | None  # the config defaults on the same year


@dataclass
class BacktestResult:
    status: str  # ok | refused | insufficient
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    config_version: str = ""
    momentum_hash: str = ""
    window: dict[str, Any] = field(default_factory=dict)
    coverage: dict[str, Any] = field(default_factory=dict)
    gross: Perf | None = None
    after_cost: Perf | None = None
    after_tax: Perf | None = None
    after_tax_liquidated: Perf | None = None
    benchmark: Perf | None = None
    in_sample: dict[str, Perf] = field(default_factory=dict)
    windows: list[Window] = field(default_factory=list)
    realised_by_fy: dict[str, dict[str, float]] = field(default_factory=dict)
    tax_by_fy: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _score(p: Perf, how: str) -> float | None:
    return p.sharpe if how == "after_cost_sharpe" else p.cagr_pct


def _slice(sim: SimResult, lo: dt.date, hi: dt.date) -> tuple[list[dt.date], list[float]]:
    pairs = [(d, e) for d, e in zip(sim.dates, sim.equity, strict=False) if lo <= d <= hi]
    return [d for d, _ in pairs], [e for _, e in pairs]


def _add_years(d: dt.date, n: int) -> dt.date:
    try:
        return d.replace(year=d.year + n)
    except ValueError:  # 29 Feb
        return d.replace(year=d.year + n, day=28)


def walk_forward(
    panel: pd.DataFrame,
    book: PriceBook,
    cfg: CalibrationConfig,
    rates: TaxRates,
    bench: tuple[list[dt.date], list[float]] | None,
) -> tuple[list[Window], Schedule | None, dt.date | None]:
    """Choose parameters per test year from the years before it; returns the windows and a schedule."""
    bt = cfg.backtest
    wf = bt.walk_forward
    rules = bt.portfolio
    axes = {k: list(v) for k, v in wf.grid.items()}
    names = sorted(axes)
    combos = [
        dict(zip(names, vals, strict=True)) for vals in itertools.product(*(axes[n] for n in names))
    ]
    gap = cfg.outcomes.delisted_gap_days
    runs: list[tuple[dict[str, float], SimResult]] = []
    for combo in combos:
        params = Params.from_rules(rules, **combo)
        runs.append(
            (combo, simulate(panel, book, bt, lambda _d, p=params: p, rates, costs=True, tax=False,
                             delisted_gap_days=gap))
        )  # fmt: skip
    base = Params.from_rules(rules)
    base_run = simulate(
        panel, book, bt, lambda _d: base, rates, costs=True, tax=False, delisted_gap_days=gap
    )
    if not base_run.dates:
        return [], None, None
    first = base_run.dates[0]
    last = base_run.dates[-1]
    test_start = _add_years(first, wf.train_years)
    windows: list[Window] = []
    chosen_at: list[tuple[dt.date, Params]] = []
    while test_start < last:
        test_end = min(_add_years(test_start, wf.test_years), last)
        train_start = _add_years(test_start, -wf.train_years)
        best: tuple[float, dict[str, float]] | None = None
        for combo, sim in runs:
            d, e = _slice(sim, train_start, test_start - dt.timedelta(days=1))
            sc = _score(perf_of(d, e, bt.risk_free_pct), wf.select_by)
            if sc is not None and (best is None or sc > best[0]):
                best = (sc, combo)
        if best is None:
            test_start = _add_years(test_start, wf.step_years)
            continue
        combo = best[1]
        sim = next(s for c, s in runs if c == combo)
        d, e = _slice(sim, test_start, test_end)
        dd, de = _slice(base_run, test_start, test_end)
        windows.append(
            Window(
                train_start.isoformat(), (test_start - dt.timedelta(days=1)).isoformat(),
                test_start.isoformat(), test_end.isoformat(), combo, best[0],
                _score(perf_of(d, e, bt.risk_free_pct), wf.select_by),
                _score(perf_of(dd, de, bt.risk_free_pct), wf.select_by),
            )
        )  # fmt: skip
        chosen_at.append((test_start, Params.from_rules(rules, **combo)))
        test_start = _add_years(test_start, wf.step_years)
    if not windows:
        return [], None, None

    def schedule(asof: dt.date) -> Params:
        active = base
        for start, p in chosen_at:
            if asof >= start:
                active = p
        return active

    return windows, schedule, _add_years(first, wf.train_years)


def run_backtest(
    panel: pd.DataFrame,
    book: PriceBook,
    bench_series: pd.Series | None,
    cfg: CalibrationConfig,
    rates: TaxRates,
    *,
    membership_ok: bool,
    coverage: dict[str, Any],
    momentum_hash: str = "",
    allow_proxy: bool = False,
) -> BacktestResult:
    res = BacktestResult(
        status="ok", config_version=cfg.version, momentum_hash=momentum_hash, coverage=coverage
    )
    bt = cfg.backtest
    if panel.empty:
        res.status = "insufficient"
        res.reasons.append("no scored stock-months: load prices and index membership first")
        return res
    if not membership_ok:
        msg = (
            "index membership history does not cover the test window, so the universe on past "
            "dates would be today's index members (survivorship bias, AC-F17.1)"
        )
        if bt.require_membership_history and not allow_proxy:
            res.status = "refused"
            res.reasons.append(
                msg + ". Import historical constituents with "
                "`parakh calibration membership-import`, or pass --allow-proxy "
                "to run it labelled as biased."
            )
            return res
        res.warnings.append("SURVIVORSHIP-BIASED: " + msg)
    bench = series_from(bench_series)
    if bench is None:
        res.warnings.append(f"benchmark {bt.benchmark} not loaded: no excess return or beta")
    windows, schedule, oos_start = walk_forward(panel, book, cfg, rates, bench)
    res.windows = windows
    gap = cfg.outcomes.delisted_gap_days
    if schedule is None or oos_start is None:
        res.status = "insufficient"
        res.reasons.append(
            f"need more than {bt.walk_forward.train_years} years of scored months before the first "
            "out-of-sample year; the panel is shorter"
        )
        base = Params.from_rules(bt.portfolio)
        sim = simulate(
            panel, book, bt, lambda _d: base, rates, costs=True, tax=True, delisted_gap_days=gap
        )
        if sim.dates:
            res.after_tax = perf_of(
                sim.dates, sim.equity, bt.risk_free_pct, bench_at(bench, sim.dates), sim
            )
            res.warnings.append(
                "figures below are in-sample only, with the config default parameters"
            )
        return res
    variants = {"gross": (False, False), "after_cost": (True, False), "after_tax": (True, True)}
    sims: dict[str, SimResult] = {}
    for name, (c, t) in variants.items():
        sims[name] = simulate(panel, book, bt, schedule, rates, costs=c, tax=t, start=oos_start,
                              delisted_gap_days=gap)  # fmt: skip
    ref = sims["after_tax"]
    if not ref.dates:
        res.status = "insufficient"
        res.reasons.append("no out-of-sample rebalance dates")
        return res
    b_eq = bench_at(bench, ref.dates)
    res.gross = perf_of(
        sims["gross"].dates, sims["gross"].equity, bt.risk_free_pct, b_eq, sims["gross"]
    )
    res.after_cost = perf_of(
        sims["after_cost"].dates,
        sims["after_cost"].equity,
        bt.risk_free_pct,
        b_eq,
        sims["after_cost"],
    )
    res.after_tax = perf_of(ref.dates, ref.equity, bt.risk_free_pct, b_eq, ref)
    liquidated = ref.equity[-1] - ref.liquidation_tax_inr - ref.liquidation_cost_inr
    res.after_tax_liquidated = perf_of(
        ref.dates, ref.equity, bt.risk_free_pct, b_eq, ref, end_override=liquidated
    )
    if b_eq:
        be = [ref.start_inr * v / b_eq[0] for v in b_eq]
        res.benchmark = perf_of(ref.dates, be, bt.risk_free_pct)
    first_win = windows[0].test_start
    res.window = {
        "oos_start": first_win,
        "oos_end": ref.dates[-1].isoformat(),
        "train_years": bt.walk_forward.train_years,
        "test_years": bt.walk_forward.test_years,
        "rebalances": len(ref.dates) - 1,
        "panel_months": int(panel["period"].nunique()),
        "panel_first": str(panel["asof"].min()),
        "panel_last": str(panel["asof"].max()),
    }
    base = Params.from_rules(bt.portfolio)
    s_default = simulate(
        panel, book, bt, lambda _d: base, rates, costs=True, tax=False, delisted_gap_days=gap
    )
    res.in_sample["default_params_full_period"] = perf_of(
        s_default.dates,
        s_default.equity,
        bt.risk_free_pct,
        bench_at(bench, s_default.dates),
        s_default,
    )
    res.realised_by_fy = {
        f"FY{f}-{(f + 1) % 100:02d}": {"stcg_inr": v[0], "ltcg_inr": v[1]}
        for f, v in sorted(ref.realised.items())
    }
    res.tax_by_fy = {f"FY{f}-{(f + 1) % 100:02d}": t for f, t in sorted(ref.tax_by_fy.items())}
    if len(windows) < 3:
        res.warnings.append(
            f"only {len(windows)} out-of-sample year(s): too few to judge whether the choice of "
            "parameters is stable"
        )
    chosen = {tuple(sorted(w.chosen.items())) for w in windows}
    if len(chosen) > max(1, len(windows) // 2):
        res.warnings.append(
            "the walk-forward chose a different parameter set in most years: the result is "
            "sensitive to the knobs, treat the headline with caution"
        )
    return res
