"""Exchange XBRL results → Screener-comparable line items (the T1 cross-check of fundamentals).

Two NSE sources, same XBRL shape (spike ③ and Phase 1, 1 Oct 2026):
- `/api/corporates-financial-results`: filings up to the Dec 2024 quarter (namespace in-bse-fin).
- `/api/integrated-filing-results`: SEBI's integrated filing, Mar 2025 onwards (in-capmkt).
Both list each filing with a broadcast timestamp (the `reported_on` date) and an XBRL link.

Values are in rupees whatever `LevelOfRoundingUsedInFinancialStatements` says, so they are
divided by 1e7 to ₹ crore. The quarter itself is the context `OneD`; `FourD` is year-to-date.

Definition map, verified to the paisa on M&M (Dec 2024, Jun 2026) and HDFC Bank (Jun 2026):
- Ind AS companies: Sales = RevenueFromOperations; Interest = FinanceCosts; Depreciation;
  Tax = TaxExpense; PBT includes the share of associates/JVs, which some companies report after
  PBT (M&M) and others inside it (MAZDOCK), detected from Income − Expenses; Net profit = profit
  attributable to owners of the parent (consolidated). Screener splits Expenses and Other
  Income its own way (M&M Jun 2026: ₹262 Cr moved between them), so only their difference is
  compared, as implied by Screener's identity (PBT = Sales − that − Depreciation − Interest).
- Banks: Sales = InterestEarned; Interest = InterestExpended; Expenses = operating expenses +
  provisions; PBT before exceptional items (HDFC Bank Sep 2025); Net profit after minority
  interest and associates.
Verified on the first full pilot load (2 Oct 2026): 7 pilots, the latest 4 quarters each.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Literal

CRORE = 1e7
_FACT = re.compile(r'<[a-z][a-z\-]*:([A-Za-z]+)\b[^>]*contextRef="([^"]+)"[^>]*>([^<]*)<')
NET_COST = "Expenses less Other Income"  # the comparable form of Screener's two split lines


@dataclass
class XbrlResult:
    period_start: dt.date | None
    period_end: dt.date
    consolidated: bool
    taxonomy: Literal["indas", "banking"]
    values_cr: dict[str, float] = field(default_factory=dict)  # quarter context only

    def get(self, *names: str) -> float | None:
        for n in names:
            if n in self.values_cr:
                return self.values_cr[n]
        return None


def parse_xbrl(text: str, context: str = "OneD") -> XbrlResult:
    numeric: dict[str, float] = {}
    strings: dict[str, str] = {}
    for name, ctx, raw in _FACT.findall(text):
        if ctx != context:
            continue
        raw = raw.strip()
        try:
            numeric[name] = float(raw) / CRORE
        except ValueError:
            strings[name] = raw
    end = strings.get("DateOfEndOfReportingPeriod")
    if not end:
        raise ValueError("XBRL has no DateOfEndOfReportingPeriod in the quarter context")
    start = strings.get("DateOfStartOfReportingPeriod")
    nature = strings.get("NatureOfReportStandaloneConsolidated", "")
    banking = "InterestEarned" in numeric
    for key in ("DateOfEndOfReportingPeriod", "DateOfStartOfReportingPeriod"):
        numeric.pop(key, None)
    return XbrlResult(
        period_start=dt.date.fromisoformat(start) if start else None,
        period_end=dt.date.fromisoformat(end),
        consolidated=nature.lower().startswith("consolidated"),
        taxonomy="banking" if banking else "indas",
        values_cr=numeric,
    )


def screener_lines(x: XbrlResult) -> dict[str, float]:
    """The filing re-expressed in Screener's quarterly line items (see the module docstring)."""
    out: dict[str, float] = {}

    def put(item: str, value: float | None) -> None:
        if value is not None:
            out[item] = round(value, 2)

    if x.taxonomy == "banking":
        put("Sales", x.get("InterestEarned"))
        put("Other Income", x.get("OtherIncome"))
        put("Interest", x.get("InterestExpended"))
        opex, prov = x.get("OperatingExpenses"), x.get("ProvisionsOtherThanTaxAndContingencies")
        if opex is not None:
            put("Expenses", opex + (prov or 0.0))
        pbt = x.get("ProfitLossFromOrdinaryActivitiesBeforeTax")
        # Screener's bank PBT is before exceptional items (HDFC Bank Sep 2025: −₹753.10 Cr)
        put("Profit before tax", None if pbt is None else pbt - (x.get("ExceptionalItems") or 0.0))
        put("Tax", x.get("TaxExpense"))
        put(
            "Net profit",
            x.get(
                "ProfitLossAfterTaxesMinorityInterestAndShareOfProfitLossOfAssociates",
                "ProfitLossForThePeriod",
            ),
        )
        return out

    assoc = (
        x.get("ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod") or 0.0
    )
    fin = x.get("FinanceCosts")
    dep = x.get("DepreciationDepletionAndAmortisationExpense")
    sales = x.get("RevenueFromOperations")
    put("Sales", sales)
    put("Interest", fin)
    put("Depreciation", dep)
    put("Tax", x.get("TaxExpense"))
    pbt = x.get("ProfitBeforeTax")
    if pbt is not None:
        # Companies place the associates' share either after PBT (M&M) or inside it (MAZDOCK).
        # Income − Expenses (+ exceptional) tells which; Screener's PBT always includes it.
        income, expenses = x.get("Income"), x.get("Expenses")
        exceptional = x.get("ExceptionalItemsBeforeTax") or 0.0
        inside = False
        if income is not None and expenses is not None and assoc:
            base = income - expenses + exceptional
            inside = abs(base + assoc - pbt) < abs(base - pbt)
        put("Profit before tax", pbt if inside else pbt + assoc)
    net = x.get("ProfitOrLossAttributableToOwnersOfParent") if x.consolidated else None
    put("Net profit", net if net is not None else x.get("ProfitLossForPeriod"))
    if sales is not None and "Profit before tax" in out:
        # Screener splits Expenses and Other Income its own way, so compare their difference,
        # implied by Screener's identity: PBT = Sales − (Expenses − Other Income) − Dep − Int.
        put(NET_COST, sales - (dep or 0.0) - (fin or 0.0) - out["Profit before tax"])
    return out


