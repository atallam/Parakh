# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportReturnType=false, reportArgumentType=false, reportOperatorIssue=false, reportAssignmentType=false
# why: the pandas stubs infer ndarray/Series unions for indexing and sorting that are Series at run time; tests cover these paths
"""Value metrics (plan 01 §2). Each takes a `VCalc` and returns a `Measure` (value or reason).

Registered under `MET.value.*`. Figures come from the Screener export (consolidated, ₹ crore)
and the shareholding table; metrics the export cannot supply (bank asset quality, lease
liabilities, order books and the like) read analyst/filing inputs from `profile_inputs.yaml` and
show ❔ N/A with that reason when no input exists (plan 13 §8.0c).
"""

from __future__ import annotations

import statistics
from collections.abc import Callable

import numpy as np
import pandas as pd

from parakh.analytics import intrinsic as iv
from parakh.analytics.value_calc import Measure, VCalc
from parakh.registry import register_metric

ValueFn = Callable[[VCalc], Measure]
VALUE_METRICS: dict[str, ValueFn] = {}
LENS = ["LENS.value"]
P = "MET.value."


def value_metric(ident: str, unit: str, inputs: list[str]) -> Callable[[ValueFn], ValueFn]:
    def deco(fn: ValueFn) -> ValueFn:
        register_metric(id=ident, unit=unit, inputs=inputs, used_by=LENS)(fn)  # type: ignore[arg-type]
        VALUE_METRICS[ident] = fn
        return fn

    return deco


def _na(why: str) -> Measure:
    return Measure.na(why)


def _median_tail(s: pd.Series, years: int) -> tuple[float, int] | None:
    tail = s.iloc[-years:]
    if len(tail) < max(3, min(years, 3)):
        return None
    return float(statistics.median(tail.tolist())), len(tail)


# -- valuation -------------------------------------------------------------------------------
@value_metric(P + "pe_ttm", "x", ["prices.close", "fundamentals.quarterly_pl"])
def pe_ttm(v: VCalc) -> Measure:
    """Price ÷ trailing-twelve-month earnings per share.

    Formula:   price ÷ (sum of last four quarters' net profit ÷ adjusted shares)
    Meaning:   What the market pays for a rupee of current earnings.
    Pitfalls:  N/A on a loss (negative EPS); uses the export's adjusted share count.
    Source:    prices; Screener export (quarterly P&L, derived shares)
    """
    eps = v.eps_ttm()
    if v.inp.price is None:
        return _na("no price at the as-of date")
    if eps is None:
        return _na("fewer than four consecutive quarters of results")
    if eps <= 0:
        return _na("loss-making: TTM EPS is not positive")
    return Measure(v.inp.price / eps)


def _pe_discount(v: VCalc, years: int, key: str) -> Measure:
    cur = pe_ttm(v)
    if cur.value is None:
        return _na(cur.reason or "P/E unavailable")
    if why := v.own_history_gate(years):
        return _na(why)
    hist = v.pe_history()
    got = _median_tail(hist, years)
    need = max(3, years - 2)
    if got is None or got[1] < need:
        return _na(f"{0 if got is None else got[1]} usable year-end P/Es; needs {need}")
    med = got[0]
    return Measure((med - cur.value) / med)


@value_metric(P + "pe_discount_own_5y", "ratio", ["prices.close", "fundamentals.annual_price"])
def pe_discount_own_5y(v: VCalc) -> Measure:
    """Discount of the current P/E to the stock's own 5-year median year-end P/E.

    Formula:   (median P/E of the last 5 fiscal year-ends − current P/E) ÷ that median
    Meaning:   Positive means cheap for itself; the core valuation metric in its most reliable form.
    Pitfalls:  N/A below 60 months of listing and with fewer than three usable years (H1/H0 rules).
    Source:    Screener export (year-end price, EPS); plan 01 §2.1
    """
    return _pe_discount(v, 5, "5y")


@value_metric(P + "pe_discount_own_10y", "ratio", ["prices.close", "fundamentals.annual_price"])
def pe_discount_own_10y(v: VCalc) -> Measure:
    """Discount of the current P/E to the stock's own 10-year median year-end P/E.

    Formula:   (median P/E of the last 10 fiscal year-ends − current P/E) ÷ that median
    Meaning:   The long-cycle version of the own-history test.
    Pitfalls:  N/A below 120 months of listing or with fewer than eight usable years.
    Source:    Screener export (year-end price, EPS); plan 01 §2.1
    """
    return _pe_discount(v, 10, "10y")


@value_metric(P + "pe_discount_own_3y", "ratio", ["prices.close", "fundamentals.annual_price"])
def pe_discount_own_3y(v: VCalc) -> Measure:
    """Discount of the current P/E to the stock's own 3-year median (the H1 and order-book anchor).

    Formula:   (median P/E of the last 3 fiscal year-ends − current P/E) ÷ that median
    Meaning:   Used where 5–10 year bands do not exist or a sector re-rating distorts them.
    Pitfalls:  N/A below 36 months of listing; only three data points, so low weight.
    Source:    Screener export (year-end price, EPS); plan 01 §3.1, §3
    """
    return _pe_discount(v, 3, "3y")


@value_metric(P + "pe_percentile_10y", "score", ["prices.close", "fundamentals.annual_price"])
def pe_percentile_10y(v: VCalc) -> Measure:
    """Where the current P/E sits within the stock's own year-end P/E history, 0–100.

    Formula:   100 × share of the last 10 year-end P/Es at or below the current P/E
    Meaning:   A high percentile means the multiple is near its own highs (fully-valued trigger above 90).
    Pitfalls:  Needs six usable years; informational, not scored.
    Source:    Screener export; plan 01 §5
    """
    cur = pe_ttm(v)
    if cur.value is None:
        return _na(cur.reason or "P/E unavailable")
    hist = v.pe_history().iloc[-10:]
    if len(hist) < 6:
        return _na(f"{len(hist)} usable year-end P/Es; needs 6")
    return Measure(float(100 * (hist <= cur.value).mean()))


@value_metric(P + "pe_sector_percentile", "score", ["peers.pe"])
def pe_sector_percentile(v: VCalc) -> Measure:
    """The stock's P/E rank among its sector peers, 0–100 (lower is cheaper).

    Formula:   100 × share of sector peers with a P/E at or below this stock's
    Meaning:   Relative cheapness among comparable businesses.
    Pitfalls:  Needs a peer set; pilot mode has none, so this is N/A until the segment universe loads.
    Source:    peer P/Es from the watchlist and index constituents; plan 01 §2.1
    """
    return _na("no sector peer set loaded (pilot universe)")


