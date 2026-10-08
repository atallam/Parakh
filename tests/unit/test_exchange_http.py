"""Bhavcopy archive with a mock transport (no sockets). T-ADP-50…"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import httpx
import pytest

from parakh.adapters.exchange_http import ExchangeArchive

SRC = Path(__file__).resolve().parents[1] / "fixtures" / "sources"
NSE_ZIP = (SRC / "nse" / "BhavCopy_NSE_CM_20260928.csv.zip").read_bytes()
BSE_CSV = (SRC / "bse" / "BhavCopy_BSE_CM_20260928_pilot_and_first40.csv").read_bytes()


def _archive(tmp_path: Path, handler) -> tuple[ExchangeArchive, list[str]]:  # type: ignore[no-untyped-def]
    calls: list[str] = []

    def record(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        return handler(request)

    client = httpx.Client(transport=httpx.MockTransport(record))
    return ExchangeArchive(tmp_path / "raw", client, min_interval_s=0), calls


@pytest.mark.ac("AC-F02.5")
def test_nse_first_then_cached(tmp_path: Path) -> None:
    """T-ADP-50: the second read comes from the raw archive, with its hash recorded once."""
    archive, calls = _archive(tmp_path, lambda r: httpx.Response(200, content=NSE_ZIP))
    day = dt.date(2026, 9, 28)
    first = archive.bars(day)
    second = archive.bars(day)
    assert first is not None and second is not None and len(first) == len(second) > 1000
    assert calls == ["nsearchives.nseindia.com"]
    assert len(archive.fetched) == 1 and archive.fetched[0][2].startswith("sha256:")


def test_bse_when_nse_fails_and_holidays_are_remembered(tmp_path: Path) -> None:
    """T-ADP-51"""

    def handler(request: httpx.Request) -> httpx.Response:
        on_28th = "20260928" in str(request.url)
        if request.url.host.endswith("nseindia.com"):
            return httpx.Response(503 if on_28th else 404)  # an outage vs a real holiday
        return httpx.Response(200, content=BSE_CSV) if on_28th else httpx.Response(404)

    archive, calls = _archive(tmp_path, handler)
    bars = archive.bars(dt.date(2026, 9, 28))
    assert bars is not None and set(bars["source"]) == {"bse"}
    holiday = dt.date(2026, 8, 27)  # a past weekday that both exchanges 404
    assert archive.bars(holiday) is None
    n = len(calls)
    assert archive.bars(holiday) is None and len(calls) == n  # not asked again
    assert archive.bars(dt.date(2026, 9, 26)) is None  # Saturday: no request at all
    assert len(calls) == n


def test_unusable_reply_counts_as_no_file_and_is_not_cached(tmp_path: Path) -> None:
    """T-ADP-52: an error page instead of a bhavcopy must not crash the price load or stay cached."""
    html = b"<html><head><title>Error</title></head>\n<body>\n<p>Service unavailable</p>\n</body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host.endswith("nseindia.com"):
            return httpx.Response(404)
        return httpx.Response(200, content=html)

    archive, _ = _archive(tmp_path, handler)
    day = dt.date(2026, 9, 28)
    assert archive.bars(day) is None
    assert not (tmp_path / "raw" / "bse" / "20260928").exists()