def screener_quarter(values: dict[str, float | None]) -> dict[str, float]:
    """Screener's quarterly lines in the same comparable form as `screener_lines`."""
    out = {k: float(v) for k, v in values.items() if v is not None}
    if "Expenses" in out and "Other Income" in out:
        out[NET_COST] = round(out["Expenses"] - out["Other Income"], 2)
    return out


# -- filing lists ----------------------------------------------------------------------------
@dataclass(frozen=True)
class Filing:
    symbol: str
    period_end: dt.date
    consolidated: bool
    broadcast_at: dt.datetime  # IST, naive
    xbrl_url: str
    source: str  # "nse_results" (to Dec 2024) or "nse_integrated" (Mar 2025 on)
    revised: bool = False


def _ts(*candidates: object) -> dt.datetime | None:
    """First parseable timestamp. Some integrated-filing rows have no broadcast date (seen on
    the Phase 1 pilot load, 2 Oct 2026); their creation date is the fallback."""
    for value in candidates:
        if isinstance(value, str) and value.strip() and value.strip() not in ("-", "None"):
            try:
                return dt.datetime.strptime(value.strip(), "%d-%b-%Y %H:%M:%S")
            except ValueError:
                continue
    return None


def parse_financial_results(rows: list[dict[str, object]]) -> list[Filing]:
    """`/api/corporates-financial-results`: quarterly, non-cumulative rows with an XBRL link."""
    out = []
    for r in rows:
        if r.get("period") != "Quarterly" or r.get("cumulative") == "Cumulative":
            continue
        url = str(r.get("xbrl") or "")
        when = _ts(r.get("broadCastDate"), r.get("exchdisstime"), r.get("filingDate"))
        if not url.endswith(".xml") or when is None:
            continue
        out.append(
            Filing(
                symbol=str(r["symbol"]),
                period_end=dt.datetime.strptime(str(r["toDate"]), "%d-%b-%Y").date(),
                consolidated=str(r.get("consolidated", "")).startswith("Consolidated"),
                broadcast_at=when,
                xbrl_url=url,
                source="nse_results",
            )
        )
    return out


def parse_integrated_filings(payload: dict[str, object]) -> list[Filing]:
    """`/api/integrated-filing-results` (type "Integrated Filing- Financials")."""
    rows = payload.get("data") or []
    out = []
    for r in rows if isinstance(rows, list) else []:
        url = str(r.get("xbrl") or "")
        when = _ts(r.get("broadcast_Date"), r.get("creation_Date"))
        if not url.endswith(".xml") or when is None:
            continue
        out.append(
            Filing(
                symbol=str(r["symbol"]),
                period_end=dt.datetime.strptime(str(r["qe_Date"]), "%d-%b-%Y").date(),
                consolidated=str(r.get("consolidated", "")).startswith("Consolidated"),
                broadcast_at=when,
                xbrl_url=url,
                source="nse_integrated",
                revised=str(r.get("type_Sub", "Original")) != "Original",
            )
        )
    return out


def first_reported(filings: list[Filing]) -> dict[dt.date, dt.datetime]:
    """Quarter end → when results were first public (any filing for that quarter)."""
    out: dict[dt.date, dt.datetime] = {}
    for f in filings:
        if f.period_end not in out or f.broadcast_at < out[f.period_end]:
            out[f.period_end] = f.broadcast_at
    return out
