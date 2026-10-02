"""Daily prices: Yahoo (adjusted, primary) and exchange bhavcopies (official, fallback and check).

Plan 00 "Data sources": yfinance `TICKER.NS` is the primary adjusted series (T2); the NSE and BSE
bhavcopies are official (T1) but unadjusted. Findings that shape this module (spikes ①, ④):
- Yahoo's Close is already adjusted for splits and bonuses; Adj Close also removes dividends.
  Parakh stores both: `close` (split/bonus-adjusted) for returns and levels, `adj_close`
  (total return) for momentum.
- Bhavcopies are unadjusted: HDFCBANK fell 50.4% on the 1:1 bonus ex-date (26 Aug 2025). They
  are back-adjusted with corporate actions before any comparison with Yahoo.
- Both exchanges publish the same "UDiFF" CSV layout (TradDt, ISIN, TckrSymb, SctySrs, OpnPric, …)
  since July 2024; NSE zips it, BSE doesn't.
- The NSE equity list (EQUITY_L.csv) gives each listing date, which bounds a young listing's
  history (D24: since listing for GROWW, ATHERENERG, SHADOWFAX).
"""

from __future__ import annotations

import datetime as dt
import io
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import pandas as pd

from parakh.adapters.corporate_actions import CorporateAction, back_adjust

EXCHANGE_COLUMNS = [
    "isin",
    "trade_date",
    "symbol",
    "series",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "source",
]
# Equity series worth keeping: EQ (rolling), BE/BZ (trade-for-trade). A pilot moving to BE is
# itself a surveillance signal (Phase 3), so the series is kept on every row.
NSE_EQUITY_SERIES = frozenset({"EQ", "BE", "BZ"})
_UDIFF = {
    "TradDt": "trade_date",
    "ISIN": "isin",
    "TckrSymb": "symbol",
    "SctySrs": "series",
    "OpnPric": "open",
    "HghPric": "high",
    "LwPric": "low",
    "ClsPric": "close",
    "TtlTradgVol": "volume",
}


class PriceSourceError(ValueError):
    pass


def _udiff_frame(text: str, source: str) -> pd.DataFrame:
    raw = pd.read_csv(io.StringIO(text), dtype=str)
    missing = set(_UDIFF) - set(raw.columns)
    if missing:
        raise PriceSourceError(f"{source}: not a UDiFF bhavcopy (missing {sorted(missing)})")
    if "FinInstrmTp" in raw.columns:
        raw = raw[raw["FinInstrmTp"] == "STK"]
    frame = pd.DataFrame(raw[list(_UDIFF)]).rename(columns=_UDIFF)
    for col in ("open", "high", "low", "close"):
        frame[col] = pd.Series(pd.to_numeric(frame[col], errors="coerce"), index=frame.index)
    volume = pd.Series(pd.to_numeric(frame["volume"], errors="coerce"), index=frame.index)
    frame["volume"] = volume.fillna(0).astype("int64")
    frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.date
    frame["source"] = source
    frame["isin"] = frame["isin"].str.strip()
    return pd.DataFrame(frame[EXCHANGE_COLUMNS]).reset_index(drop=True)


def parse_nse_bhavcopy(data: bytes) -> pd.DataFrame:
    """NSE CM bhavcopy (zip or csv) → unadjusted bars for equity series."""
    if data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not names:
                raise PriceSourceError("nse: zip has no csv")
            data = zf.read(names[0])
    frame = _udiff_frame(data.decode("utf-8-sig"), "nse_archives")
    return pd.DataFrame(frame[frame["series"].isin(list(NSE_EQUITY_SERIES))]).reset_index(drop=True)


def parse_bse_bhavcopy(data: bytes) -> pd.DataFrame:
    """BSE CM bhavcopy csv → unadjusted bars (series is the BSE group: A, B, T, …)."""
    return _udiff_frame(data.decode("utf-8-sig"), "bse")


def nse_bhavcopy_url(day: dt.date) -> str:
    return f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{day:%Y%m%d}_F_0000.csv.zip"


def bse_bhavcopy_url(day: dt.date) -> str:
    return f"https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_{day:%Y%m%d}_F_0000.CSV"


@dataclass(frozen=True)
class Listing:
    isin: str
    symbol: str
    name: str
    series: str
    listed_on: dt.date
    face_value_inr: float


