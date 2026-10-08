"""HTTP access to NSE and BSE: bhavcopies (cached raw archive) and the corporate-actions API.

Findings from spike ① that shape this:
- nsearchives.nseindia.com serves bhavcopy zips to a plain GET with browser headers; a missing
  day (holiday, weekend, not yet published) is a 404.
- www.nseindia.com/api/* needs the homepage cookies first and a Referer header.
- BSE serves the same UDiFF CSV; it's the fallback when NSE fails for a day.
- Reachable from GitHub runners and your PC; this cloud workspace gets 403 from NSE.

Raw files are kept under `state/raw/<source>/` (plan 10 §13 raw-input archive, 24 months), so a
re-run reads the same bytes and each file's sha256 can be cited in lineage.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import structlog

from parakh.adapters.prices import (
    bse_bhavcopy_url,
    nse_bhavcopy_url,
    parse_bse_bhavcopy,
    parse_nse_bhavcopy,
)
from parakh.adapters.xbrl import Filing, parse_financial_results, parse_integrated_filings

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "text/html,application/json,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
}
log = structlog.get_logger(__name__)

# why: be a polite client of public exchange sites; ~3 requests a second at most
MIN_INTERVAL_S = 0.35


def _client() -> httpx.Client:
    return httpx.Client(headers=BROWSER_HEADERS, timeout=30, follow_redirects=True)


class ExchangeArchive:
    """Bhavcopy per day: cache → NSE → BSE. `bars(day)` returns None when neither has the day."""

    def __init__(
        self,
        raw_dir: Path,
        client: httpx.Client | None = None,
        min_interval_s: float = MIN_INTERVAL_S,
        use_bse: bool = True,
    ) -> None:
        self.raw_dir = raw_dir
        self.client = client or _client()
        self.min_interval_s = min_interval_s
        self.use_bse = use_bse
        self._last = 0.0
        self.fetched: list[tuple[str, str, str]] = []  # (source, path, sha256) for lineage

    def _get(self, url: str, **kwargs: Any) -> httpx.Response:
        wait = self.min_interval_s - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        return self.client.get(url, **kwargs)

    def _raw(
        self, source: str, day: dt.date, url: str, headers: dict[str, str] | None = None
    ) -> bytes | None:
        path = self.raw_dir / source / f"{day:%Y%m%d}"
        missing = path.with_suffix(".missing")
        if path.exists():
            return path.read_bytes()
        if missing.exists():
            return None
        resp = self._get(url, headers=headers or {})
        if resp.status_code == 404:
            if day < dt.date.today():  # only a past day's absence is final
                missing.parent.mkdir(parents=True, exist_ok=True)
                missing.touch()
            return None
        resp.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(resp.content)
        self.fetched.append(
            (source, str(path), "sha256:" + hashlib.sha256(resp.content).hexdigest())
        )
        return resp.content

    def _discard(self, source: str, day: dt.date) -> None:
        """Drop a cached download that does not parse, so the next run asks the exchange again."""
        (self.raw_dir / source / f"{day:%Y%m%d}").unlink(missing_ok=True)

    def bars(self, day: dt.date) -> pd.DataFrame | None:
        if day.weekday() >= 5:
            return None
        try:
            data = self._raw("nse", day, nse_bhavcopy_url(day))
            if data is not None:
                return parse_nse_bhavcopy(data)
        except httpx.HTTPError:
            if not self.use_bse:
                raise
        except ValueError as exc:
            # why: a reply that is not a bhavcopy (an error page, a half-published file) means "no
            # usable file for that day", the same as a 404. The cross-check then warns instead of
            # the whole price load crashing.
            self._discard("nse", day)
            log.warning(
                "exchange.bhavcopy_unusable",
                source="nse",
                day=day.isoformat(),
                error=str(exc)[:120],
            )
        if self.use_bse:
            try:
                data = self._raw(
                    "bse", day, bse_bhavcopy_url(day), {"Referer": "https://www.bseindia.com/"}
                )
                if data is not None:
                    return parse_bse_bhavcopy(data)
            except ValueError as exc:
                self._discard("bse", day)
                log.warning(
                    "exchange.bhavcopy_unusable",
                    source="bse",
                    day=day.isoformat(),
                    error=str(exc)[:120],
                )
        return None


class NseApi:  # pragma: no cover - network; parsers are tested on recorded responses
    """www.nseindia.com JSON APIs (cookies from the homepage first)."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or _client()
        self._warm = False

    def _json(
        self, path: str, params: dict[str, str], referer: str = "https://www.nseindia.com/"
    ) -> Any:
        if not self._warm:
            self.client.get("https://www.nseindia.com/")
            self._warm = True
        resp = self.client.get(
            f"https://www.nseindia.com/api/{path}",
            params=params,
            headers={"Referer": referer, "Accept": "application/json"},
        )
        resp.raise_for_status()
        return json.loads(resp.text)

    def corporate_actions(self, symbol: str) -> list[dict[str, Any]]:
        data = self._json("corporates-corporateActions", {"index": "equities", "symbol": symbol})
        return data if isinstance(data, list) else []

    def shareholding_master(self, symbol: str) -> list[dict[str, Any]]:
        data = self._json(
            "corporate-share-holdings-master",
            {"index": "equities", "symbol": symbol},
            referer="https://www.nseindia.com/companies-listing/corporate-filings-shareholding-pattern",
        )
        return data if isinstance(data, list) else []

    def shareholding_xbrl(self, url: str) -> str:
        """Fetched, parsed and dropped: the file names holders above 1%, so it is not archived."""
        if not self._warm:
            self.client.get("https://www.nseindia.com/")
            self._warm = True
        resp = self.client.get(url)
        resp.raise_for_status()
        return resp.text

    def equity_list(self) -> bytes:
        resp = self.client.get("https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv")
        resp.raise_for_status()
        return resp.content


class NseFilings:  # pragma: no cover - network; parsers are tested on recorded responses
    """FilingsSource over both NSE result feeds (to Dec 2024, and integrated filings after)."""

    def __init__(self, api: NseApi, raw_dir: Path | None = None) -> None:
        self.api = api
        self.raw_dir = raw_dir

    def filings(self, symbol: str) -> list[Filing]:
        old = self.api._json(
            "corporates-financial-results",
            {"index": "equities", "symbol": symbol, "period": "Quarterly"},
        )
        new = self.api._json(
            "integrated-filing-results",
            {"index": "equities", "symbol": symbol, "type": "Integrated Filing- Financials"},
            referer="https://www.nseindia.com/companies-listing/corporate-integrated-filing",
        )
        return parse_financial_results(
            old if isinstance(old, list) else []
        ) + parse_integrated_filings(new if isinstance(new, dict) else {})

    def xbrl(self, url: str) -> str:
        name = url.rsplit("/", 1)[-1]
        cached = self.raw_dir / "xbrl" / name if self.raw_dir else None
        if cached and cached.exists():
            return cached.read_text(encoding="utf-8")
        resp = self.api.client.get(url)
        resp.raise_for_status()
        if cached:
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_text(resp.text, encoding="utf-8")
        return resp.text
