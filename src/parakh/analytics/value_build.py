"""Builds the value lens's inputs: metrics, intrinsic value, checks that could not run. No I/O."""

from __future__ import annotations

import datetime as dt
import statistics
from typing import Any

import pandas as pd

from parakh.analytics import intrinsic as iv
from parakh.analytics.fundamentals_view import Fundamentals
from parakh.analytics.metrics.value import compute_all, sotp_value
from parakh.analytics.momentum_calc import Measure
from parakh.analytics.value_calc import ValueInputs, VCalc
from parakh.configs.lens_models import ValueConfig

# Checks plan 01 lists that no loaded source can run yet. They are shown as ❔ UNKNOWN with the
# reason, never as clean (UX-05), and the veto list names them so nothing is silently skipped.
UNKNOWN_CHECKS = {
    "auditor qualification or resignation": "auditor and KMP events are not loaded until the Phase 3 event watcher",
    "exchange surveillance (ASM/GSM)": "surveillance lists are not loaded until Phase 3",
    "Altman Z-score": "current assets and liabilities are not in the Screener export",
    "Beneish M-score": "receivables, depreciation and SG&A detail are not in the export",
    "related-party transactions": "not in the export; needs the annual report",
    "contingent liabilities vs net worth": "not in the export; needs the annual report",
    "credit rating actions": "rating feed not loaded until Phase 3",
    "promoter insider buying and selling": "insider-trading disclosures not loaded until Phase 3",
    "MF scheme count": "AMFI monthly holdings not loaded",
}


def build_inputs(
    isin: str,
    symbol: str,
    cap: str,
    profile: str,
    asof: dt.date,
    price: float | None,
    fundamentals_rows: list[dict[str, Any]],
    cfg: ValueConfig,
    shareholding_rows: list[dict[str, Any]] | None = None,
    listed_on: dt.date | None = None,
    profile_inputs: dict[str, float | None] | None = None,
    input_reasons: dict[str, str] | None = None,
    stakes: list[dict[str, Any]] | None = None,
    excess_return_12m: float | None = None,
    index_pe_percentile: float | None = None,
) -> ValueInputs:
    brk = next((b for b in cfg.history_breaks if b.isin == isin), None)
    return ValueInputs(
        isin=isin,
        symbol=symbol,
        cap=cap,
        profile=profile,
        asof=asof,
        price=price,
        fundamentals=Fundamentals(fundamentals_rows),
        shareholding=shareholding_rows or [],
        listed_on=listed_on,
        profile_inputs=profile_inputs or {},
        input_reasons=input_reasons or {},
        stakes=stakes or [],
        excess_return_12m=excess_return_12m,
        index_pe_percentile=index_pe_percentile,
        history_break=brk.break_on if brk else None,
        history_break_reason=brk.reason if brk else "",
    )


def _median_pe(v: VCalc) -> float | None:
    hist = v.pe_history()
    for n in (5, 3):
        tail = hist.iloc[-n:]
        if len(tail) >= 3 and v.own_history_gate(n) is None:
            return float(statistics.median(tail.tolist()))
    return None


def _median_pb(v: VCalc) -> float | None:
    hist = v.pb_history().iloc[-5:]
    if len(hist) >= 3 and v.own_history_gate(5) is None:
        return float(statistics.median(hist.tolist()))
    return None


