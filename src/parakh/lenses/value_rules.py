"""Value-lens vetoes (plan 01 §4, AC-F04.3). Registered so the catalogue lists them (RULES.md).

Each rule takes the lens inputs and returns True (veto), False (clear) or None (cannot be
checked: shown as ❔ UNKNOWN with its reason, never as clean, UX-05).
"""

from __future__ import annotations

from parakh.configs.lens_models import ValueConfig
from parakh.lenses.base import StockContext
from parakh.registry import register_rule


@register_rule(id="RULE.value.pledge_cap", kind="veto")
def pledge_cap(ctx: StockContext, cfg: ValueConfig) -> bool | None:
    """Promoter pledge above the cap's limit vetoes the stock.

    Formula:   pledged promoter shares ÷ promoter shares > 25% / 20% / 10% (large / mid / small)
    Meaning:   Forced selling risk when the price falls.
    Pitfalls:  No filing means UNKNOWN, not 0%.
    Source:    exchange shareholding filings; plan 01 §2.5
    """
    p = ctx.metrics.get("MET.value.pledge_pct")
    if p is None:
        return None
    return p > cfg.vetoes.pledge_pct[ctx.cap]  # type: ignore[index]


@register_rule(id="RULE.value.negative_cfo", kind="veto")
def negative_cfo(ctx: StockContext, cfg: ValueConfig) -> bool | None:
    """Negative operating cash flow in 3 of the last 5 years vetoes the stock.

    Formula:   count of years with CFO < 0 among the last five ≥ 3
    Meaning:   A business that does not generate cash from operations.
    Pitfalls:  For pre-profit companies this is a flag while cash runway is at least 24 months,
               and a veto below it (AC-F04.12). Not applied to banks.
    Source:    Screener export; plan 01 §4
    """
    n, years = ctx.extras.get("cfo_negative_years"), ctx.extras.get("cfo_years", 0)
    if n is None or years < 5:
        return None
    hit = n >= cfg.vetoes.negative_cfo_years_of_5
    if not hit:
        return False
    if ctx.profile == "new_age":
        runway = ctx.metrics.get("MET.value.cash_runway_months")
        if runway is None:
            return None
        return bool(runway < cfg.vetoes.runway_months_min)
    return True


@register_rule(id="RULE.value.nnpa_cap", kind="veto")
def nnpa_cap(ctx: StockContext, cfg: ValueConfig) -> bool | None:
    """Net NPA above the threshold vetoes a bank or NBFC.

    Formula:   net NPA ratio > threshold (config)
    Meaning:   Asset quality that threatens capital.
    Pitfalls:  Needs filed asset-quality data; UNKNOWN until supplied.
    Source:    bank filings; plan 01 §4
    """
    if ctx.profile not in ("bank", "nbfc"):
        return False
    n = ctx.metrics.get("MET.value.nnpa")
    return None if n is None else n > cfg.vetoes.nnpa_pct_max
