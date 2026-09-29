"""Generate the synthetic CAS fixtures (plan 14 §4.3). Real CAS files are never committed.

Two monthly statements (Aug and Sep 2026) for a fake investor with 3 demat accounts (2 NSDL,
1 CDSL) and 12 ISINs, with quantity changes between the months. Every identifier is fake but
shaped like the real thing (PAN, DP ID, client ID, CDSL BO ID, mobile, e-mail), so redaction
tests (AC-F03.7, AC-F21.11) exercise the real patterns.

The JSON follows the holdings shape we expect from casparser. Phase 0.5 spike ⑦ parses your
real CAS, confirms casparser's field names, and adds a rendered PDF version of these fixtures
if the parser needs one; regenerate with `uv run python tools/make_synthetic_cas.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "cas"

INVESTOR = {
    "name": "PARAKH TEST INVESTOR",
    "pan": "ZZZPT9999Z",
    "email": "parakh.test@example.com",
    "mobile": "9000000001",
    "address": "Flat 0, Test Towers, Nowhere Road, Hyderabad 500000",
}
ACCOUNTS = [
    {"alias": "acct-a", "type": "NSDL", "dp_id": "IN300000", "client_id": "10000001"},
    {"alias": "acct-b", "type": "NSDL", "dp_id": "IN300001", "client_id": "10000002"},
    {"alias": "acct-c", "type": "CDSL", "bo_id": "1208160000000001"},
]
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
PERIODS = {"2026-08": ("2026-08-01", "2026-08-31", 3), "2026-09": ("2026-09-01", "2026-09-30", 4)}


def statement(month: str) -> dict[str, object]:
    start, end, qty_index = PERIODS[month]
    accounts = []
    for acct in ACCOUNTS:
        equities = []
        for isin, name, alias, qty_aug, qty_sep in HOLDINGS:
            qty = qty_aug if qty_index == 3 else qty_sep
            if alias == acct["alias"] and qty > 0:
                equities.append({"isin": isin, "name": name, "num_shares": qty})
        accounts.append(
            {
                **{k: v for k, v in acct.items() if k != "alias"},
                "name": f"{acct['type']} account",
                "equities": equities,
            }
        )
    return {
        "_synthetic": "Fake data for tests (plan 14 §4.3). Not a real statement.",
        "file_type": "NSDL",
        "statement_period": {"from": start, "to": end},
        "investor_info": INVESTOR,
        "accounts": accounts,
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
