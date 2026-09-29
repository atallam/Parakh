"""Spike ④: do our sources agree on split/bonus adjustment around real pilot ex-dates?

- Yahoo via yfinance: raw Close vs Adj Close and the recorded splits.
- NSE bhavcopy (UDiFF): the exchange's unadjusted closes on the days either side.
Then our back_adjust() with the known actions should remove the gap.
"""

from __future__ import annotations

import datetime as dt
import io
import zipfile

from _common import Recorder, client

from parakh.adapters.corporate_actions import CorporateAction, back_adjust, find_gaps, unexplained

EVENTS = [
    (
        "MAZDOCK",
        "INE249Z01020",
        CorporateAction("INE249Z01020", dt.date(2024, 12, 27), "split", 2.0, "news+NSE"),
    ),
    (
        "HDFCBANK",
        "INE040A01034",
        CorporateAction("INE040A01034", dt.date(2025, 8, 26), "bonus", 1.0, "news+NSE"),
    ),
]


def bhav_close(c, day: dt.date, isin: str) -> float | None:
    url = f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{day:%Y%m%d}_F_0000.csv.zip"
    r = c.get(url)
    if r.status_code != 200:
        return None
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        text = z.read(z.namelist()[0]).decode("utf-8")
    header, *rows = text.splitlines()
    cols = header.split(",")
    for row in rows:
        cells = row.split(",")
        rec = dict(zip(cols, cells, strict=False))
        if rec.get("ISIN") == isin and rec.get("SctySrs") == "EQ":
            return float(rec["ClsPric"])
    return None


def main() -> None:
    rec = Recorder("s4")
    import yfinance as yf

    with client() as c:
        for symbol, isin, action in EVENTS:
            start = action.ex_date - dt.timedelta(days=7)
            end = action.ex_date + dt.timedelta(days=7)
            try:
                df = yf.Ticker(f"{symbol}.NS").history(
                    start=start, end=end, auto_adjust=False, actions=True
                )
                closes = {ts.date(): float(v) for ts, v in df["Close"].items()}
                raw_gaps = find_gaps(closes, [action])
                rec.note(
                    probe=f"yfinance {symbol}",
                    ok=not df.empty,
                    rows=len(df),
                    splits=[(str(k.date()), float(v)) for k, v in df["Stock Splits"].items() if v],
                    gaps_in_close=[(str(g.day), round(g.move_ratio, 3)) for g in raw_gaps],
                    note="no gap = Yahoo Close is already split/bonus-adjusted",
                )
            except Exception as exc:
                rec.note(
                    probe=f"yfinance {symbol}", ok=False, error=f"{type(exc).__name__}: {exc}"[:300]
                )
            try:
                days = [action.ex_date - dt.timedelta(days=d) for d in range(1, 5)] + [
                    action.ex_date
                ]
                bhav = {d: bhav_close(c, d, isin) for d in days}
                bhav = {d: v for d, v in bhav.items() if v is not None}
                gaps = find_gaps(bhav, [action])
                adjusted = back_adjust(bhav, [action])
                rec.note(
                    probe=f"nse.bhavcopy {symbol}",
                    ok=bool(bhav),
                    closes={str(k): v for k, v in sorted(bhav.items())},
                    gaps=[
                        (str(g.day), round(g.move_ratio, 3), g.explained_by is not None)
                        for g in gaps
                    ],
                    unexplained_after_adjust=len(unexplained(find_gaps(adjusted, []))),
                )
            except Exception as exc:
                rec.note(
                    probe=f"nse.bhavcopy {symbol}",
                    ok=False,
                    error=f"{type(exc).__name__}: {exc}"[:300],
                )
    rec.save()


if __name__ == "__main__":
    main()