def parse_equity_list(data: bytes) -> dict[str, Listing]:
    """NSE EQUITY_L.csv → listing per ISIN (headers carry stray spaces, dates like 06-MAY-2025)."""
    raw = pd.read_csv(io.BytesIO(data), dtype=str)
    raw.columns = [c.strip() for c in raw.columns]
    out = {}
    for row in raw.itertuples(index=False):
        rec: dict[str, Any] = dict(zip(raw.columns, row, strict=True))
        isin = str(rec["ISIN NUMBER"]).strip()
        out[isin] = Listing(
            isin=isin,
            symbol=str(rec["SYMBOL"]).strip(),
            name=str(rec["NAME OF COMPANY"]).strip(),
            series=str(rec["SERIES"]).strip(),
            listed_on=dt.datetime.strptime(str(rec["DATE OF LISTING"]).strip(), "%d-%b-%Y").date(),
            face_value_inr=float(rec["FACE VALUE"]),
        )
    return out


# -- Yahoo ------------------------------------------------------------------------------------
def yahoo_symbol(nse_symbol: str) -> str:
    return f"{nse_symbol}.NS"


def normalize_yahoo(history: pd.DataFrame, isin: str) -> pd.DataFrame:
    """yfinance `history(auto_adjust=False)` output → the store's price frame.

    Rows with no close (Yahoo pads holidays with NaN at times) are dropped, never filled.
    """
    need = {"Open", "High", "Low", "Close", "Adj Close", "Volume"}
    missing = need - set(history.columns)
    if missing:
        raise PriceSourceError(f"yahoo: missing columns {sorted(missing)}")
    idx = pd.DatetimeIndex(history.index)
    if idx.tz is not None:
        idx = idx.tz_convert("Asia/Kolkata").tz_localize(None)
    frame = pd.DataFrame(
        {
            "isin": isin,
            "trade_date": [ts.date() for ts in idx],
            "open": history["Open"].to_numpy(dtype=float),
            "high": history["High"].to_numpy(dtype=float),
            "low": history["Low"].to_numpy(dtype=float),
            "close": history["Close"].to_numpy(dtype=float),
            "adj_close": history["Adj Close"].to_numpy(dtype=float),
            "volume": history["Volume"].fillna(0).to_numpy(dtype="int64"),
            "source": "yfinance",
        }
    )
    frame = frame.dropna(subset=["close"])
    return (
        frame.drop_duplicates(subset=["trade_date"], keep="last")
        .sort_values("trade_date")
        .reset_index(drop=True)
    )


def fetch_yahoo(
    nse_symbol: str, isin: str, start: dt.date, end: dt.date
) -> pd.DataFrame:  # pragma: no cover - network
    """Daily bars from Yahoo, start and end inclusive."""
    import yfinance as yf

    history = yf.Ticker(yahoo_symbol(nse_symbol)).history(
        start=start.isoformat(),
        end=(end + dt.timedelta(days=1)).isoformat(),
        interval="1d",
        auto_adjust=False,
        actions=False,
        raise_errors=True,
    )
    if history.empty:
        raise PriceSourceError(f"yahoo: no rows for {nse_symbol} {start}..{end}")
    return normalize_yahoo(history, isin)


# -- Cross-source check -----------------------------------------------------------------------
@dataclass(frozen=True)
class CloseCheck:
    trade_date: dt.date
    primary_close: float
    exchange_close_adjusted: float
    diff_pct: float
    ok: bool


def cross_check_closes(
    primary: pd.DataFrame,
    exchange: pd.DataFrame,
    actions: Iterable[CorporateAction],
    tolerance_pct: float,
) -> list[CloseCheck]:
    """Compare Yahoo's close with the exchange close back-adjusted to today's share structure.

    Formula: diff % = |yahoo − adjusted exchange| ÷ adjusted exchange × 100, on common dates.
    Pitfall: an unrecorded split or bonus shows up here as a ~50% or ~67% difference on every
    date before the ex-date; that is a missing corporate action, not a bad price.
    """
    exch = {
        d: float(c)
        for d, c in zip(exchange["trade_date"], exchange["close"], strict=True)
        if pd.notna(c)
    }
    adjusted = back_adjust(exch, list(actions))
    checks = []
    for day, close in zip(primary["trade_date"], primary["close"], strict=True):
        if day in adjusted and adjusted[day] > 0:
            diff = abs(float(close) - adjusted[day]) / adjusted[day] * 100
            checks.append(CloseCheck(day, float(close), adjusted[day], diff, diff <= tolerance_pct))
    return checks