@value_metric(P + "peg", "x", ["prices.close", "fundamentals.annual_pl"])
def peg(v: VCalc) -> Measure:
    """P/E divided by the 3-year EPS growth rate in percent.

    Formula:   P/E ÷ (EPS CAGR 3y × 100)
    Meaning:   Growth-adjusted valuation; below 1 is strong, above 2.5 expensive.
    Pitfalls:  N/A when EPS CAGR is not positive or exceeds 50% (AC-F04.2).
    Source:    Screener export; plan 01 §2.1
    """
    cur, g = pe_ttm(v), eps_cagr_3y(v)
    if cur.value is None:
        return _na(cur.reason or "P/E unavailable")
    if g.value is None:
        return _na(g.reason or "EPS growth unavailable")
    if g.value <= 0:
        return _na("3-year EPS CAGR is not positive")
    if g.value > 0.5:
        return _na("3-year EPS CAGR above 50%: PEG not meaningful")
    return Measure(cur.value / (g.value * 100))


@value_metric(
    P + "ev_ebitda",
    "x",
    ["prices.close", "fundamentals.balance_sheet", "fundamentals.quarterly_pl"],
)
def ev_ebitda(v: VCalc) -> Measure:
    """Enterprise value divided by trailing operating profit.

    Formula:   (market cap + borrowings − cash) ÷ TTM operating profit
    Meaning:   Capital-structure-neutral valuation, so debt cannot flatter a cheap-looking P/E.
    Pitfalls:  Not for banks, NBFCs or insurers; lease-heavy companies use EV/EBITDAR instead.
    Source:    prices; Screener export; plan 01 §2.1
    """
    ev, op = v.ev_cr(), v.f.ttm("Operating Profit")
    if ev is None:
        return _na("market cap or net debt unavailable")
    if op is None or op <= 0:
        return _na("TTM operating profit unavailable or not positive")
    return Measure(ev / op)


@value_metric(
    P + "ev_ebitda_discount_own",
    "ratio",
    ["prices.close", "fundamentals.balance_sheet", "fundamentals.annual_pl"],
)
def ev_ebitda_discount_own(v: VCalc) -> Measure:
    """Discount of the current EV/EBITDA to its own 5-year median at fiscal year-ends.

    Formula:   (median year-end EV/EBITDA, last 5 years − current) ÷ that median
    Meaning:   Positive means cheap for itself on a debt-neutral basis.
    Pitfalls:  N/A below 60 months of listing; year-end EV uses the year-end price and balance sheet.
    Source:    Screener export; plan 01 §2.1
    """
    cur = ev_ebitda(v)
    if cur.value is None:
        return _na(cur.reason or "EV/EBITDA unavailable")
    if why := v.own_history_gate(5):
        return _na(why)
    price = v.f.annual("annual_price", "PRICE:")
    sh = v.f.annual("derived", "Adjusted Equity Shares in Cr")
    nd = (
        v.f.annual("balance_sheet", "Borrowings") - v.f.annual("balance_sheet", "Cash & Bank")
    ).dropna()
    e = v.ebitda_annual()
    d = pd.concat([price * sh, nd, e], axis=1, keys=["m", "nd", "e"]).dropna()
    d = d[d["e"] > 0]
    hist = ((d["m"] + d["nd"]) / d["e"]).iloc[-5:]
    if len(hist) < 3:
        return _na(f"{len(hist)} usable year-end EV/EBITDA values; needs 3")
    med = float(statistics.median(hist.tolist()))
    return Measure((med - cur.value) / med)


@value_metric(P + "pb", "x", ["prices.close", "fundamentals.balance_sheet"])
def pb(v: VCalc) -> Measure:
    """Price divided by book value per share.

    Formula:   market cap ÷ (equity capital + reserves)
    Meaning:   The primary valuation metric for banks and NBFCs.
    Pitfalls:  Book value includes intangibles; P/ABV (net NPAs deducted) needs asset-quality data.
    Source:    prices; Screener export (balance sheet)
    """
    nw, mc = v.net_worth(), v.mcap_cr
    if mc is None or not len(nw) or nw.iloc[-1] <= 0:
        return _na("market cap or positive net worth unavailable")
    return Measure(mc / float(nw.iloc[-1]))


@value_metric(P + "pb_discount_own_5y", "ratio", ["prices.close", "fundamentals.balance_sheet"])
def pb_discount_own_5y(v: VCalc) -> Measure:
    """Discount of the current P/B to the stock's own 5-year median year-end P/B.

    Formula:   (median P/B of the last 5 fiscal year-ends − current P/B) ÷ that median
    Meaning:   Positive means cheap for itself on book value.
    Pitfalls:  N/A below 60 months of listing. Per-share ratios stay comparable across a merger.
    Source:    Screener export; plan 01 §2.1
    """
    cur = pb(v)
    if cur.value is None:
        return _na(cur.reason or "P/B unavailable")
    if why := v.own_history_gate(5):
        return _na(why)
    got = _median_tail(v.pb_history(), 5)
    if got is None or got[1] < 3:
        return _na("fewer than three usable year-end P/B values")
    return Measure((got[0] - cur.value) / got[0])


@value_metric(
    P + "pb_justified_gap",
    "ratio",
    ["prices.close", "fundamentals.balance_sheet", "fundamentals.annual_pl"],
)
def pb_justified_gap(v: VCalc) -> Measure:
    """How far the market P/B sits below the P/B that ROE justifies.

    Formula:   (ROE_5y_avg ÷ cost of equity) ÷ P/B − 1
    Meaning:   Positive means the market pays less than the bank's returns warrant.
    Pitfalls:  Sensitive to the cost-of-equity assumption (config); ROE must be sustainable.
    Source:    Screener export; plan 01 §2.1
    """
    cur, roe = pb(v), roe_5y_avg(v)
    if cur.value is None or roe.value is None:
        return _na(cur.reason or roe.reason or "P/B or ROE unavailable")
    return Measure(roe.value / v.cfg.dcf.cost_of_equity / cur.value - 1)


@value_metric(P + "earnings_yield_spread", "ratio", ["prices.close", "macro.g_sec_10y"])
def earnings_yield_spread(v: VCalc) -> Measure:
    """Earnings yield minus the 10-year government bond yield.

    Formula:   1 ÷ P/E − 10y G-sec yield
    Meaning:   Equity versus bond opportunity cost.
    Pitfalls:  N/A until a G-sec yield is configured or loaded by the market-context layer (F16).
    Source:    prices; config g_sec_yield (placeholder for the macro feed)
    """
    cur = pe_ttm(v)
    if cur.value is None:
        return _na(cur.reason or "P/E unavailable")
    if v.cfg.g_sec_yield is None:
        return _na("10-year G-sec yield not configured")
    return Measure(1 / cur.value - v.cfg.g_sec_yield)


