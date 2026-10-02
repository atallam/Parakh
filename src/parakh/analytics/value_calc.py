# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportReturnType=false, reportArgumentType=false, reportOperatorIssue=false, reportAssignmentType=false
# why: the pandas stubs infer ndarray/Series unions for indexing and sorting that are Series at run time; tests cover these paths
"""Value calculation context: point-in-time fundamentals, price, shareholding and profile inputs.

`VCalc` mirrors the momentum `Calc`: lazily computed, memoised measures, each either a value or
a reason it is missing. It does no I/O; `analytics.value_build` assembles its inputs.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from parakh.analytics.fundamentals_view import Fundamentals
from parakh.analytics.momentum_calc import Measure
from parakh.configs.lens_models import ValueConfig

__all__ = ["Measure", "ValueInputs", "VCalc"]


@dataclass
class ValueInputs:
    isin: str
    symbol: str
    cap: str
    profile: str
    asof: dt.date
    price: float | None  # latest close on or before the as-of date
    fundamentals: Fundamentals
    shareholding: list[dict[str, Any]] = field(default_factory=list)  # visible rows, any order
    listed_on: dt.date | None = None
    profile_inputs: dict[str, float | None] = field(default_factory=dict)  # analyst/filing inputs
    input_reasons: dict[str, str] = field(default_factory=dict)
    stakes: list[dict[str, Any]] = field(default_factory=list)  # {name, isin, stake, mcap_cr|None}
    excess_return_12m: float | None = None  # momentum context, for the value-trap detector
    index_pe_percentile: float | None = None  # market-level check (F16)
    history_break: dt.date | None = None  # a merger or demerger after which growth restarts
    history_break_reason: str = ""


@dataclass
class VCalc:
    inp: ValueInputs
    cfg: ValueConfig
    _cache: dict[str, Any] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)

    def memo[T](self, key: str, fn: Callable[[], T]) -> T:
        if key not in self._cache:
            self._cache[key] = fn()
        return self._cache[key]  # type: ignore[no-any-return]

    # -- listing history --------------------------------------------------------------------
    @property
    def months_listed(self) -> float | None:
        if self.inp.listed_on is None:
            return None
        return (self.inp.asof - self.inp.listed_on).days / 30.4375

    @property
    def history_class(self) -> str:
        m = self.months_listed
        h = self.cfg.history
        if m is None or m >= h.h2_min_months:
            return "H2"
        return "H1" if m >= h.h1_min_months else "H0"

    def own_history_gate(self, years: int) -> str | None:
        """Reason an own-history band can't be used yet, e.g. 'listed 11 months; needs 36'."""
        m = self.months_listed
        need = years * 12
        if m is not None and m < need:
            return f"listed {m:.0f} months; needs {need}"
        return None

    # -- fundamentals helpers -----------------------------------------------------------------
    @property
    def f(self) -> Fundamentals:
        return self.inp.fundamentals

    def ann(self, section: str, item: str, post_break: bool = False) -> pd.Series:
        since = self.inp.history_break if post_break else None
        return self.f.annual(section, item, since)

    @property
    def shares_cr(self) -> float | None:
        s = self.f.annual("derived", "Adjusted Equity Shares in Cr")
        if len(s):
            return float(s.iloc[-1])
        n = self.f.annual("balance_sheet", "No. of Equity Shares")
        return float(n.iloc[-1]) / 1e7 if len(n) else None

    @property
    def mcap_cr(self) -> float | None:
        if self.inp.price is None or self.shares_cr is None:
            return None
        return self.inp.price * self.shares_cr

    def net_worth(self) -> pd.Series:
        eq = self.ann("balance_sheet", "Equity Share Capital")
        res = self.ann("balance_sheet", "Reserves")
        return (eq + res).dropna()

    def eps_annual(self) -> pd.Series:
        """Annual EPS in ₹ = net profit ÷ that year's adjusted shares (both from the export)."""
        np_ = self.ann("annual_pl", "Net profit")
        sh = self.f.annual("derived", "Adjusted Equity Shares in Cr")
        return (np_ / sh).dropna()

    def eps_ttm(self) -> float | None:
        np_ttm, sh = self.f.ttm("Net profit"), self.shares_cr
        if np_ttm is None or not sh:
            return None
        return np_ttm / sh

    def bvps(self) -> float | None:
        nw, sh = self.net_worth(), self.shares_cr
        if not len(nw) or not sh:
            return None
        return float(nw.iloc[-1]) / sh

    def pe_history(self) -> pd.Series:
        """Year-end P/E: the export's year-end price ÷ that year's EPS (positive EPS only)."""
        price = self.f.annual("annual_price", "PRICE:")
        eps = self.eps_annual()
        both = pd.concat([price, eps], axis=1, keys=["p", "e"]).dropna()
        both = both[both["e"] > 0]
        return (both["p"] / both["e"]).astype(float)

    def pb_history(self) -> pd.Series:
        price = self.f.annual("annual_price", "PRICE:")
        sh = self.f.annual("derived", "Adjusted Equity Shares in Cr")
        nw = self.net_worth()
        both = pd.concat([price, nw / sh], axis=1, keys=["p", "b"]).dropna()
        both = both[both["b"] > 0]
        return (both["p"] / both["b"]).astype(float)

    def ebitda_annual(self) -> pd.Series:
        pbt = self.ann("annual_pl", "Profit before tax")
        intr = self.ann("annual_pl", "Interest")
        dep = self.ann("annual_pl", "Depreciation")
        oth = self.ann("annual_pl", "Other Income")
        return (pbt + intr + dep - oth).dropna()

    def capital_employed(self) -> pd.Series:
        b = self.ann("balance_sheet", "Borrowings")
        return (self.net_worth() + b).dropna()

    def capex_proxy(self) -> pd.Series:
        """Capex ≈ change in net block and CWIP plus depreciation (the export has no capex line)."""
        nb = self.ann("balance_sheet", "Net Block")
        cwip = self.ann("balance_sheet", "Capital Work in Progress")
        dep = self.ann("annual_pl", "Depreciation")
        gross = (nb + cwip.reindex(nb.index).fillna(0)).dropna()
        return (gross.diff() + dep.reindex(gross.index)).dropna()

    def fcf_annual(self) -> pd.Series:
        cfo = self.ann("cash_flow", "Cash from Operating Activity")
        return (cfo - self.capex_proxy()).dropna()

    def net_debt_cr(self) -> float | None:
        b = self.f.annual("balance_sheet", "Borrowings")
        c = self.f.annual("balance_sheet", "Cash & Bank")
        if not len(b) or not len(c):
            return None
        return float(b.iloc[-1] - c.iloc[-1])

    def ev_cr(self) -> float | None:
        nd, mc = self.net_debt_cr(), self.mcap_cr
        return None if nd is None or mc is None else mc + nd

    def shareholding_sorted(self) -> list[dict[str, Any]]:
        best: dict[Any, dict[str, Any]] = {}
        for r in self.inp.shareholding:
            k = str(r["period_end"])
            if k not in best or str(r.get("reported_on")) > str(best[k].get("reported_on")):
                best[k] = r
        return [best[k] for k in sorted(best)]

    def inputs_value(self, key: str) -> Measure:
        v = self.inp.profile_inputs.get(key)
        if v is None:
            return Measure.na(
                self.inp.input_reasons.get(key, f"{key} not supplied (profile_inputs.yaml)")
            )
        return Measure(float(v))
