"""Sector-profile inputs read from the filed results XBRL (plan 13 D24; plan 01 §3; T1).

The results taxonomy has no tag for a lease liability, an aircraft rental or a contract
liability. Companies file them as **described lines**: a `DescriptionOf<Tag>` text and a
`<Tag>` amount that share one context, e.g. (IndiGo, FY2026 consolidated)

    DescriptionOfOtherNoncurrentFinancialLiabilities = "Lease liabilities"
    OtherNoncurrentFinancialLiabilities              = 644705000000        (₹64,470.5 Cr)

Found on the pilot (2 Oct 2026):
- INDIGO: lease liabilities (current and non-current), "Aircraft and engine rentals",
  "Supplementary rentals and aircraft repair and maintenance", "Foreign exchange loss": the
  inputs of EBITDAR and of lease-adjusted debt.
- MAZDOCK: "Contract Liability" under other current liabilities: the customer advances.
- Balance-sheet lines appear only in the half-year and full-year filings (September, March);
  expense lines appear every quarter (the quarter itself and the year to date).
- The order book is not in any XBRL; it comes from the investor presentation (a document
  input, read in Phase 2 with the concall work).
Amounts are in rupees and are divided by 1e7 to ₹ crore, as in `adapters.xbrl`.
"""

from __future__ import annotations

import datetime as dt
import html
import re
from dataclasses import dataclass
from typing import Literal

CRORE = 1e7
_CONTEXT = re.compile(r'<xbrli:context id="([^"]+)">(.*?)</xbrli:context>', re.S)
_FACT = re.compile(r'<[a-z][a-z\-]*:([A-Za-z]+)\b[^>]*contextRef="([^"]+)"[^>]*>([^<]*)<')
_DATE = r"(\d{4}-\d{2}-\d{2})"
_INSTANT = re.compile(rf"<xbrli:instant>{_DATE}</xbrli:instant>")
_START = re.compile(rf"<xbrli:startDate>{_DATE}</xbrli:startDate>")
_END = re.compile(rf"<xbrli:endDate>{_DATE}</xbrli:endDate>")
QUARTER_DAYS = 100  # a quarter is at most 92 days; the year to date is 180 or more

Kind = Literal["balance", "flow"]


@dataclass(frozen=True)
class DescribedLine:
    tag: str
    description: str
    value_cr: float
    kind: Kind  # balance = at the period end; flow = over the quarter
    period_end: dt.date


def described_lines(xml: str) -> list[DescribedLine]:
    """Every described line for the period end itself or for the quarter (not year to date)."""
    periods: dict[str, tuple[dt.date | None, dt.date]] = {}
    for cid, body in _CONTEXT.findall(xml):
        instant, start, end = _INSTANT.search(body), _START.search(body), _END.search(body)
        if instant:
            periods[cid] = (None, dt.date.fromisoformat(instant.group(1)))
        elif start and end:
            periods[cid] = (
                dt.date.fromisoformat(start.group(1)),
                dt.date.fromisoformat(end.group(1)),
            )
    text: dict[str, dict[str, str]] = {}
    amount: dict[str, dict[str, float]] = {}
    for name, cid, raw in _FACT.findall(xml):
        raw = raw.strip()
        if name.startswith("DescriptionOf"):
            text.setdefault(cid, {})[name.removeprefix("DescriptionOf")] = html.unescape(raw)
            continue
        try:
            amount.setdefault(cid, {})[name] = float(raw) / CRORE
        except ValueError:
            continue
    out = []
    for cid, tags in text.items():
        if cid not in periods:
            continue
        start, end = periods[cid]
        if start is not None and (end - start).days > QUARTER_DAYS:
            continue
        for tag, description in tags.items():
            value = amount.get(cid, {}).get(tag)
            if value is not None:
                out.append(
                    DescribedLine(
                        tag,
                        description,
                        round(value, 2),
                        "balance" if start is None else "flow",
                        end,
                    )
                )
    return out


def pick(lines: list[DescribedLine], tag: str, match: str, kind: Kind) -> float | None:
    """Sum of the lines under `tag` whose description contains `match` (case-insensitive)."""
    hits = [
        x.value_cr
        for x in lines
        if x.tag == tag and x.kind == kind and match.lower() in x.description.lower()
    ]
    return round(sum(hits), 2) if hits else None
