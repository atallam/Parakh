# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false, reportOperatorIssue=false, reportOptionalSubscript=false, reportAssignmentType=false, reportGeneralTypeIssues=false
# why: tests build pandas/numpy fixtures and read optional result fields the assertions already prove are set
"""F17 backtest: point-in-time membership, costs, tax, walk-forward discipline (AC-F17.1, AC-F17.2)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from parakh.calibration import backtest as bt
from parakh.calibration.membership import Membership, Span, import_csv
from parakh.calibration.panel import build_panel, month_ends
from parakh.configs import load_all
from tests.helpers.calibration import frame, securities, trailing_panel, world

BUNDLE = load_all()
CAL = BUNDLE.calibration
RATES = BUNDLE.portfolio.tax


# -- membership -----------------------------------------------------------------------------------
def test_membership_spans_are_half_open() -> None:
    m = Membership.from_rows(
        [
            {
                "index_id": "NIFTY 100",
                "isin": "A",
                "valid_from": "2020-01-31",
                "valid_to": "2021-06-30",
            }
        ]
    )
    assert m.members_on("NIFTY 100", dt.date(2020, 1, 30)) == set()
    assert m.members_on("NIFTY 100", dt.date(2020, 1, 31)) == {"A"}
    assert m.members_on("NIFTY 100", dt.date(2021, 6, 29)) == {"A"}
    assert m.members_on("NIFTY 100", dt.date(2021, 6, 30)) == set()  # the first day it is out


def test_membership_coverage_and_window() -> None:
    m = Membership(
        [Span("NIFTY 100", "A", dt.date(2026, 10, 1)), Span("NIFTY 500", "A", dt.date(2016, 1, 1))]
    )
    assert m.coverage_start("NIFTY 100") == dt.date(2026, 10, 1)
    assert not m.covers_window(["NIFTY 100"], dt.date(2017, 1, 1))
    assert m.covers_window(["NIFTY 500"], dt.date(2017, 1, 1))
    assert not m.covers_window(["NIFTY 100", "MISSING"], dt.date(2030, 1, 1))


def test_membership_rejects_bad_rows() -> None:
    with pytest.raises(ValueError, match="ends before"):
        Membership.from_rows(
            [{"index_id": "X", "isin": "A", "valid_from": "2020-02-01", "valid_to": "2020-01-01"}]
        )
    with pytest.raises(ValueError, match="lacks"):
        Membership.from_rows([{"index_id": "X", "isin": "", "valid_from": "2020-02-01"}])


def test_membership_import_merges_without_duplicates(tmp_path: Path) -> None:
    src, dst = tmp_path / "in.csv", tmp_path / "state" / "hist.csv"
    src.write_text(
        "index_id,isin,valid_from,valid_to\nNIFTY 100,A,2019-01-01,2020-01-01\nNIFTY 100,B,2019-01-01,\n"
    )
    assert import_csv(src, dst) == 2
    assert import_csv(src, dst) == 2  # the same file again adds nothing
    assert Membership.from_csv(dst).members_on("NIFTY 100", dt.date(2019, 6, 1)) == {"A", "B"}


# -- tax ------------------------------------------------------------------------------------------
def test_tax_due_rules() -> None:
    cess = 1 + RATES.cess_pct / 100
    assert bt.tax_due(100_000, 0, RATES) == pytest.approx(100_000 * 0.20 * cess)
    assert bt.tax_due(0, 100_000, RATES) == 0  # inside the ₹1.25 lakh exemption
    assert bt.tax_due(0, 225_000, RATES) == pytest.approx(100_000 * 0.125 * cess)
    assert bt.tax_due(-50_000, 225_000, RATES) == pytest.approx(
        50_000 * 0.125 * cess
    )  # STCL sets off LTCG
    assert bt.tax_due(80_000, -30_000, RATES) == pytest.approx(
        80_000 * 0.20 * cess
    )  # LTCL does not touch STCG
    assert bt.tax_due(-10, -10, RATES) == 0
    assert bt.fy_of(dt.date(2026, 3, 31)) == 2025
    assert bt.fy_of(dt.date(2026, 4, 1)) == 2026


# -- selection ------------------------------------------------------------------------------------
def params(**over: float) -> bt.Params:
    return bt.Params.from_rules(CAL.backtest.portfolio, **over)


def ranked(n: int) -> list[tuple[str, float, str]]:
    return [(f"S{i:02d}", 99.0 - i, "large") for i in range(n)]  # S00 best


def test_select_top_share_and_min_score() -> None:
    p = params(top_pct=20, min_score=0)
    got = [i for i, _ in bt.select_targets(ranked(50), set(), p)]
    assert got == [f"S{i:02d}" for i in range(10)]
    only_four = params(top_pct=20, min_score=96)  # S00..S03 score at least 96
    assert (
        len(bt.select_targets(ranked(50), set(), params(top_pct=20, min_score=96, min_names=1)))
        == 4
    )
    assert bt.select_targets(ranked(50), set(), only_four) == []  # fewer than min_names (5) → cash


def test_rank_buffer_keeps_a_holder_that_slipped() -> None:
    p = params(top_pct=20, buffer_pct=40, min_score=0)
    held = {"S15"}  # rank 16 of 50: outside the top 10 but inside the 20-name buffer
    got = [i for i, _ in bt.select_targets(ranked(50), held, p)]
    assert "S15" in got and len(got) == 10
    out = [i for i, _ in bt.select_targets(ranked(50), {"S30"}, p)]
    assert "S30" not in out  # rank 31 is beyond the buffer


# -- simulation: costs and tax on a hand-made path -----------------------------------------------
def two_stock_world() -> tuple[pd.DataFrame, bt.PriceBook, pd.DataFrame]:
    """A is bought, doubles, then B takes the top rank; month-ends are real business days."""
    days = pd.bdate_range("2024-01-01", "2025-12-31")
    a = np.where(days < pd.Timestamp("2024-06-01"), 100.0, 200.0)
    b = np.full(len(days), 100.0)
    prices = {"A": frame("A", days, a), "B": frame("B", days, b)}
    rows = []
    for asof in month_ends([d.date() for d in days]):
        top = "A" if asof < dt.date(2024, 8, 1) else "B"
        for isin in ("A", "B"):
            rows.append(
                {
                    "period": f"{asof:%Y-%m}", "asof": asof, "isin": isin, "symbol": isin,
                    "segment": "large", "member": True, "close": 1.0,
                    "score": 90.0 if isin == top else 10.0, "view": "N", "confidence": "High",
                    "informational": False, "sessions": 400, "rs_percentile": None, "signals": "",
                    "momentum_hash": "t",
                }
            )  # fmt: skip
    return pd.DataFrame(rows), bt.PriceBook.from_frames(prices), pd.DataFrame(prices["A"])


def run(
    panel: pd.DataFrame, book: bt.PriceBook, *, costs: bool, tax: bool, cfg=CAL.backtest
) -> bt.SimResult:  # type: ignore[no-untyped-def]
    p = bt.Params.from_rules(cfg.portfolio, top_pct=50, min_score=0, min_names=1, buffer_pct=50)
    return bt.simulate(panel, book, cfg, lambda _d: p, RATES, costs=costs, tax=tax)


@pytest.mark.ac("AC-F17.2")
def test_gross_after_cost_after_tax_are_ordered_and_reported() -> None:
    panel, book, _ = two_stock_world()
    gross = run(panel, book, costs=False, tax=False)
    cost = run(panel, book, costs=True, tax=False)
    taxed = run(panel, book, costs=True, tax=True)
    assert gross.equity[-1] > cost.equity[-1] > taxed.equity[-1]
    assert cost.cost_inr > 0 and gross.cost_inr == 0
    assert taxed.tax_inr > 0 and cost.tax_inr == 0
    # A was bought near 100 and sold near 200 inside 12 months: a short-term gain, taxed at 20% + cess
    fy = bt.fy_of(dt.date(2024, 9, 1))
    stcg, ltcg = taxed.realised[fy]
    assert ltcg == 0 and stcg > 0
    assert taxed.tax_by_fy[fy] == pytest.approx(bt.tax_due(stcg, ltcg, RATES))


def test_cost_matches_the_configured_basis_points() -> None:
    panel, book, _ = two_stock_world()
    cost = run(panel, book, costs=True, tax=False)
    c = CAL.backtest.costs
    buy = (c.statutory_buy_bps + c.impact_bps["large"]) / 1e4
    first_buy = (
        CAL.backtest.portfolio.initial_capital_inr
    )  # the whole book goes into the first name
    assert cost.cost_inr >= first_buy * buy / (1 + buy) * 0.99


def test_the_first_purchase_is_not_called_turnover() -> None:
    panel, book, _ = two_stock_world()
    sim = run(panel, book, costs=False, tax=False)
    assert len(sim.turnover) == len(sim.dates) - 2 or len(sim.turnover) >= 1
    assert (
        sim.turnover[0] < 1.01
    )  # a switch is at most a full sale and a full purchase, not the build-up


def test_series_starts_at_the_capital_before_costs() -> None:
    panel, book, _ = two_stock_world()
    sim = run(panel, book, costs=True, tax=False)
    assert sim.equity[0] == pytest.approx(CAL.backtest.portfolio.initial_capital_inr)
    assert sim.equity[1] < sim.equity[0] * 1.2  # the first month's cost is inside the first period


def test_a_held_stock_whose_series_ends_is_sold_and_counted() -> None:
    days = pd.bdate_range("2024-01-01", "2025-06-30")
    a_days = days[days < pd.Timestamp("2024-09-15")]
    prices = {
        "A": frame("A", a_days, np.full(len(a_days), 100.0)),
        "B": frame("B", days, np.full(len(days), 100.0)),
    }
    rows = []
    for asof in month_ends([d.date() for d in days]):
        for isin in ("A", "B"):
            if isin == "A" and asof > dt.date(2024, 9, 14):
                continue  # delisted: no row after it stopped trading
            rows.append(
                {
                    "period": f"{asof:%Y-%m}", "asof": asof, "isin": isin, "symbol": isin,
                    "segment": "large", "member": True, "close": 1.0,
                    "score": 90.0 if isin == "A" else 40.0, "view": "N", "confidence": "High",
                    "informational": False, "sessions": 400, "rs_percentile": None, "signals": "",
                    "momentum_hash": "t",
                }
            )  # fmt: skip
    sim = run(pd.DataFrame(rows), bt.PriceBook.from_frames(prices), costs=False, tax=False)
    assert [i for i, _ in sim.delisted] == ["A"]
    assert sim.equity[-1] > 0


# -- point-in-time through the real panel builder -------------------------------------------------
@pytest.fixture(scope="module")
def panel_world(module_isolation):  # type: ignore[no-untyped-def]
    prices, bench, isins = world(n_stocks=10, years=4.2, seed=3)
    secs = securities(isins)
    joiner, leaver = isins[0], isins[1]
    m = Membership(
        [Span("NIFTY 100", i, dt.date(2000, 1, 1)) for i in isins[2:]]
        + [Span("NIFTY 100", joiner, dt.date(2026, 1, 1))]
        + [Span("NIFTY 100", leaver, dt.date(2000, 1, 1), dt.date(2026, 3, 1))]
    )
    days = sorted({pd.Timestamp(d).date() for f in prices.values() for d in f["trade_date"]})
    rb = [d for d in month_ends(days) if d >= dt.date(2025, 10, 1)]
    panel = build_panel(BUNDLE, secs, prices, {"large": bench}, m, rb)
    return panel, prices, bench, secs, m, rb, joiner, leaver


@pytest.mark.ac("AC-F17.1")
def test_panel_only_holds_constituents_valid_on_each_date(panel_world) -> None:  # type: ignore[no-untyped-def]
    panel, _p, _b, _s, _m, rb, joiner, leaver = panel_world
    early = panel[panel["asof"] < dt.date(2026, 1, 1)]
    assert joiner not in set(early["isin"])  # not a member yet, however well it did later
    assert joiner in set(panel[panel["asof"] >= dt.date(2026, 1, 1)]["isin"])
    late = panel[panel["asof"] >= dt.date(2026, 3, 1)]
    assert leaver not in set(late["isin"])
    assert leaver in set(panel[panel["asof"] < dt.date(2026, 3, 1)]["isin"])
    assert panel["member"].all()
    assert set(panel["period"]) == {f"{d:%Y-%m}" for d in rb}


def test_panel_has_no_lookahead(panel_world) -> None:  # type: ignore[no-untyped-def]
    panel, prices, bench, secs, m, rb, *_ = panel_world
    cut = rb[-3]
    jumped = {k: v.copy() for k, v in prices.items()}
    for f in jumped.values():  # a violent move after the cut date must not touch earlier rows
        after = pd.to_datetime(f["trade_date"]).dt.date > cut
        for col in ("open", "high", "low", "close", "adj_close"):
            f.loc[after, col] = f.loc[after, col] * 3.0
    again = build_panel(BUNDLE, secs, jumped, {"large": bench}, m, [d for d in rb if d <= cut])
    a = panel[panel["asof"] <= cut].reset_index(drop=True)
    b = again.reset_index(drop=True)
    cols = ["asof", "isin", "score", "view", "signals"]
    pd.testing.assert_frame_equal(a[cols], b[cols], check_dtype=False)


def test_panel_reuses_rows_scored_under_the_same_settings(panel_world) -> None:  # type: ignore[no-untyped-def]
    panel, prices, bench, secs, m, rb, *_ = panel_world
    again = build_panel(BUNDLE, secs, prices, {"large": bench}, m, rb, existing=panel)
    assert len(again) == len(panel)


def test_without_membership_the_panel_marks_every_row_as_proxy() -> None:
    prices, bench, isins = world(n_stocks=6, years=2.0, seed=2)
    days = sorted({pd.Timestamp(d).date() for f in prices.values() for d in f["trade_date"]})
    p = build_panel(
        BUNDLE, securities(isins), prices, {"large": bench}, None, month_ends(days)[-2:]
    )
    assert len(p) > 0
    assert not p["member"].any()


# -- the whole backtest ---------------------------------------------------------------------------
def test_run_backtest_refuses_without_membership_history() -> None:
    prices, bench, isins = world(n_stocks=20, years=9.0, seed=5)
    book = bt.PriceBook.from_frames(prices)
    panel = trailing_panel(prices)
    res = bt.run_backtest(
        panel, book, bench, CAL, RATES, membership_ok=False, coverage={"covered": False}
    )
    assert res.status == "refused" and "survivorship" in res.reasons[0]
    assert res.gross is None


@pytest.mark.ac("AC-F17.2")
def test_run_backtest_reports_all_three_returns_and_the_walk_forward() -> None:
    prices, bench, isins = world(n_stocks=24, years=11.0, seed=11)
    book = bt.PriceBook.from_frames(prices)
    panel = trailing_panel(prices)
    res = bt.run_backtest(
        panel, book, bench, CAL, RATES, membership_ok=False, coverage={}, allow_proxy=True
    )
    assert res.status == "ok"
    assert any("SURVIVORSHIP" in w for w in res.warnings)
    assert (
        res.gross
        and res.after_cost
        and res.after_tax
        and res.after_tax_liquidated
        and res.benchmark
    )
    assert res.gross.cagr_pct > res.after_cost.cagr_pct > res.after_tax.cagr_pct
    assert res.after_tax_liquidated.end_inr <= res.after_tax.end_inr
    assert res.windows and all(w.train_end < w.test_start for w in res.windows)
    assert res.window["oos_start"] == res.windows[0].test_start
    assert res.after_tax.excess_cagr_pct is not None
    assert res.as_dict()["status"] == "ok"


def test_walk_forward_choice_for_a_year_ignores_that_year_and_after() -> None:
    prices, bench, isins = world(n_stocks=24, years=11.0, seed=11)
    book = bt.PriceBook.from_frames(prices)
    panel = trailing_panel(prices)
    base = bt.run_backtest(panel, book, bench, CAL, RATES, membership_ok=True, coverage={})
    # rewrite the last two years of prices (thereby the panel scores for them) completely
    days = sorted(book.days)
    cutoff = days[-1] - dt.timedelta(days=2 * 365)
    mutated = {}
    rng = np.random.default_rng(99)
    for isin, f in prices.items():
        g = f.copy()
        late = pd.to_datetime(g["trade_date"]).dt.date > cutoff
        noise = np.exp(np.cumsum(rng.normal(0, 0.02, int(late.sum()))))
        for col in ("open", "high", "low", "close", "adj_close"):
            g.loc[late, col] = g.loc[late, col].to_numpy() * noise
        mutated[isin] = g
    book2 = bt.PriceBook.from_frames(mutated)
    panel2 = trailing_panel(mutated)
    again = bt.run_backtest(panel2, book2, bench, CAL, RATES, membership_ok=True, coverage={})
    early = [w for w in base.windows if w.test_end < cutoff.isoformat()]
    assert early, "the fixture needs at least one test year before the cutoff"
    for w, w2 in zip(base.windows, again.windows, strict=False):
        if w in early:
            assert w.chosen == w2.chosen and w.train_score == pytest.approx(w2.train_score)


def test_too_short_a_history_is_reported_not_faked() -> None:
    prices, bench, isins = world(n_stocks=24, years=3.0, seed=4)
    panel = trailing_panel(prices)
    res = bt.run_backtest(
        panel, bt.PriceBook.from_frames(prices), bench, CAL, RATES, membership_ok=True, coverage={}
    )
    assert res.status == "insufficient" and "out-of-sample" in res.reasons[0]


def test_perf_metrics_on_a_known_curve() -> None:
    dates = [dt.date(2024, 1, 1) + dt.timedelta(days=30 * i) for i in range(13)]
    eq = [100.0 * 1.01**i for i in range(13)]
    p = bt.perf_of(dates, eq, 0.0)
    assert p.months == 12 and p.max_drawdown_pct == 0
    assert p.cagr_pct == pytest.approx((1.01**12) ** (365.25 / 360) * 100 - 100, rel=0.02)
    eq2 = [100, 110, 99, 120]
    assert bt.perf_of(dates[:4], eq2, 0.0).max_drawdown_pct == pytest.approx(-10.0)
