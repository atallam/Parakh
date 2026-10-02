"""Value-lens document inputs from the filing-derived `profile.*` fundamentals (plan 13 D24).

The profile-inputs job stores what the exchange filings contain as `profile.<id>` and
`stake_pct.<SYMBOL>` rows. This turns the visible rows into the inputs the value metrics take.
Nothing is guessed: a part that is not in a filing leaves the input unset, with a reason.
"""

from __future__ import annotations

from typing import Any

# value-lens input -> the filed lines it is the sum of (all must be present)
SUMS: dict[str, tuple[str, ...]] = {
    "lease_liabilities_cr": ("lease_liabilities_noncurrent_cr", "lease_liabilities_current_cr"),
    "customer_advances_cr": ("contract_liabilities_cr",),
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
