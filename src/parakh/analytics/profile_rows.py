"""Value-lens document inputs from the filing-derived `profile.*` fundamentals (plan 13 D24).

The profile-inputs job stores what the exchange filings contain as `profile.<id>` and
`stake_pct.<SYMBOL>` rows. This turns the visible rows into the inputs the value metrics take.
Nothing is guessed: a part that is not in a filing leaves the input unset, with a reason.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

# value-lens input -> the filed lines it is the sum of (all must be present)
SUMS: dict[str, tuple[str, ...]] = {
    "lease_liabilities_cr": ("lease_liabilities_noncurrent_cr", "lease_liabilities_current_cr"),
    "customer_advances_cr": ("contract_liabilities_cr",),
}

# value-lens input -> a filed quarterly flow summed over the last four consecutive quarters
TTM_SUMS: dict[str, str] = {
    "lease_cost_cr": "aircraft_engine_rentals_cr",
}


def _latest(rows: list[dict[str, Any]], metric: str) -> float | None:
    best = None
    for r in rows:
        if (
            r["metric_id"] == metric
            and r.get("value") is not None
            and (best is None or r["period_end"] > best["period_end"])
        ):
            best = r
    return None if best is None else float(best["value"])


def _ttm(rows: list[dict[str, Any]], metric: str) -> tuple[float | None, str]:
    """Sum of the last four quarters of a filed flow; None with a reason unless all four exist."""
    qs: dict[Any, float] = {}
    for r in rows:
        if r["metric_id"] == metric and r.get("value") is not None:
            qs[r["period_end"]] = float(r["value"])
    ends = sorted(qs)[-4:]
    if len(ends) < 4:
        return None, f"only {len(ends)} of 4 quarters filed"
    # consecutive quarters end about 91 days apart; a gap means a quarter is missing in between
    days = [dt.date.fromisoformat(str(e)[:10]) for e in ends]
    gaps = [(b - a).days for a, b in zip(days, days[1:], strict=False)]
    if any(not 80 <= g <= 100 for g in gaps):
        return None, "the last four filed quarters are not consecutive"
    return float(sum(qs[e] for e in ends)), ""


def profile_inputs_from(
    rows: list[dict[str, Any]],
) -> tuple[dict[str, float | None], dict[str, str]]:
    values: dict[str, float | None] = {}
    reasons: dict[str, str] = {}
    for key, parts in SUMS.items():
        got = [_latest(rows, f"profile.{p}") for p in parts]
        if all(g is not None for g in got):
            values[key] = float(sum(got))  # type: ignore[arg-type]
        elif any(r["metric_id"].startswith("profile.") for r in rows):
            missing = [p for p, g in zip(parts, got, strict=True) if g is None]
            reasons[key] = f"{key}: not yet in a filing ({', '.join(missing)})"
    for key, flow in TTM_SUMS.items():
        total, why = _ttm(rows, f"profile.{flow}")
        if total is not None:
            values[key] = total
        elif any(r["metric_id"].startswith("profile.") for r in rows):
            reasons[key] = f"{key}: {why} ({flow})"
    return values, reasons


def stakes_from(rows: list[dict[str, Any]], investees: list[Any]) -> list[dict[str, Any]]:
    out = []
    for inv in investees:
        pct = _latest(rows, f"profile.stake_pct.{inv.symbol}")
        out.append(
            {
                "name": inv.symbol,
                "isin": inv.isin,
                "stake": None if pct is None else pct / 100.0,
                "mcap_cr": None,
            }
        )
    return out