@value_metric(P + "fcf_yield", "ratio", ["prices.close", "fundamentals.cash_flow"])
def fcf_yield(v: VCalc) -> Measure:
    """Three-year average free cash flow divided by market cap.

    Formula:   mean(CFO − capex proxy, last 3 years) ÷ market cap
    Meaning:   Cash-based valuation that is harder to window-dress; negative earns no points.
    Pitfalls:  Capex is a proxy (change in net block and CWIP plus depreciation); not for banks.
    Source:    Screener export; plan 01 §2.1
    """
    fcf, mc = v.fcf_annual().iloc[-3:], v.mcap_cr
    if mc is None or len(fcf) < 2:
        return _na("market cap or two years of cash flow unavailable")
    return Measure(float(fcf.mean() / mc))


@value_metric(P + "dividend_yield", "ratio", ["prices.close", "fundamentals.annual_pl"])
def dividend_yield(v: VCalc) -> Measure:
    """Latest fiscal year's dividend divided by market cap.

    Formula:   dividend amount ÷ market cap
    Meaning:   Income support and capital-allocation signal; informational.
    Pitfalls:  Uses the last fiscal year, not a forward estimate.
    Source:    Screener export; plan 01 §2.1
    """
    d, mc = v.ann("annual_pl", "Dividend Amount"), v.mcap_cr
    if mc is None or not len(d):
        return _na("dividend or market cap unavailable")
    return Measure(float(d.iloc[-1] / mc))


@value_metric(P + "pe_normalised", "x", ["prices.close", "fundamentals.annual_pl"])
def pe_normalised(v: VCalc) -> Measure:
    """Price divided by the average EPS of up to ten fiscal years (cyclicals and airlines).

    Formula:   price ÷ mean(EPS, last 10 years)
    Meaning:   Avoids calling a cyclical cheap at peak earnings or expensive at the trough.
    Pitfalls:  Needs five years of EPS; loss years stay in the average (they are the cycle).
    Source:    Screener export; plan 01 §3, §11 #5
    """
    eps = v.eps_annual().iloc[-10:]
    if v.inp.price is None or len(eps) < 5:
        return _na(f"{len(eps)} years of EPS; needs 5")
    avg = float(eps.mean())
    if avg <= 0:
        return _na("average EPS over the cycle is not positive")
    return Measure(v.inp.price / avg)


@value_metric(P + "pe_2y_avg_discount_3y", "ratio", ["prices.close", "fundamentals.annual_pl"])
def pe_2y_avg_discount_3y(v: VCalc) -> Measure:
    """Order-book businesses: P/E on 2-year average EPS versus its own 3-year median.

    Formula:   (median of year-end price ÷ trailing 2-year average EPS, last 3 years − current) ÷ median
    Meaning:   Smooths lumpy execution and avoids 5–10 year bands distorted by a sector re-rating.
    Pitfalls:  Only three comparison points; peers' multiples are the second anchor (needs a peer set).
    Source:    Screener export; plan 01 §3
    """
    eps = v.eps_annual()
    price = v.f.annual("annual_price", "PRICE:")
    avg2 = eps.rolling(2).mean()
    d = pd.concat([price, avg2], axis=1, keys=["p", "e"]).dropna()
    d = d[d["e"] > 0]
    hist = (d["p"] / d["e"]).iloc[-3:]
    if v.inp.price is None or len(avg2.dropna()) == 0 or avg2.dropna().iloc[-1] <= 0:
        return _na("average EPS unavailable or not positive")
    if why := v.own_history_gate(3):
        return _na(why)
    if len(hist) < 3:
        return _na(f"{len(hist)} comparison years; needs 3")
    cur = v.inp.price / float(avg2.dropna().iloc[-1])
    med = float(statistics.median(hist.tolist()))
    return Measure((med - cur) / med)


@value_metric(
    P + "ev_sales", "x", ["prices.close", "fundamentals.quarterly_pl", "fundamentals.balance_sheet"]
)
def ev_sales(v: VCalc) -> Measure:
    """Enterprise value divided by trailing revenue.

    Formula:   (market cap + borrowings − cash) ÷ TTM sales
    Meaning:   Valuation for pre-profit growth companies where P/E does not exist.
    Pitfalls:  Ignores margins; read with the revenue growth and margin trajectory.
    Source:    prices; Screener export
    """
    ev, sales = v.ev_cr(), v.f.ttm("Sales")
    if ev is None or sales is None or sales <= 0:
        return _na("EV or TTM sales unavailable")
    return Measure(ev / sales)


@value_metric(P + "ev_sales_to_growth", "x", ["prices.close", "fundamentals.quarterly_pl"])
def ev_sales_to_growth(v: VCalc) -> Measure:
    """EV/Sales divided by revenue growth in percent (a growth-adjusted sales multiple).

    Formula:   (EV ÷ TTM sales) ÷ (latest-year revenue growth × 100)
    Meaning:   Lower means the market pays less per point of growth.
    Pitfalls:  N/A when revenue is not growing; informational for new-age companies.
    Source:    prices; Screener export; plan 01 §3
    """
    m, g = ev_sales(v), revenue_growth_1y(v)
    if m.value is None or g.value is None:
        return _na(m.reason or g.reason or "unavailable")
    if g.value <= 0:
        return _na("revenue is not growing")
    return Measure(m.value / (g.value * 100))


@value_metric(P + "ev_ebitdar", "x", ["prices.close", "profile_inputs.lease_liabilities_cr"])
def ev_ebitdar(v: VCalc) -> Measure:
    """Airlines: EV including lease liabilities divided by EBITDAR (EBITDA before lease cost).

    Formula:   (market cap + borrowings + lease liabilities − cash) ÷ (TTM operating profit + lease cost)
    Meaning:   Ind AS 116 moves leases onto the balance sheet, so EV and earnings must both include them.
    Pitfalls:  Needs lease liabilities and lease cost from filings (profile_inputs.yaml); N/A without them.
    Source:    Screener export; filings (analyst input); plan 01 §3
    """
    lease, cost = v.inputs_value("lease_liabilities_cr"), v.inputs_value("lease_cost_cr")
    ev, op = v.ev_cr(), v.f.ttm("Operating Profit")
    if lease.value is None or cost.value is None:
        return _na(lease.reason or cost.reason or "lease inputs missing")
    if ev is None or op is None:
        return _na("EV or operating profit unavailable")
    ebitdar = op + cost.value
    return Measure((ev + lease.value) / ebitdar) if ebitdar > 0 else _na("EBITDAR not positive")


