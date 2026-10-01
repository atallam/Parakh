"""Fundamentals checks: export health, history length, recency, and the XBRL tie-out.

Check IDs:
- DQ.fundamentals.export: the parser's own findings (blank META, share-count gaps, pre-listing
  counts) as a warning; a balance sheet that doesn't balance or a missing section fails.
- DQ.fundamentals.history: 10 annual periods, or every year since listing for young listings.
- DQ.fundamentals.recency: the latest quarter is recent enough (results are due within 45 days).
- DQ.fundamentals.xbrl_tieout: Screener's quarter agrees with the filed XBRL line by line.
"""

from __future__ import annotations

import datetime as dt
import re

from parakh.adapters.screener_export import ScreenerExport
from parakh.configs.models import FundamentalsDq, Security
from parakh.quality import DqResult

_SUFFIX = re.compile(r"\b(LTD|LIMITED|THE)\b")


def normalize_name(name: str) -> str:
    """'INTERGLOBE AVIATION LTD' and 'InterGlobe Aviation Ltd' → 'INTERGLOBE AVIATION'."""
    text = re.sub(r"[^A-Z0-9 ]", " ", name.upper().replace("&", " AND "))
    return " ".join(_SUFFIX.sub(" ", text).split())


def match_security(export: ScreenerExport, pilot: list[Security]) -> Security | None:
    target = normalize_name(export.company_name)
    hits = [s for s in pilot if normalize_name(s.name) == target]
    return hits[0] if len(hits) == 1 else None


def fiscal_year_end(day: dt.date) -> dt.date:
    """Indian fiscal year end (31 Mar) on or after `day`."""
    return dt.date(day.year if day.month <= 3 else day.year + 1, 3, 31)


def check_export(
    export: ScreenerExport, sec: Security, today: dt.date, cfg: FundamentalsDq
) -> list[DqResult]:
    isin = sec.isin
    fatal = [i for i in export.issues if "does not balance" in i or "missing" in i]
    results = [
        DqResult(
            "DQ.fundamentals.export",
            isin,
            "fail" if fatal else ("warn" if export.issues else "pass"),
            {"issues": export.issues},
        )
    ]
    annual = export.periods("annual_pl")
    young = sec.listed_on is not None and sec.listed_on > today.replace(
        year=today.year - cfg.min_annual_years
    )
    if young and sec.listed_on is not None:
        need_from = fiscal_year_end(sec.listed_on)
        ok = bool(annual) and annual[0] <= need_from
        rule = f"since listing (FY ending {need_from})"
    else:
        ok = len(annual) >= cfg.min_annual_years
        rule = f"{cfg.min_annual_years} annual periods"
    results.append(
        DqResult(
            "DQ.fundamentals.history",
            isin,
            "pass" if ok else "fail",
            {
                "annual_periods": len(annual),
                "first": annual[0].isoformat() if annual else None,
                "rule": rule,
            },
        )
    )
    quarters = export.periods("quarterly_pl")
    age = (today - quarters[-1]).days if quarters else None
    results.append(
        DqResult(
            "DQ.fundamentals.recency",
            isin,
            "pass" if age is not None and age <= cfg.max_latest_quarter_age_days else "fail",
            {"latest_quarter": quarters[-1].isoformat() if quarters else None, "age_days": age},
        )
    )
    return results


def tieout(
    screener: dict[str, float], filed: dict[str, float], cfg: FundamentalsDq
) -> tuple[list[str], list[dict[str, object]]]:
    """(lines compared, mismatches) between Screener's quarter and the filing's mapped lines."""
    compared, bad = [], []
    for item, value in filed.items():
        if item not in screener:
            continue
        compared.append(item)
        diff = abs(screener[item] - value)
        limit = max(cfg.xbrl_tolerance_cr, abs(value) * cfg.xbrl_tolerance_pct / 100)
        if diff > limit:
            bad.append(
                {
                    "line": item,
                    "screener": screener[item],
                    "filed": value,
                    "diff_cr": round(diff, 2),
                }
            )
    return compared, bad


def check_tieout(isin: str, checks: list[dict[str, object]], filings_found: int) -> DqResult:
    """One result per stock over the quarters compared; warn when no filing could be compared."""
    if not checks:
        return DqResult(
            "DQ.fundamentals.xbrl_tieout",
            isin,
            "warn",
            {"compared_quarters": 0, "filings": filings_found},
        )
    bad = [c for c in checks if c["mismatches"]]
    return DqResult(
        "DQ.fundamentals.xbrl_tieout",
        isin,
        "fail" if bad else "pass",
        {"compared_quarters": len(checks), "quarters": checks},
    )
