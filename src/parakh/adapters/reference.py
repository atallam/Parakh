"""Reference lists: AMFI cap categories and Nifty index constituents (plan 05 §3.4; D9).

- AMFI "Average Market Capitalization of listed companies" (.xlsx, sheet FINAL), published every
  January and July for the six months just ended. Rank 1–100 = Large Cap, 101–250 = Mid Cap,
  251+ = Small Cap (SEBI circular of 6 Oct 2017). It is the official source of a stock's cap
  bucket (T1).
- niftyindices.com constituent CSVs (Company Name, Industry, Symbol, Series, ISIN Code).

Findings on the pilot (lists recorded 29 Sep 2026): index membership and AMFI category are
different things (MAZDOCK is AMFI Mid Cap but in the Nifty 100; GROWW is AMFI Large Cap but in
the Midcap 150), so both are stored. The Smallcap 250 file had 251 rows (a demerger in
progress), so row counts are checked with a tolerance, not exactly.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import re
from dataclasses import dataclass
from typing import Literal

import openpyxl

Bucket = Literal["large", "mid", "small"]
_BUCKETS: dict[str, Bucket] = {"large cap": "large", "mid cap": "mid", "small cap": "small"}
_PERIOD = re.compile(r"six months ended (\d{1,2} \w+ \d{4})", re.I)
INDEX_FILES = {
    "NIFTY 100": "ind_nifty100list",
    "NIFTY MIDCAP 150": "ind_niftymidcap150list",
    "NIFTY SMALLCAP 250": "ind_niftysmallcap250list",
}
INDEX_SIZES = {"NIFTY 100": 100, "NIFTY MIDCAP 150": 150, "NIFTY SMALLCAP 250": 250}


class ReferenceFormatError(ValueError):
    pass


@dataclass(frozen=True)
class AmfiRow:
    rank: int
    name: str
    isin: str
    avg_mcap_cr: float | None
    bucket: Bucket
    nse_symbol: str | None = None  # None when the stock is not listed on NSE


@dataclass(frozen=True)
class AmfiList:
    period_end: dt.date
    rows: list[AmfiRow]

    def by_isin(self) -> dict[str, AmfiRow]:
        return {r.isin: r for r in self.rows}


def parse_amfi_list(data: bytes) -> AmfiList:
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    try:
        rows = list(wb[wb.sheetnames[0]].iter_rows(values_only=True))
    finally:
        wb.close()
    title = next((str(r[0]) for r in rows[:5] if r and r[0] and _PERIOD.search(str(r[0]))), None)
    if title is None:
        raise ReferenceFormatError("AMFI list: period line ('six months ended …') not found")
    match = _PERIOD.search(title)
    assert match is not None
    period_end = dt.datetime.strptime(match.group(1), "%d %B %Y").date()
    header = next(
        (i for i, r in enumerate(rows[:10]) if r and "ISIN" in [str(c).strip() for c in r if c]),
        None,
    )
    if header is None:
        raise ReferenceFormatError("AMFI list: header row with 'ISIN' not found")
    cols = [str(c or "").strip() for c in rows[header]]
    isin_i = cols.index("ISIN")
    name_i = next(i for i, c in enumerate(cols) if c.lower().startswith("company"))
    cat_i = next(i for i, c in enumerate(cols) if c.lower().startswith("categorization"))
    avg_i = next((i for i, c in enumerate(cols) if c.lower().startswith("average of all")), None)
    nse_i = next((i for i, c in enumerate(cols) if c.lower() == "nse symbol"), None)
    out = []
    for r in rows[header + 1 :]:
        if not r or not isinstance(r[0], int | float) or not r[isin_i]:
            continue
        bucket = _BUCKETS.get(str(r[cat_i] or "").strip().lower())
        if bucket is None:
            continue
        avg = r[avg_i] if avg_i is not None else None
        nse = str(r[nse_i] or "").strip() if nse_i is not None else ""
        out.append(
            AmfiRow(
                int(r[0]),
                str(r[name_i]).strip(),
                str(r[isin_i]).strip(),
                float(avg) if isinstance(avg, int | float) else None,
                bucket,
                nse if nse and nse != "-" else None,
            )
        )
    if not out:
        raise ReferenceFormatError("AMFI list: no categorised rows")
    return AmfiList(period_end, out)


@dataclass(frozen=True)
class Constituent:
    index_id: str
    isin: str
    symbol: str
    name: str
    industry: str


def parse_index_constituents(data: bytes, index_id: str) -> list[Constituent]:
    reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
    need = {"Company Name", "Industry", "Symbol", "ISIN Code"}
    if not reader.fieldnames or not need <= {f.strip() for f in reader.fieldnames}:
        raise ReferenceFormatError(f"{index_id}: not a niftyindices constituent file")
    out = []
    for row in reader:
        clean = {k.strip(): (v or "").strip() for k, v in row.items() if k}
        if clean.get("ISIN Code"):
            out.append(
                Constituent(
                    index_id,
                    clean["ISIN Code"],
                    clean["Symbol"],
                    clean["Company Name"],
                    clean["Industry"],
                )
            )
    return out


def index_url(index_id: str) -> str:
    return f"https://www.niftyindices.com/IndexConstituent/{INDEX_FILES[index_id]}.csv"