@value_metric(P + "sotp_discount", "ratio", ["prices.close", "profile_inputs.listed_stakes"])
def sotp_discount(v: VCalc) -> Measure:
    """Conglomerates: discount of the market cap to the sum of the parts.

    Formula:   (SOTP − market cap) ÷ SOTP, with SOTP = core value + stakes at market × (1 − holdco discount) + unlisted at book
    Meaning:   Positive means the market values the group below its pieces.
    Pitfalls:  Needs the stake register, the stakes' market caps and the core standalone profit.
    Source:    shareholding filings, prices, standalone results (analyst input); plan 01 §3
    """
    s = sotp_value(v)
    mc = v.mcap_cr
    if s.value is None or mc is None:
        return _na(s.reason or "market cap unavailable")
    return Measure((s.value - mc) / s.value)


def sotp_value(v: VCalc, discount: float | None = None) -> Measure:
    """SOTP in ₹ crore (not a registered metric: it feeds the intrinsic range)."""
    d = v.cfg.dcf.holdco_discount if discount is None else discount
    pat = v.inputs_value("standalone_pat_cr")
    if pat.value is None:
        return _na(pat.reason or "standalone profit missing")
    pe_hist = _median_tail(v.pe_history(), 5)
    if pe_hist is None:
        return _na("own median P/E unavailable for the core business")
    if not v.inp.stakes:
        return _na("listed-stake register empty")
    missing = [s["name"] for s in v.inp.stakes if s.get("mcap_cr") is None]
    if missing:
        return _na(f"market cap missing for {', '.join(missing)}")
    core = pat.value * pe_hist[0]
    listed = sum(s["stake"] * s["mcap_cr"] for s in v.inp.stakes) * (1 - d)
    unlisted = v.inp.profile_inputs.get("unlisted_book_cr") or 0.0
    return Measure(core + listed + unlisted)


# -- quality ---------------------------------------------------------------------------------
def _avg_ratio(num: pd.Series, den: pd.Series, n: int) -> float | None:
    d = pd.concat([num, den], axis=1, keys=["n", "d"]).dropna()
    d = d[d["d"] > 0].iloc[-n:]
    if len(d) < min(n, 3):
        return None
    return float((d["n"] / d["d"]).mean())


def _latest_ratio(num: pd.Series, den: pd.Series) -> float | None:
    d = pd.concat([num, den], axis=1, keys=["n", "d"]).dropna()
    d = d[d["d"] > 0]
    return float(d["n"].iloc[-1] / d["d"].iloc[-1]) if len(d) else None


def _roce_parts(v: VCalc) -> tuple[pd.Series, pd.Series]:
    ebit = (v.ann("annual_pl", "Profit before tax") + v.ann("annual_pl", "Interest")).dropna()
    return ebit, v.capital_employed()


@value_metric(P + "roce_5y_avg", "ratio", ["fundamentals.annual_pl", "fundamentals.balance_sheet"])
def roce_5y_avg(v: VCalc) -> Measure:
    """Five-year average return on capital employed.

    Formula:   mean((PBT + interest) ÷ (equity + reserves + borrowings), last 5 years)
    Meaning:   The most important quality metric for Indian non-financials.
    Pitfalls:  Year-end capital (not average); lease-heavy and financial companies need their own measures.
    Source:    Screener export; plan 01 §2.2
    """
    r = _avg_ratio(*_roce_parts(v), 5)
    return Measure(r) if r is not None else _na("fewer than three years of ROCE inputs")


@value_metric(P + "roce_latest", "ratio", ["fundamentals.annual_pl", "fundamentals.balance_sheet"])
def roce_latest(v: VCalc) -> Measure:
    """Latest fiscal year's return on capital employed.

    Formula:   (PBT + interest) ÷ (equity + reserves + borrowings)
    Meaning:   Whether the 5-year average still holds today.
    Pitfalls:  A single year can mislead; read with the 5-year average and trend.
    Source:    Screener export; plan 01 §2.2
    """
    r = _latest_ratio(*_roce_parts(v))
    return Measure(r) if r is not None else _na("ROCE inputs unavailable")


@value_metric(
    P + "roce_trend_pp", "score", ["fundamentals.annual_pl", "fundamentals.balance_sheet"]
)
def roce_trend_pp(v: VCalc) -> Measure:
    """Change in ROCE over the last two fiscal years, in percentage points.

    Formula:   (ROCE_latest − ROCE two years earlier) × 100
    Meaning:   Falling ROCE is a thesis-break sign and part of the value-trap detector.
    Pitfalls:  Needs three consecutive years.
    Source:    Screener export; plan 01 §5, §11 #3
    """
    ebit, ce = _roce_parts(v)
    d = pd.concat([ebit, ce], axis=1, keys=["e", "c"]).dropna()
    d = d[d["c"] > 0]
    if len(d) < 3:
        return _na("fewer than three years of ROCE inputs")
    r = d["e"] / d["c"]
    return Measure(float((r.iloc[-1] - r.iloc[-3]) * 100))


@value_metric(P + "roe_5y_avg", "ratio", ["fundamentals.annual_pl", "fundamentals.balance_sheet"])
def roe_5y_avg(v: VCalc) -> Measure:
    """Five-year average return on equity.

    Formula:   mean(net profit ÷ (equity + reserves), last 5 years)
    Meaning:   Owner returns; high ROE driven by leverage is checked against debt/equity.
    Pitfalls:  Year-end equity; buybacks and write-offs distort single years.
    Source:    Screener export; plan 01 §2.2
    """
    r = _avg_ratio(v.ann("annual_pl", "Net profit"), v.net_worth(), 5)
    return Measure(r) if r is not None else _na("fewer than three years of ROE inputs")


@value_metric(P + "roe_latest", "ratio", ["fundamentals.annual_pl", "fundamentals.balance_sheet"])
def roe_latest(v: VCalc) -> Measure:
    """Latest fiscal year's return on equity.

    Formula:   net profit ÷ (equity + reserves)
    Meaning:   Whether the 5-year average still holds today.
    Pitfalls:  A single year can mislead.
    Source:    Screener export; plan 01 §2.2
    """
    r = _latest_ratio(v.ann("annual_pl", "Net profit"), v.net_worth())
    return Measure(r) if r is not None else _na("ROE inputs unavailable")


