"""Quarterly shareholding pattern and promoter pledge, from the exchange filing (plan 01 §3; T1).

Source: NSE `corporate-share-holdings-master` (one row per quarter: promoter %, public %, the
filing time and a link to the XBRL) and the XBRL itself (SEBI LODR Reg. 31), which carries share
counts per category of shareholder.

Findings on the pilot (recorded 2 Oct 2026):
- Two taxonomies are in use. To 2023: percentages as numbers (19.46), one `InstitutionsMember`,
  pledge as `PledgedOrEncumberedNumberOfShares`. Now: percentages as fractions (0.1845),
  `InstitutionsDomesticMember` / `InstitutionsForeignMember`, pledge as
  `NumberOfSharesEncumberedUnderPledged` beside the wider `NumberOfSharesEncumbered` (pledge +
  non-disposal undertaking + other). So the scale is read from the total line (1 or 100) and
  categories are found by their member name, never by the context id.
- The filed percentage is of the SCRR share base, which leaves out shares underlying depository
  receipts (M&M: 2.09 Cr GDR shares; HDFC Bank: 205 Cr ADR shares). Dividing a category by
  `NumberOfShares` of the total line therefore understates it (M&M promoters 18.14% against the
  filed 18.45%). The filed percentages are stored, as the exchange and every data vendor quote
  them; the share counts are kept beside them.
- A company with no promoter (HDFC Bank) has no promoter context at all: promoter is 0, not
  missing.
- The filing lists named holders above 1% with their PAN field. Only the category totals are
  read; names are never parsed, stored or logged, and the raw file is not archived (only its hash).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
from dataclasses import dataclass
from typing import Any

_CONTEXT = re.compile(r'<xbrli:context id="([^"]+)">(.*?)</xbrli:context>', re.S)
_MEMBER = re.compile(r'explicitMember dimension="[\w-]+:(\w+)">\s*[\w-]+:(\w+)Member\s*<')
_INSTANT = re.compile(r"<xbrli:instant>(\d{4}-\d{2}-\d{2})</xbrli:instant>")
_FACT = re.compile(r'<[\w-]+:(\w+)\s[^>]*contextRef="([^"]+)"[^>]*>([^<]*)<')

# Category → member names across both taxonomies (first one present wins).
_MEMBERS: dict[str, tuple[str, ...]] = {
    "total": ("ShareholdingPattern",),
    "promoter": ("ShareholdingOfPromoterAndPromoterGroup",),
    "public": ("PublicShareholding",),
    "institutions": ("Institutions",),  # old taxonomy: domestic + foreign together
    "dii": ("InstitutionsDomestic",),
    "fii": ("InstitutionsForeign",),
    "fpi_old": ("InstitutionsForeignPortfolioInvestor", "ForeignPortfolioInvestor"),
    "mf": ("MutualFundsOrUTI", "MutualFundsOrUti"),
}
_PLEDGED = ("NumberOfSharesEncumberedUnderPledged", "PledgedOrEncumberedNumberOfShares")
_PCT = "ShareholdingAsAPercentageOfTotalNumberOfShares"
_ENCUMBERED = ("NumberOfSharesEncumbered", "PledgedOrEncumberedNumberOfShares")


class ShareholdingFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Shareholding:
    """One quarter-end pattern: share counts and percentages as filed (SCRR base)."""

    period_end: dt.date
    total_shares: int
    promoter_shares: int
    public_shares: int
    fii_shares: int | None
    dii_shares: int | None
    mf_shares: int | None
    promoter_pledged_shares: int
    promoter_encumbered_shares: int
    promoter_pct: float
    public_pct: float
    fii_pct: float | None
    dii_pct: float | None
    mf_pct: float | None
    raw_hash: str

    @property
    def pledge_pct(self) -> float:
        """Pledged promoter shares as % of the promoters' own holding (plan 01 veto input)."""
        if not self.promoter_shares:
            return 0.0
        return round(100 * self.promoter_pledged_shares / self.promoter_shares, 4)

    @property
    def encumbered_pct(self) -> float:
        if not self.promoter_shares:
            return 0.0
        return round(100 * self.promoter_encumbered_shares / self.promoter_shares, 4)


def _int(text: str | None) -> int | None:
    try:
        return int(float(text)) if text not in (None, "") else None
    except ValueError:
        return None