def intrinsic_block(v: VCalc, values: dict[str, float | None]) -> dict[str, Any]:
    """Per-share values by method, the implied growth and the probability-weighted return."""
    d = v.cfg.dcf
    methods: dict[str, float] = {}
    notes: dict[str, str] = {}
    price = v.inp.price
    eps, bvps = v.eps_ttm(), v.bvps()
    spec = v.cfg.profiles[v.inp.profile]  # type: ignore[index]
    conv = values.get("MET.value.cfo_to_pat_3y")
    g5, g3 = values.get("MET.value.eps_cagr_5y"), values.get("MET.value.eps_cagr_3y")
    hist_g = g5 if g5 is not None else g3
    base_g = None if hist_g is None else max(0.0, min(hist_g, d.growth_cap))
    med_pe, med_pb = _median_pe(v), _median_pb(v)
    cf0 = eps * min(1.0, max(0.3, conv)) if eps and eps > 0 and conv is not None else None

    for m in spec.intrinsic_methods:
        if m == "reverse_dcf":
            continue  # a check, not a value: reported below
        out: float | None = None
        if m == "dcf_2stage":
            if cf0 is None or base_g is None:
                notes[m] = "needs positive EPS, cash conversion and an EPS growth history"
            else:
                out = iv.dcf_value(
                    cf0, base_g, d.cost_of_equity, d.terminal_growth, d.explicit_years, d.fade_years
                )
        elif m == "hist_multiple":
            if eps is None or eps <= 0 or med_pe is None:
                notes[m] = "needs positive EPS and an own-history median P/E"
            else:
                out = med_pe * eps
        elif m == "hist_multiple_normalised":
            avg = v.eps_annual().iloc[-10:]
            if med_pe is None or len(avg) < 5 or avg.mean() <= 0:
                notes[m] = "needs five years of EPS and an own-history median P/E"
            else:
                out = med_pe * float(avg.mean())
        elif m == "graham":
            out = (
                iv.graham_number(eps, bvps, d.graham_multiplier)
                if eps is not None and bvps is not None
                else None
            )
            if out is None:
                notes[m] = "needs positive EPS and book value"
        elif m == "hist_pb":
            if bvps is None or med_pb is None:
                notes[m] = "needs book value and an own-history median P/B"
            else:
                out = med_pb * bvps
        elif m == "justified_pb":
            roe = values.get("MET.value.roe_5y_avg")
            if bvps is None or roe is None:
                notes[m] = "needs book value and 5-year ROE"
            else:
                out = roe / d.cost_of_equity * bvps
        elif m == "sotp":
            sh = v.shares_cr
            mid = sotp_value(v)
            if mid.value is None or not sh:
                notes[m] = mid.reason or "needs shares"
            else:
                methods["sotp_low"] = sotp_value(v, d.holdco_discount_range[1]).value / sh  # type: ignore[operator]
                methods["sotp_high"] = sotp_value(v, d.holdco_discount_range[0]).value / sh  # type: ignore[operator]
                out = mid.value / sh
        if out is not None and out > 0:
            methods[m] = float(out)

    sotp_aux = {k: methods.pop(k) for k in ("sotp_low", "sotp_high") if k in methods}
    vals = sorted(methods.values()) + sorted(sotp_aux.values())
    block: dict[str, Any] = {"methods": methods, "notes": notes, "sotp_range": sotp_aux}
    if vals:
        block |= {
            "low": min(vals),
            "high": max(vals),
            "mid": statistics.median(sorted(methods.values()))
            if methods
            else statistics.median(vals),
            "single_method": len(methods) <= 1 and not sotp_aux,
        }
    # Reverse DCF: what growth does the price assume, against what has been delivered?
    ig = None
    if price and cf0 and v.inp.profile not in ("bank", "nbfc", "insurance"):
        ig = iv.implied_growth(
            price,
            cf0,
            d.cost_of_equity,
            d.terminal_growth,
            d.explicit_years,
            d.fade_years,
            d.reverse_dcf_max_growth,
        )
    block["implied_growth_reverse_dcf"] = ig
    block["delivered_growth"] = hist_g
    # Probability-weighted expected return against the hurdle (plan 01 §11 #2).
    if price and eps and eps > 0 and base_g is not None and med_pe is not None:
        div = values.get("MET.value.dividend_yield") or 0.0
        rows = {}
        total_p = 0.0
        exp = 0.0
        for name, s in d.scenarios.items():
            r = iv.expected_irr(
                price, eps, base_g * s.growth_mult, med_pe * s.exit_pe_mult, d.irr_years, div
            )
            if r is not None:
                rows[name] = r
                exp += r * s.probability
                total_p += s.probability
        if rows and total_p > 0:
            block["expected_irr"] = {
                "scenarios": rows,
                "weighted": exp / total_p,
                "hurdle": d.hurdle_rate,
            }
    return block