@value_metric(P + "roa_5y_avg", "ratio", ["fundamentals.annual_pl", "fundamentals.balance_sheet"])
def roa_5y_avg(v: VCalc) -> Measure:
    """Five-year average return on assets (the bank and NBFC quality measure).

    Formula:   mean(net profit ÷ total assets, last 5 years)
    Meaning:   Profit earned per rupee of balance sheet; the leverage-neutral bank metric.
    Pitfalls:  Year-end assets; a merger year distorts the denominator.
    Source:    Screener export; plan 01 §3
    """
    r = _avg_ratio(v.ann("annual_pl", "Net profit"), v.ann("balance_sheet", "Total Assets"), 5)
    return Measure(r) if r is not None else _na("fewer than three years of ROA inputs")


@value_metric(P + "roa_latest", "ratio", ["fundamentals.annual_pl", "fundamentals.balance_sheet"])
def roa_latest(v: VCalc) -> Measure:
    """Latest fiscal year's return on assets.

    Formula:   net profit ÷ total assets
    Meaning:   Whether the 5-year average still holds today.
    Pitfalls:  A single year can mislead.
    Source:    Screener export; plan 01 §3
    """
    r = _latest_ratio(v.ann("annual_pl", "Net profit"), v.ann("balance_sheet", "Total Assets"))
    return Measure(r) if r is not None else _na("ROA inputs unavailable")


@value_metric(P + "cfo_to_ebitda_3y", "ratio", ["fundamentals.cash_flow", "fundamentals.annual_pl"])
def cfo_to_ebitda_3y(v: VCalc) -> Measure:
    """Operating cash flow as a share of EBITDA over three years.

    Formula:   Σ CFO ÷ Σ EBITDA, last 3 years
    Meaning:   Low conversion suggests receivables or inventory build-up and weak earnings quality.
    Pitfalls:  EBITDA is derived (PBT + interest + depreciation − other income); not for banks.
    Source:    Screener export; plan 01 §2.2
    """
    d = (
        pd.concat(
            [v.ann("cash_flow", "Cash from Operating Activity"), v.ebitda_annual()],
            axis=1,
            keys=["c", "e"],
        )
        .dropna()
        .iloc[-3:]
    )
    if len(d) < 2 or d["e"].sum() <= 0:
        return _na("fewer than two years of CFO and EBITDA, or EBITDA not positive")
    return Measure(float(d["c"].sum() / d["e"].sum()))


@value_metric(P + "cfo_to_pat_3y", "ratio", ["fundamentals.cash_flow", "fundamentals.annual_pl"])
def cfo_to_pat_3y(v: VCalc) -> Measure:
    """Operating cash flow as a share of net profit over three years.

    Formula:   Σ CFO ÷ Σ net profit, last 3 years
    Meaning:   Profit that turns into cash; also the owner-earnings conversion for the DCF.
    Pitfalls:  N/A when three-year profit is not positive.
    Source:    Screener export; plan 01 §2.2
    """
    d = (
        pd.concat(
            [v.ann("cash_flow", "Cash from Operating Activity"), v.ann("annual_pl", "Net profit")],
            axis=1,
            keys=["c", "p"],
        )
        .dropna()
        .iloc[-3:]
    )
    if len(d) < 2 or d["p"].sum() <= 0:
        return _na("fewer than two years of CFO and profit, or profit not positive")
    return Measure(float(d["c"].sum() / d["p"].sum()))


@value_metric(P + "op_margin_trend_pp", "score", ["fundamentals.quarterly_pl"])
def op_margin_trend_pp(v: VCalc) -> Measure:
    """Operating-margin change: latest four quarters versus the four before, in percentage points.

    Formula:   (margin of last 4 quarters − margin of previous 4 quarters) × 100
    Meaning:   Falling margins with a falling P/E is a classic value trap.
    Pitfalls:  Needs eight quarters; seasonal businesses compare like with like because both windows span a year.
    Source:    Screener export; plan 01 §2.2
    """
    op, sales = (
        v.f.quarterly("quarterly_pl", "Operating Profit"),
        v.f.quarterly("quarterly_pl", "Sales"),
    )
    d = pd.concat([op, sales], axis=1, keys=["o", "s"]).dropna()
    if len(d) < 8:
        return _na(f"{len(d)} quarters; needs 8")
    a, b = d.iloc[-4:], d.iloc[-8:-4]
    if a["s"].sum() <= 0 or b["s"].sum() <= 0:
        return _na("sales not positive")
    return Measure(float((a["o"].sum() / a["s"].sum() - b["o"].sum() / b["s"].sum()) * 100))


@value_metric(
    P + "piotroski_fraction",
    "ratio",
    ["fundamentals.annual_pl", "fundamentals.balance_sheet", "fundamentals.cash_flow"],
)
def piotroski_fraction(v: VCalc) -> Measure:
    """Share of the Piotroski F-score checks that pass, among those computable from the export.

    Formula:   passed ÷ computable over: ROA > 0, CFO > 0, ROA up, CFO > profit, leverage down, no dilution, asset turnover up
    Meaning:   Nine binary quality checks (≥ 7 of 9 good, ≤ 3 poor); two need data the export lacks.
    Pitfalls:  Current-ratio and gross-margin checks are not computable, so the denominator is 7 at most.
    Source:    Screener export; plan 01 §2.2
    """
    npf, ta = v.ann("annual_pl", "Net profit"), v.ann("balance_sheet", "Total Assets")
    cfo, borr = (
        v.ann("cash_flow", "Cash from Operating Activity"),
        v.ann("balance_sheet", "Borrowings"),
    )
    sales = v.ann("annual_pl", "Sales")
    shares = v.f.annual("derived", "Adjusted Equity Shares in Cr")
    d = pd.concat(
        [npf, ta, cfo, borr, sales, shares], axis=1, keys=["np", "ta", "cfo", "b", "s", "sh"]
    ).dropna()
    if len(d) < 2:
        return _na("fewer than two years of data")
    cur, prev = d.iloc[-1], d.iloc[-2]
    checks = [
        cur["np"] / cur["ta"] > 0,
        cur["cfo"] > 0,
        cur["np"] / cur["ta"] > prev["np"] / prev["ta"],
        cur["cfo"] > cur["np"],
        cur["b"] / cur["ta"] <= prev["b"] / prev["ta"],
        cur["sh"] <= prev["sh"] * 1.005,
        cur["s"] / cur["ta"] > prev["s"] / prev["ta"],
    ]
    return Measure(float(sum(bool(c) for c in checks) / len(checks)))


