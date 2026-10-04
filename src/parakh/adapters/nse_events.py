"""Live NSE feeds for the Event Watcher and the market-context job (implements `EventSource`).

Endpoints, as recorded in `tests/fixtures/sources/nse/` on 2026-10-04:
    corporate-announcements   filings per symbol and date range
    corporates-pit            insider-trading disclosures (promoter trades and pledges)
    reportASM / reportGSM     surveillance lists (today's list, no date)
    snapshot-capital-market-largedeal   bulk and block deals for the last session
    fiidiiTradeReact          FII/FPI and DII cash-market flows
    holiday-master            the trading-holiday calendar

NSE answers only with browser headers, the homepage cookies and a Referer. A 401 or 403 means the
cookies went stale; the client warms up again once and retries. These classes are network-bound, so
the parsers they feed are tested on the recorded responses and the HTTP paths on a mock transport.
"""

from __future__ import annotations

import datetime as dt
import json
import time
from typing import Any

import httpx
import structlog

from parakh.adapters.exchange_http import MIN_INTERVAL_S, _client

log = structlog.get_logger(__name__)
BASE = "https://www.nseindia.com"


def nse_date(day: dt.date) -> str:
    return day.strftime("%d-%m-%Y")


class NseFeeds:
    def __init__(
        self, client: httpx.Client | None = None, min_interval_s: float = MIN_INTERVAL_S
    ) -> None:
        self.client = client or _client()
        self.min_interval_s = min_interval_s
        self._warm = False
        self._last = 0.0

    def _warmup(self) -> None:
        self.client.get(BASE + "/")
        self._warm = True

    def _json(self, path: str, params: dict[str, str] | None = None) -> Any:
        for attempt in (1, 2):
            if not self._warm:
                self._warmup()
            wait = self.min_interval_s - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            resp = self.client.get(
                f"{BASE}/api/{path}",
                params=params or {},
                headers={"Referer": BASE + "/", "Accept": "application/json"},
            )
            if resp.status_code in (401, 403) and attempt == 1:
                self._warm = False
                continue
            resp.raise_for_status()
            return json.loads(resp.text)
        raise RuntimeError("unreachable")  # pragma: no cover

    # -- EventSource -------------------------------------------------------------------------
    def announcements(self, symbol: str, start: dt.date, end: dt.date) -> list[dict[str, Any]]:
        data = self._json(
            "corporate-announcements",
            {
                "index": "equities",
                "symbol": symbol,
                "from_date": nse_date(start),
                "to_date": nse_date(end),
            },
        )
        return data if isinstance(data, list) else []

    def insider(self, symbol: str, start: dt.date, end: dt.date) -> list[dict[str, Any]]:
        data = self._json(
            "corporates-pit",
            {
                "index": "equities",
                "symbol": symbol,
                "from_date": nse_date(start),
                "to_date": nse_date(end),
            },
        )
        return list(data.get("data", [])) if isinstance(data, dict) else []

    def asm(self) -> Any:
        return self._json("reportASM")

    def gsm(self) -> list[dict[str, Any]]:
        data = self._json("reportGSM")
        return data if isinstance(data, list) else []

    def deals(self, day: dt.date) -> list[dict[str, Any]]:
        data = self._json("snapshot-capital-market-largedeal")
        rows: list[dict[str, Any]] = []
        if isinstance(data, dict):
            rows += list(data.get("BULK_DEALS_DATA") or [])
            rows += list(data.get("BLOCK_DEALS_DATA") or [])
        return rows  # the API serves the latest session only; the watcher dedupes by deal

    # -- calendar (monthly email .ics) -------------------------------------------------------
    def event_calendar(self, symbol: str) -> list[dict[str, Any]]:
        data = self._json("event-calendar", {"index": "equities", "symbol": symbol})
        return data if isinstance(data, list) else []

    def board_meetings(self, symbol: str) -> list[dict[str, Any]]:
        data = self._json("corporate-board-meetings", {"index": "equities", "symbol": symbol})
        return data if isinstance(data, list) else []

    def corporate_actions(self, symbol: str) -> list[dict[str, Any]]:
        data = self._json("corporates-corporateActions", {"index": "equities", "symbol": symbol})
        return data if isinstance(data, list) else []

    # -- market context ----------------------------------------------------------------------
    def fii_dii(self) -> list[dict[str, Any]]:
        data = self._json("fiidiiTradeReact")
        return data if isinstance(data, list) else []

    def holiday_master(self) -> Any:
        return self._json("holiday-master", {"type": "trading"})