def archetype(v: VCalc, values: dict[str, float | None]) -> str:
    a = v.cfg.archetype
    eps = v.eps_annual().iloc[-2:]
    if len(eps) and (eps <= 0).any():
        return "Turnaround"
    if v.inp.profile in ("cyclical", "airline_lease_heavy"):
        return "Cyclical"
    g = values.get("MET.value.eps_cagr_5y") or values.get("MET.value.eps_cagr_3y")
    pbv = values.get("MET.value.pb")
    nc = values.get("MET.value.net_cash_to_mcap")
    if pbv is not None and pbv < a.asset_play_max_pb and nc is not None and nc > 0:
        return "Asset play"
    if g is None:
        return "Unclassified"
    if g >= a.fast_grower_min_eps_cagr:
        return "Fast grower"
    if g <= a.slow_grower_max_eps_cagr:
        return "Slow grower"
    return "Stalwart"


def cfo_negative_years(v: VCalc) -> tuple[int, int]:
    cfo = v.ann("cash_flow", "Cash from Operating Activity").dropna().iloc[-5:]
    return int((cfo < 0).sum()), len(cfo)


def value_context_parts(
    inp: ValueInputs, cfg: ValueConfig
) -> tuple[dict[str, float | None], dict[str, str], dict[str, Any]]:
    v = VCalc(inp, cfg)
    values, reasons = compute_all(v)
    neg, n = cfo_negative_years(v)
    block = intrinsic_block(v, values)
    f = inp.fundamentals
    sh = v.shareholding_sorted()
    extras: dict[str, Any] = {
        "price": inp.price,
        "mcap_cr": v.mcap_cr,
        "shares_cr": v.shares_cr,
        "history_class": v.history_class,
        "months_listed": v.months_listed,
        "profile": inp.profile,
        "intrinsic": block,
        "archetype": archetype(v, values),
        "cfo_negative_years": neg,
        "cfo_years": n,
        "unknown_checks": [{"check": k, "reason": r} for k, r in UNKNOWN_CHECKS.items()],
        "excess_return_12m": inp.excess_return_12m,
        "index_pe_percentile": inp.index_pe_percentile,
        "history_break": inp.history_break.isoformat() if inp.history_break else None,
        "history_break_reason": inp.history_break_reason,
        "asof": {
            "fundamentals_annual": f.last_annual.isoformat() if f.last_annual else None,
            "fundamentals_quarter": f.last_quarter.isoformat() if f.last_quarter else None,
            "shareholding": sh[-1]["period_end"].isoformat()
            if sh and isinstance(sh[-1]["period_end"], dt.date)
            else (str(sh[-1]["period_end"]) if sh else None),
            "price": inp.asof.isoformat(),
        },
        "stakes": [
            {"name": s["name"], "stake": s["stake"], "mcap_cr": s.get("mcap_cr")}
            for s in inp.stakes
        ],
    }
    return values, reasons, extras


def earnings_accel_measure(f: Fundamentals) -> Measure:
    """Earnings momentum for the momentum lens: acceleration of YoY net-profit growth (pp)."""
    q = f.quarterly("quarterly_pl", "Net profit")
    if len(q) < 8:
        return Measure.na(f"{len(q)} quarters of results; needs 8")
    yoy = []
    for i in range(1, 5):
        cur, prev = q.iloc[-i], q.iloc[-i - 4]
        if prev <= 0:
            return Measure.na("year-ago quarter profit is not positive")
        yoy.append((cur / prev - 1) * 100)
    latest, rest = yoy[0], sum(yoy[1:]) / 3
    return Measure(float(latest - rest))


def price_on_or_before(prices: pd.DataFrame, asof: dt.date) -> float | None:
    f = prices.copy()
    f["trade_date"] = pd.to_datetime(f["trade_date"]).dt.date
    f = f[f["trade_date"] <= asof].sort_values("trade_date")
    return float(f["close"].iloc[-1]) if len(f) else None