@value_metric(P + "other_income_share", "ratio", ["fundamentals.annual_pl"])
def other_income_share(v: VCalc) -> Measure:
    """Other income as a share of profit before tax (a flag above 25% for non-financials).

    Formula:   other income ÷ PBT, latest year
    Meaning:   Profit inflated by treasury income or one-offs.
    Pitfalls:  Meaningless when PBT is near zero; N/A then.
    Source:    Screener export; plan 01 §2.7
    """
    oi, pbt = v.ann("annual_pl", "Other Income"), v.ann("annual_pl", "Profit before tax")
    if not len(oi) or not len(pbt) or pbt.iloc[-1] <= 0:
        return _na("other income or positive PBT unavailable")
    return Measure(float(oi.iloc[-1] / pbt.iloc[-1]))


@value_metric(
    P + "debtor_days_change", "ratio", ["fundamentals.balance_sheet", "fundamentals.annual_pl"]
)
def debtor_days_change(v: VCalc) -> Measure:
    """Year-on-year change in debtor days (receivables ÷ sales × 365).

    Formula:   debtor days_t ÷ debtor days_t-1 − 1
    Meaning:   Rising debtor days without matching growth is the commonest early warning in mid and small caps.
    Pitfalls:  Year-end receivables; needs two years.
    Source:    Screener export; plan 01 §2.7
    """
    r, s = v.ann("balance_sheet", "Receivables"), v.ann("annual_pl", "Sales")
    d = pd.concat([r, s], axis=1, keys=["r", "s"]).dropna()
    d = d[d["s"] > 0]
    if len(d) < 2:
        return _na("fewer than two years of receivables and sales")
    days = d["r"] / d["s"] * 365
    return (
        Measure(float(days.iloc[-1] / days.iloc[-2] - 1))
        if days.iloc[-2] > 0
        else _na("prior debtor days zero")
    )


# -- balance sheet ---------------------------------------------------------------------------
@value_metric(P + "debt_equity", "x", ["fundamentals.balance_sheet"])
def debt_equity(v: VCalc) -> Measure:
    """Borrowings divided by net worth.

    Formula:   borrowings ÷ (equity + reserves)
    Meaning:   Leverage; thresholds are 1.0 / 0.8 / 0.5 for large / mid / small.
    Pitfalls:  Not for banks or NBFCs; lease liabilities are excluded (airlines use lease-adjusted leverage).
    Source:    Screener export; plan 01 §2.3
    """
    b, nw = v.ann("balance_sheet", "Borrowings"), v.net_worth()
    if not len(b) or not len(nw) or nw.iloc[-1] <= 0:
        return _na("borrowings or positive net worth unavailable")
    return Measure(float(b.iloc[-1] / nw.iloc[-1]))


@value_metric(P + "interest_coverage", "x", ["fundamentals.annual_pl"])
def interest_coverage(v: VCalc) -> Measure:
    """Operating earnings divided by interest cost.

    Formula:   (PBT + interest) ÷ interest, latest year (capped at 50 when interest is negligible)
    Meaning:   Serviceability of debt; 4× or better is comfortable.
    Pitfalls:  Not for brokers (client-money borrowings are operating) or financials.
    Source:    Screener export; plan 01 §2.3
    """
    pbt, intr = v.ann("annual_pl", "Profit before tax"), v.ann("annual_pl", "Interest")
    if not len(pbt) or not len(intr):
        return _na("PBT or interest unavailable")
    if intr.iloc[-1] <= 0.01 * abs(pbt.iloc[-1] + intr.iloc[-1]):
        return Measure(50.0)
    return Measure(float(min(50.0, (pbt.iloc[-1] + intr.iloc[-1]) / intr.iloc[-1])))


@value_metric(P + "net_cash_to_mcap", "ratio", ["prices.close", "fundamentals.balance_sheet"])
def net_cash_to_mcap(v: VCalc) -> Measure:
    """Net cash (cash − borrowings) as a share of market cap.

    Formula:   (cash & bank − borrowings) ÷ market cap
    Meaning:   Downside cushion; above 20% with no payout is a capital-allocation question.
    Pitfalls:  Cash & bank excludes treasury investments held elsewhere on the balance sheet.
    Source:    prices; Screener export; plan 01 §2.7
    """
    nd, mc = v.net_debt_cr(), v.mcap_cr
    if nd is None or mc is None:
        return _na("net debt or market cap unavailable")
    return Measure(-nd / mc)


@value_metric(
    P + "lease_adj_leverage",
    "x",
    ["fundamentals.balance_sheet", "profile_inputs.lease_liabilities_cr"],
)
def lease_adj_leverage(v: VCalc) -> Measure:
    """Airlines: lease-adjusted net debt divided by EBITDAR.

    Formula:   (borrowings + lease liabilities − cash) ÷ (TTM operating profit + lease cost)
    Meaning:   Leverage that counts leases; raw D/E fails every airline (AC-F04.10).
    Pitfalls:  Needs lease inputs from filings; a flag above 4× is a starting point.
    Source:    Screener export; filings (analyst input); plan 01 §3
    """
    lease, cost = v.inputs_value("lease_liabilities_cr"), v.inputs_value("lease_cost_cr")
    nd, op = v.net_debt_cr(), v.f.ttm("Operating Profit")
    if lease.value is None or cost.value is None:
        return _na(lease.reason or cost.reason or "lease inputs missing")
    if nd is None or op is None:
        return _na("net debt or operating profit unavailable")
    ebitdar = op + cost.value
    return Measure((nd + lease.value) / ebitdar) if ebitdar > 0 else _na("EBITDAR not positive")


@value_metric(P + "standalone_debt_equity", "x", ["profile_inputs.standalone_net_debt_cr"])
def standalone_debt_equity(v: VCalc) -> Measure:
    """Conglomerates: the standalone core business's net debt divided by its equity.

    Formula:   standalone net debt ÷ standalone equity
    Meaning:   A lending subsidiary's borrowings distort consolidated leverage; score the core standalone (AC-F04.11).
    Pitfalls:  Needs standalone figures from filings (profile_inputs.yaml).
    Source:    standalone results (analyst input); plan 01 §3
    """
    nd, eq = v.inputs_value("standalone_net_debt_cr"), v.inputs_value("standalone_equity_cr")
    if nd.value is None or eq.value is None:
        return _na(nd.reason or eq.reason or "standalone inputs missing")
    return Measure(nd.value / eq.value) if eq.value > 0 else _na("standalone equity not positive")


@value_metric(
    P + "cash_runway_months", "count", ["fundamentals.balance_sheet", "fundamentals.cash_flow"]
)
def cash_runway_months(v: VCalc) -> Measure:
    """New-age companies: months of cash left at the latest year's free-cash-flow burn.

    Formula:   net cash ÷ (monthly free-cash-flow burn); 999 when the company is not burning cash
    Meaning:   Below 24 months turns the negative-CFO flag into a veto (AC-F04.12).
    Pitfalls:  Annual burn from the export (CFO − capex proxy); net cash excludes treasury investments.
    Source:    Screener export; plan 01 §3
    """
    fcf, nd = v.fcf_annual(), v.net_debt_cr()
    if not len(fcf) or nd is None:
        return _na("free cash flow or net debt unavailable")
    last = float(fcf.iloc[-1])
    if last >= 0:
        return Measure(999.0)
    net_cash = -nd
    if net_cash <= 0:
        return Measure(0.0)
    return Measure(float(net_cash / (-last / 12)))


