"""Position context per stock: cost, P&L, weight, days to long-term status, tax if sold now.

Built from tax lots (plan 05 §2.4, §4; AC-F03.3, AC-F03.6). Rules:

- A lot with no price is *cost pending*: the position's average cost, P&L, tax estimate and
  LTCG timer then show "cost pending", never a guessed cost (AC-F03.6).
- Long term means held more than `tax.long_term_days` (365) days from the trade date.
- The tax estimate is per stock and *before* the yearly LTCG exemption and any loss set-off,
  which depend on your other gains; it says so.
- Weight is the share of the market value of the holdings that have a price loaded. In pilot
  mode that is the pilot holdings only, and the position records that basis.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from collections.abc import Iterable

from pydantic import BaseModel

from parakh.configs.lens_models import TaxRates
from parakh.holdings.lots import Lot
from parakh.holdings.xirr import benchmark_xirr, xirr


class PositionInfo(BaseModel):
    isin: str
    quantity: float
    avg_cost_inr: float | None
    cost_pending: bool
    invested_inr: float | None
    market_value_inr: float
    pnl_inr: float | None
    pnl_pct: float | None
    weight_pct: float | None
    weight_basis: str
    lots: int
    lots_long_term: int
    qty_long_term: float
    days_to_long_term: int  # until the next short-term lot turns long term; 0 when all are
    tax_if_sold_now_inr: float | None
    tax_note: str
    xirr_pct: float | None = None  # annualised return on the lots; None when a cost is pending
    benchmark_xirr_pct: float | None = None  # same rupees in the cap benchmark on the same days


def _tax(lots: list[Lot], close: float, asof: dt.date, rates: TaxRates) -> float | None:
    short = long = 0.0
    for lot in lots:
        if lot.price_inr is None:
            return None
        gain = (close - lot.price_inr) * lot.qty
        if (asof - lot.trade_date).days > rates.long_term_days:
            long += gain
        else:
            short += gain
    raw = max(short, 0.0) * rates.stcg_pct / 100 + max(long, 0.0) * rates.ltcg_pct / 100
    return raw * (1 + rates.cess_pct / 100)


def positions_from_lots(
    lots: Iterable[Lot],
    closes: dict[str, float],
    asof: dt.date,
    rates: TaxRates,
    weight_basis: str = "holdings with a loaded price",
    cap_of: dict[str, str] | None = None,
    bench_series: dict[str, dict[dt.date, float]] | None = None,
) -> dict[str, PositionInfo]:
    by_isin: dict[str, list[Lot]] = defaultdict(list)
    for lot in lots:
        if lot.qty > 0 and lot.isin in closes:
            by_isin[lot.isin].append(lot)
    total_mv = sum(sum(x.qty for x in ls) * closes[i] for i, ls in by_isin.items())
    out: dict[str, PositionInfo] = {}
    for isin, ls in by_isin.items():
        qty = sum(x.qty for x in ls)
        close = closes[isin]
        mv = qty * close
        pending = any(x.price_inr is None for x in ls)
        invested = None if pending else sum(x.qty * (x.price_inr or 0.0) for x in ls)
        long_lots = [x for x in ls if (asof - x.trade_date).days > rates.long_term_days]
        short_lots = [x for x in ls if x not in long_lots]
        days_left = (
            min(rates.long_term_days + 1 - (asof - x.trade_date).days for x in short_lots)
            if short_lots
            else 0
        )
        tax = _tax(ls, close, asof, rates)
        rate: float | None = None
        bench_rate: float | None = None
        if not pending:
            buys = [(x.trade_date, x.qty * (x.price_inr or 0.0)) for x in ls]
            rate = xirr([*((d, -a) for d, a in buys), (asof, mv)])
            series = (bench_series or {}).get((cap_of or {}).get(isin, ""))
            if series:
                bench_rate = benchmark_xirr(buys, series, asof)
        out[isin] = PositionInfo(
            isin=isin,
            quantity=qty,
            avg_cost_inr=None if invested is None else invested / qty,
            cost_pending=pending,
            invested_inr=invested,
            market_value_inr=mv,
            pnl_inr=None if invested is None else mv - invested,
            pnl_pct=None if not invested else (mv / invested - 1) * 100,
            weight_pct=mv / total_mv * 100 if total_mv else None,
            weight_basis=weight_basis,
            lots=len(ls),
            lots_long_term=len(long_lots),
            qty_long_term=sum(x.qty for x in long_lots),
            days_to_long_term=days_left,
            tax_if_sold_now_inr=tax,
            tax_note=(
                "cost pending: tax cannot be estimated"
                if tax is None
                else "estimate before the yearly LTCG exemption and loss set-offs"
            ),
            xirr_pct=None if rate is None else rate * 100,
            benchmark_xirr_pct=None if bench_rate is None else bench_rate * 100,
        )
    return out
