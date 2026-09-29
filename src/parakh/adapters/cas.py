"""Depository CAS (NSDL/CDSL) → holdings per account: the quantity source of truth (plan 13 D8).

casparser (MIT) turns the password-protected PDF into a dict; this module turns that dict into
`CasStatement`, keeping only what Parakh needs. Findings from spike ⑦ and the Phase 1 files:
- Equity rows carry quantity and a statement-date price, never cost. Mutual-fund rows carry
  units and `avg_cost`.
- Quantities are settled holdings at the statement's end date, so trades on the last day or
  two are missing until the next statement (reconcile on settlement date).

Privacy (plan 13 P6, AC-F03.7): the investor's name, e-mail, address, mobile and PAN, account
DP/client IDs, MF folio numbers and UCCs are never copied out of the casparser dict. Accounts are
identified by `account_ref`, a keyed hash (HMAC-SHA256 with a local key) that is stable across
statements but can't be reversed or brute-forced without the key.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

ACCOUNT_REF_PREFIX = "acct_"


class CasFormatError(ValueError):
    pass


@dataclass(frozen=True)
class CasHolding:
    account_ref: str
    depository: Literal["NSDL", "CDSL", "OTHER"]
    kind: Literal["equity", "mutual_fund"]
    isin: str
    name: str
    qty: float
    avg_cost_inr: float | None  # mutual funds only; equity rows have no cost

    @property
    def is_equity(self) -> bool:
        return self.kind == "equity"


@dataclass(frozen=True)
class CasStatement:
    period_from: dt.date
    period_to: dt.date
    file_type: str
    holdings: list[CasHolding]
    warnings: list[str]

    def qty_by_isin(self, kind: str | None = "equity") -> dict[str, float]:
        out: dict[str, float] = defaultdict(float)
        for h in self.holdings:
            if kind is None or h.kind == kind:
                out[h.isin] += h.qty
        return dict(out)

    @property
    def account_refs(self) -> list[str]:
        return sorted({h.account_ref for h in self.holdings})


def account_ref(dp_id: str, client_id: str, key: bytes) -> str:
    """A stable, non-reversible reference for a demat account (P6)."""
    digest = hmac.new(key, f"{dp_id}|{client_id}".encode(), hashlib.sha256).hexdigest()
    return ACCOUNT_REF_PREFIX + digest[:12]


def _date(value: object) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                return dt.datetime.strptime(value.strip(), fmt).date()
            except ValueError:
                continue
    raise CasFormatError(f"unrecognised statement date {value!r}")


def _float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError as exc:
        raise CasFormatError(f"not a number: {value!r}") from exc


def _depository(account_type: object) -> Literal["NSDL", "CDSL", "OTHER"]:
    text = str(account_type or "").upper()
    return "NSDL" if "NSDL" in text else "CDSL" if "CDSL" in text else "OTHER"


def _clean_name(name: object) -> str:
    # casparser appends the security type: "ATHER ENERGY LIMITED # EQUITY SHARES"
    return str(name or "").split("#")[0].strip()


def from_casparser(data: dict[str, Any], key: bytes) -> CasStatement:
    """Build a CasStatement from casparser's `output="dict"` result. Drops every identifier."""
    if not key:
        raise ValueError("an account key is required to reference accounts (P6)")
    try:
        period = data["statement_period"]
        accounts = data["accounts"]
    except (KeyError, TypeError) as exc:
        raise CasFormatError("not a casparser depository CAS dict") from exc
    holdings: list[CasHolding] = []
    for account in accounts:
        dp_id, client_id = str(account.get("dp_id") or ""), str(account.get("client_id") or "")
        if not dp_id and not client_id:
            raise CasFormatError("account without DP or client ID; cannot reference it")
        ref = account_ref(dp_id, client_id, key)
        depository = _depository(account.get("type"))
        for eq in account.get("equities") or []:
            qty = _float(eq.get("num_shares"))
            if eq.get("isin") and qty:
                holdings.append(
                    CasHolding(
                        ref,
                        depository,
                        "equity",
                        eq["isin"],
                        _clean_name(eq.get("name")),
                        qty,
                        None,
                    )
                )
        for mf in account.get("mutual_funds") or []:
            qty = _float(mf.get("balance"))
            if mf.get("isin") and qty:
                holdings.append(
                    CasHolding(
                        ref,
                        depository,
                        "mutual_fund",
                        mf["isin"],
                        _clean_name(mf.get("name")),
                        qty,
                        _float(mf.get("avg_cost")),
                    )
                )
    return CasStatement(
        period_from=_date(period.get("from_") or period.get("from")),
        period_to=_date(period["to"]),
        file_type=str(data.get("file_type") or ""),
        holdings=holdings,
        # casparser warnings can quote statement text; keep only a count-safe summary
        warnings=[
            f"casparser warning {i + 1}" for i, _ in enumerate(data.get("parse_warnings") or [])
        ],
    )


def read_cas_pdf(path: Path, password: str, key: bytes) -> CasStatement:  # pragma: no cover
    """Parse a CAS PDF on your PC. Needs casparser; the PDF never leaves the machine."""
    import casparser

    raw: Any = casparser.read_cas_pdf(str(path), password, output="dict")
    if hasattr(raw, "model_dump"):  # casparser 1.4 returns a pydantic model even for "dict"
        raw = raw.model_dump()
    if not isinstance(raw, dict):
        raise CasFormatError("casparser did not return a CAS dict")
    return from_casparser(raw, key)