@value_metric(
    P + "net_cash_ex_advances_to_mcap",
    "ratio",
    ["prices.close", "profile_inputs.customer_advances_cr"],
)
def net_cash_ex_advances_to_mcap(v: VCalc) -> Measure:
    """Order-book businesses: net cash less customer advances, as a share of market cap.

    Formula:   (cash − borrowings − customer advances) ÷ market cap
    Meaning:   Customer advances are not free cash.
    Pitfalls:  Needs advances from filings (profile_inputs.yaml).
    Source:    Screener export; filings (analyst input); plan 01 §3
    """
    adv, nd, mc = v.inputs_value("customer_advances_cr"), v.net_debt_cr(), v.mcap_cr
    if adv.value is None:
        return _na(adv.reason or "advances missing")
    if nd is None or mc is None:
        return _na("net debt or market cap unavailable")
    return Measure((-nd - adv.value) / mc)


def _input_metric(ident: str, key: str, unit: str, meaning: str, source: str) -> None:
    def fn(v: VCalc) -> Measure:
        return v.inputs_value(key)

    fn.__doc__ = (
        f"{meaning}\n\nFormula:   as filed or supplied (profile_inputs.yaml: {key})\n"
        f"Meaning:   {meaning}\nPitfalls:  N/A until supplied; never estimated.\nSource:    {source}\n"
    )
    value_metric(ident, unit, [f"profile_inputs.{key}"])(fn)


for _id, _key, _unit, _meaning, _src in [
    (
        P + "gnpa",
        "gnpa_ratio",
        "ratio",
        "Gross NPA ratio of a bank or NBFC.",
        "RBI filings; plan 01 §3",
    ),
    (
        P + "nnpa",
        "nnpa_ratio",
        "ratio",
        "Net NPA ratio of a bank or NBFC.",
        "RBI filings; plan 01 §3",
    ),
    (P + "nim", "nim_ratio", "ratio", "Net interest margin of a bank.", "bank filings; plan 01 §3"),
    (
        P + "car",
        "car_ratio",
        "ratio",
        "Capital adequacy ratio of a bank.",
        "bank filings; plan 01 §3",
    ),
    (
        P + "casa",
        "casa_ratio",
        "ratio",
        "CASA share of a bank's deposits.",
        "bank filings; plan 01 §3",
    ),
    (
        P + "cost_to_income",
        "cost_to_income_ratio",
        "ratio",
        "Cost-to-income ratio of a capital-market intermediary.",
        "filings; plan 01 §3",
    ),
    (
        P + "order_cover",
        "order_cover_x",
        "x",
        "Order book divided by trailing revenue.",
        "investor presentations; plan 01 §3",
    ),
]:
    _input_metric(_id, _key, _unit, _meaning, _src)


# -- growth ----------------------------------------------------------------------------------
def _cagr_series(s: pd.Series, years: int, v: VCalc) -> Measure:
    if v.inp.history_break is not None:
        s = s[s.index >= v.inp.history_break]
    s = s.dropna()
    if len(s) < years + 1:
        reason = f"{len(s)} comparable years; needs {years + 1}"
        if v.inp.history_break is not None:
            reason += f" (history restarts at the {v.inp.history_break:%b %Y} {v.inp.history_break_reason})"
        return _na(reason)
    r = iv.cagr(float(s.iloc[-1 - years]), float(s.iloc[-1]), years)
    return Measure(r) if r is not None else _na("growth base is not positive")


@value_metric(P + "revenue_cagr_3y", "ratio", ["fundamentals.annual_pl"])
def revenue_cagr_3y(v: VCalc) -> Measure:
    """Three-year compound annual revenue growth.

    Formula:   (sales_t ÷ sales_t-3)^(1/3) − 1
    Meaning:   Medium-term top-line momentum.
    Pitfalls:  Windows that cross a recorded merger break (e.g. HDFC Bank, July 2023) are cut at the break.
    Source:    Screener export; plan 01 §2.4
    """
    return _cagr_series(v.ann("annual_pl", "Sales"), 3, v)


@value_metric(P + "revenue_cagr_5y", "ratio", ["fundamentals.annual_pl"])
def revenue_cagr_5y(v: VCalc) -> Measure:
    """Five-year compound annual revenue growth.

    Formula:   (sales_t ÷ sales_t-5)^(1/5) − 1
    Meaning:   Longer-term top-line growth.
    Pitfalls:  Windows that cross a recorded merger break are cut at the break.
    Source:    Screener export; plan 01 §2.4
    """
    return _cagr_series(v.ann("annual_pl", "Sales"), 5, v)


@value_metric(P + "eps_cagr_3y", "ratio", ["fundamentals.annual_pl"])
def eps_cagr_3y(v: VCalc) -> Measure:
    """Three-year compound annual EPS growth.

    Formula:   (EPS_t ÷ EPS_t-3)^(1/3) − 1, EPS = net profit ÷ adjusted shares
    Meaning:   The growth denominator of PEG.
    Pitfalls:  N/A when either end is a loss; cut at a recorded merger break.
    Source:    Screener export; plan 01 §2.4
    """
    return _cagr_series(v.eps_annual(), 3, v)


@value_metric(P + "eps_cagr_5y", "ratio", ["fundamentals.annual_pl"])
def eps_cagr_5y(v: VCalc) -> Measure:
    """Five-year compound annual EPS growth.

    Formula:   (EPS_t ÷ EPS_t-5)^(1/5) − 1
    Meaning:   Longer-term earnings growth; also the starting point of the DCF growth input.
    Pitfalls:  N/A when either end is a loss; cut at a recorded merger break.
    Source:    Screener export; plan 01 §2.4
    """
    return _cagr_series(v.eps_annual(), 5, v)


@value_metric(P + "growth_consistency", "ratio", ["fundamentals.annual_pl"])
def growth_consistency(v: VCalc) -> Measure:
    """Share of the last five years with positive revenue growth.

    Formula:   count of years with sales up on the prior year ÷ years compared (up to 5)
    Meaning:   Steady growers earn a higher growth score than lumpy ones.
    Pitfalls:  Needs at least three comparisons.
    Source:    Screener export; plan 01 §2.4
    """
    s = v.ann("annual_pl", "Sales", post_break=True).dropna()
    ch = s.diff().dropna().iloc[-5:]
    if len(ch) < 3:
        return _na(f"{len(ch)} year-on-year comparisons; needs 3")
    return Measure(float((ch > 0).mean()))


