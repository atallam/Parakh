"""Generate the synthetic CAS fixtures (plan 14 §4.3). Real CAS files are never committed.

Two monthly statements (Aug and Sep 2026) for a fake investor with 3 demat accounts (2 NSDL,
1 CDSL) and 12 ISINs, with quantity changes between the months. Every identifier is fake but
shaped like the real thing (PAN, DP ID, client ID, CDSL BO ID, mobile, e-mail), so redaction
tests (AC-F03.7, AC-F21.11) exercise the real patterns.

The JSON matches casparser 1.4.1's output shape for an NSDL CAS, as confirmed on your real
statement in spike ⑦ (29 Sep 2026): string quantities and prices, `statement_period.from_`,
dates like `01-Aug-2026`, account `type` strings, and `investor_info` without a PAN field (the
PAN is printed in the PDF text, so it lives under `_synthetic_pii` for the redaction tests).
A rendered PDF is not generated: casparser needs the depository's exact layout, and the
Phase 1 importer is tested at the parsed-dict boundary. Regenerate with
`uv run python tools/make_synthetic_cas.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "cas"

INVESTOR = {
    "name": "PARAKH TEST INVESTOR",
    "email": "parakh.test@example.com",
    "address": "Flat 0, Test Towers, Nowhere Road, Hyderabad 500000",
    "mobile": "9000000001",
}
PAN = "ZZZPT9999Z"  # printed in the CAS PDF text; casparser does not return it as a field
ACCOUNTS = [
    {"alias": "acct-a", "type": "NSDL Demat Account", "dp_id": "IN300000", "client_id": "10000001"},
    {"alias": "acct-b", "type": "NSDL Demat Account", "dp_id": "IN300001", "client_id": "10000002"},
    {"alias": "acct-c", "type": "CDSL Demat Account", "dp_id": "12081600", "client_id": "00000001"},
]
BO_ID = "1208160000000001"  # CDSL beneficiary-owner ID = DP ID + client ID
# (isin, name, account alias, Aug qty, Sep qty). Pilot ISINs first, then five others.
HOLDINGS = [
    ("INE646L01027", "INTERGLOBE AVIATION LIMITED", "acct-a", 40, 40),
    ("INE101A01026", "MAHINDRA & MAHINDRA LIMITED", "acct-a", 25, 30),
    ("INE040A01034", "HDFC BANK LIMITED", "acct-b", 120, 120),
    ("INE0HOQ01053", "BILLIONBRAINS GARAGE VENTURES LIMITED", "acct-c", 300, 300),
    ("INE249Z01020", "MAZAGON DOCK SHIPBUILDERS LIMITED", "acct-b", 15, 0),
    ("INE0LEZ01016", "ATHER ENERGY LIMITED", "acct-c", 200, 250),
    ("INE12UN01015", "SHADOWFAX TECHNOLOGIES LIMITED", "acct-c", 0, 150),
    ("INE467B01029", "TATA CONSULTANCY SERVICES LIMITED", "acct-a", 10, 10),
    ("INE009A01021", "INFOSYS LIMITED", "acct-b", 35, 35),
    ("INE002A01018", "RELIANCE INDUSTRIES LIMITED", "acct-a", 50, 50),
    ("INE154A01025", "ITC LIMITED", "acct-c", 400, 400),
    ("INE021A01026", "ASIAN PAINTS LIMITED", "acct-b", 12, 12),
]
PERIODS = {
    "2026-08": ("01-Aug-2026", "31-Aug-2026", 3),
    "2026-09": ("01-Sep-2026", "30-Sep-2026", 4),
}
PRICE = 1000.0  # why: a flat illustrative price; values are qty × price


def statement(month: str) -> dict[str, object]:
    start, end, qty_index = PERIODS[month]
    accounts = []
    for acct in ACCOUNTS:
        equities = []
        for isin, name, alias, qty_aug, qty_sep in HOLDINGS:
            qty = qty_aug if qty_index == 3 else qty_sep
            if alias == acct["alias"] and qty > 0:
                equities.append(
                    {
                        "name": name,
                        "isin": isin,
                        "num_shares": f"{qty:.3f}",
                        "price": f"{PRICE:.2f}",
                        "value": f"{qty * PRICE:.2f}",
                        "symbol": None,
                        "exchange": None,
                    }
                )
        accounts.append(
            {
                "name": acct["type"],
                "type": acct["type"],
                "dp_id": acct["dp_id"],
                "client_id": acct["client_id"],
                "folios": 0,
                "balance": f"{sum(float(e['value']) for e in equities):.2f}",
                "owners": [],
                "equities": equities,
                "mutual_funds": [],
                "bonds": [],
            }
        )
    return {
        "_synthetic": "Fake data for tests (plan 14 §4.3). Not a real statement.",
        "_synthetic_pii": {"pan": PAN, "bo_id": BO_ID},
        "accounts": accounts,
        "statement_period": {"from_": start, "to": end},
        "investor_info": INVESTOR,
        "file_type": "NSDL",
        "nps": None,
        "parse_warnings": [],
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for month in PERIODS:
        path = OUT / f"synthetic_cas_{month}.json"
        path.write_text(
            json.dumps(statement(month), indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