def parse_shp_xbrl(xml: str) -> Shareholding:
    """Category totals from a shareholding-pattern XBRL (either taxonomy)."""
    by_member: dict[str, str] = {}
    period: dt.date | None = None
    for cid, body in _CONTEXT.findall(xml):
        members = _MEMBER.findall(body)
        if len(members) != 1 or members[0][0] != "CategoryOfShareholdersAxis":
            continue  # named holders and sub-tables carry a second dimension
        by_member.setdefault(members[0][1], cid)
        if members[0][1] == "ShareholdingPattern":
            instant = _INSTANT.search(body)
            period = dt.date.fromisoformat(instant.group(1)) if instant else None
    wanted = {cid for cid in by_member.values()}
    facts: dict[tuple[str, str], str] = {}
    for name, cid, value in _FACT.findall(xml):
        if cid in wanted:
            facts.setdefault((cid, name), value.strip())

    def shares(category: str, names: tuple[str, ...] = ("NumberOfShares",)) -> int | None:
        for member in _MEMBERS[category]:
            cid = by_member.get(member)
            if cid is None:
                continue
            for name in names:
                value = _int(facts.get((cid, name)))
                if value is not None:
                    return value
            return None
        return None

    def filed(category: str) -> float | None:
        for member in _MEMBERS[category]:
            cid = by_member.get(member)
            if cid is not None:
                try:
                    return float(facts[(cid, _PCT)])
                except (KeyError, ValueError):
                    return None
        return None

    total, whole = shares("total"), filed("total")
    if whole is None or whole <= 0:
        raise ShareholdingFormatError("shareholding XBRL: total percentage line not found")
    scale = 100 if whole <= 1 else 1  # current taxonomy files fractions, the old one numbers

    def pct(category: str) -> float | None:
        value = filed(category)
        return None if value is None else round(value * scale, 2)

    if period is None or not total:
        raise ShareholdingFormatError("shareholding XBRL: total shares or period not found")
    public = shares("public")
    if public is None:
        raise ShareholdingFormatError("shareholding XBRL: public shareholding not found")
    fii, dii = shares("fii"), shares("dii")
    fii_pct, dii_pct = pct("fii"), pct("dii")
    if fii is None and dii is None:  # old taxonomy: split institutions by the FPI line
        inst, fpi = shares("institutions"), shares("fpi_old")
        inst_pct, fpi_pct = pct("institutions"), pct("fpi_old")
        if inst is not None and fpi is not None:
            fii, dii = fpi, inst - fpi
        if inst_pct is not None and fpi_pct is not None:
            fii_pct, dii_pct = fpi_pct, round(inst_pct - fpi_pct, 2)
    return Shareholding(
        period_end=period,
        total_shares=total,
        promoter_shares=shares("promoter") or 0,
        public_shares=public,
        fii_shares=fii,
        dii_shares=dii,
        mf_shares=shares("mf"),
        promoter_pledged_shares=shares("promoter", _PLEDGED) or 0,
        promoter_encumbered_shares=shares("promoter", _ENCUMBERED) or 0,
        promoter_pct=pct("promoter") or 0.0,
        public_pct=pct("public") or 0.0,
        fii_pct=fii_pct,
        dii_pct=dii_pct,
        mf_pct=pct("mf"),
        raw_hash="sha256:" + hashlib.sha256(xml.encode("utf-8")).hexdigest(),
    )


@dataclass(frozen=True)
class ShpFiling:
    period_end: dt.date
    reported_on: dt.date
    promoter_pct: float | None
    public_pct: float | None
    xbrl_url: str | None
    revised: bool


def _date(text: str) -> dt.date:
    return dt.datetime.strptime(text.strip().title()[:11], "%d-%b-%Y").date()


def _float(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def parse_shp_master(rows: list[dict[str, Any]]) -> list[ShpFiling]:
    """Quarter-end filings, newest first; one per period (the latest filing wins).

    A young listing also files a pattern on its listing date (not a quarter end); those are kept:
    the first pattern after an IPO is the baseline for lock-in and promoter-selling checks.
    """
    out: dict[dt.date, ShpFiling] = {}
    for r in rows:
        if not r.get("date"):
            continue
        stamp = r.get("broadcastDate") or r.get("submissionDate") or r.get("systemDate")
        if not stamp:
            continue
        filing = ShpFiling(
            _date(r["date"]),
            _date(stamp),
            _float(r.get("pr_and_prgrp")),
            _float(r.get("public_val")),
            r.get("xbrl") or None,
            str(r.get("revisedData") or "N").upper() == "Y",
        )
        held = out.get(filing.period_end)
        if held is None or filing.reported_on > held.reported_on:
            out[filing.period_end] = filing
    return sorted(out.values(), key=lambda f: f.period_end, reverse=True)