@value_metric(P + "revenue_growth_1y", "ratio", ["fundamentals.annual_pl"])
def revenue_growth_1y(v: VCalc) -> Measure:
    """Latest fiscal year's revenue growth.

    Formula:   sales_t ÷ sales_t-1 − 1
    Meaning:   Growth for companies too young for a CAGR.
    Pitfalls:  One year only; pre-listing years count as filed in the offer document.
    Source:    Screener export; plan 01 §3
    """
    s = v.ann("annual_pl", "Sales").dropna()
    if len(s) < 2 or s.iloc[-2] <= 0:
        return _na("fewer than two years of sales")
    return Measure(float(s.iloc[-1] / s.iloc[-2] - 1))


@value_metric(P + "eps_vs_revenue_gap", "ratio", ["fundamentals.annual_pl"])
def eps_vs_revenue_gap(v: VCalc) -> Measure:
    """Three-year EPS CAGR minus three-year revenue CAGR (earnings-quality flag).

    Formula:   EPS CAGR 3y − revenue CAGR 3y
    Meaning:   EPS growth well above revenue growth for years rests on margin expansion that cannot continue.
    Pitfalls:  Informational; the flag threshold is in config.
    Source:    Screener export; plan 01 §2.4
    """
    e, r = eps_cagr_3y(v), revenue_cagr_3y(v)
    if e.value is None or r.value is None:
        return _na(e.reason or r.reason or "unavailable")
    return Measure(e.value - r.value)


# -- governance ------------------------------------------------------------------------------
def _sh(v: VCalc, col: str) -> list[float]:
    return [float(r[col]) for r in v.shareholding_sorted() if r.get(col) is not None]


@value_metric(P + "promoter_holding", "ratio", ["shareholding.promoter_pct"])
def promoter_holding(v: VCalc) -> Measure:
    """Promoter holding at the latest filed quarter, as a fraction.

    Formula:   promoter shares ÷ total shares (percent ÷ 100)
    Meaning:   Skin in the game.
    Pitfalls:  Professionally-run companies with no promoter show zero; read with the trend.
    Source:    exchange shareholding filings; plan 01 §2.5
    """
    x = _sh(v, "promoter_pct")
    return Measure(x[-1] / 100) if x else _na("no shareholding filing visible at the as-of date")


@value_metric(P + "promoter_trend_pp", "score", ["shareholding.promoter_pct"])
def promoter_trend_pp(v: VCalc) -> Measure:
    """Change in promoter holding over the last four quarters, in percentage points.

    Formula:   promoter % now − promoter % four quarters ago
    Meaning:   Steady selling is a warning; a fall of more than 3 points in a year costs points.
    Pitfalls:  Needs five quarters of filings.
    Source:    exchange shareholding filings; plan 01 §2.5
    """
    x = _sh(v, "promoter_pct")
    return Measure(x[-1] - x[-5]) if len(x) >= 5 else _na(f"{len(x)} filings; needs 5")


@value_metric(P + "pledge_pct", "ratio", ["shareholding.pledge_pct"])
def pledge_pct(v: VCalc) -> Measure:
    """Promoter shares pledged, as a fraction of the promoter holding.

    Formula:   pledged promoter shares ÷ promoter shares
    Meaning:   Forced-selling risk; above the cap limit is a veto.
    Pitfalls:  ❔ unknown is not 0%: with no filing the check is UNKNOWN, never clean (UX-05).
    Source:    exchange shareholding filings; plan 01 §2.5
    """
    x = _sh(v, "pledge_pct")
    return Measure(x[-1] / 100) if x else _na("no shareholding filing visible at the as-of date")


@value_metric(P + "fii_trend_pp", "score", ["shareholding.fii_pct"])
def fii_trend_pp(v: VCalc) -> Measure:
    """Change in FII holding over the last two quarters, in percentage points.

    Formula:   FII % now − FII % two quarters ago
    Meaning:   Institutional conviction; rising for two quarters is a positive.
    Pitfalls:  Needs three filings with FII data.
    Source:    exchange shareholding filings; plan 01 §2.5
    """
    x = _sh(v, "fii_pct")
    return (
        Measure(x[-1] - x[-3]) if len(x) >= 3 else _na(f"{len(x)} filings with FII data; needs 3")
    )


@value_metric(P + "dii_trend_pp", "score", ["shareholding.dii_pct"])
def dii_trend_pp(v: VCalc) -> Measure:
    """Change in DII holding over the last two quarters, in percentage points.

    Formula:   DII % now − DII % two quarters ago
    Meaning:   Domestic institutional conviction.
    Pitfalls:  Needs three filings with DII data.
    Source:    exchange shareholding filings; plan 01 §2.5
    """
    x = _sh(v, "dii_pct")
    return (
        Measure(x[-1] - x[-3]) if len(x) >= 3 else _na(f"{len(x)} filings with DII data; needs 3")
    )


@value_metric(P + "dilution_3y", "ratio", ["fundamentals.balance_sheet"])
def dilution_3y(v: VCalc) -> Measure:
    """Annual growth in the adjusted share count over three years.

    Formula:   (shares_t ÷ shares_t-3)^(1/3) − 1
    Meaning:   Dilution quietly erodes per-share value; a flag above 3% a year.
    Pitfalls:  Uses the export's adjusted share count, so splits and bonuses do not register.
    Source:    Screener export; plan 01 §2.7
    """
    s = v.f.annual("derived", "Adjusted Equity Shares in Cr")
    if len(s) < 4:
        return _na(f"{len(s)} years of share counts; needs 4")
    return Measure(float((s.iloc[-1] / s.iloc[-4]) ** (1 / 3) - 1))


def compute_all(v: VCalc) -> tuple[dict[str, float | None], dict[str, str]]:
    """Every value metric for this stock: (values, N/A reasons)."""
    values: dict[str, float | None] = {}
    reasons: dict[str, str] = {}
    for ident, fn in VALUE_METRICS.items():
        try:
            m = fn(v)
        except (
            ZeroDivisionError,
            KeyError,
            IndexError,
            ValueError,
        ) as exc:  # a metric must never kill a run
            m = Measure.na(f"calculation failed: {type(exc).__name__}")
        values[ident] = None if m.value is None or not np.isfinite(m.value) else m.value
        if values[ident] is None:
            reasons[ident] = m.reason or "not available"
    return values, reasons
