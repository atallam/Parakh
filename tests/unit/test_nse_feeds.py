"""NseFeeds on a mock transport: warm-up, Referer, stale-cookie retry, response shapes."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import httpx

from parakh.adapters.nse_events import NseFeeds, nse_date

FIX = Path(__file__).parent.parent / "fixtures" / "sources" / "nse"


def _feeds(handler):  # type: ignore[no-untyped-def]
    return NseFeeds(httpx.Client(transport=httpx.MockTransport(handler)), min_interval_s=0)


def test_warms_up_then_sends_referer_and_dates() -> None:
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.url.path == "/":
            return httpx.Response(200, text="home")
        return httpx.Response(
            200,
            text=(FIX / "announcements_INDIGO_2026-10-04_sample.json").read_text(encoding="utf-8"),
        )

    rows = _feeds(handler).announcements("INDIGO", dt.date(2026, 10, 1), dt.date(2026, 10, 4))
    assert len(rows) == 50 and seen[0].url.path == "/"
    api = seen[1]
    assert api.headers["referer"].startswith(
        "https://www.nseindia.com"
    ) and "from_date=01-10-2026" in str(api.url)


def test_stale_cookies_warm_up_again_once() -> None:
    calls = {"api": 0, "home": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/":
            calls["home"] += 1
            return httpx.Response(200)
        calls["api"] += 1
        return httpx.Response(403) if calls["api"] == 1 else httpx.Response(200, text="[]")

    assert _feeds(handler).gsm() == []
    assert calls == {"api": 2, "home": 2}


def test_persistent_403_raises() -> None:
    import pytest

    f = _feeds(lambda r: httpx.Response(200) if r.url.path == "/" else httpx.Response(403))
    with pytest.raises(httpx.HTTPStatusError):
        f.gsm()


def test_shapes_insider_asm_deals_flows() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        files = {
            "/api/corporates-pit": "pit_HDFCBANK_2026-10-04.json",
            "/api/reportASM": "asm_2026-10-04.json",
            "/api/snapshot-capital-market-largedeal": "large_deals_2026-10-01.json",
            "/api/fiidiiTradeReact": "fii_dii_2026-10-01.json",
        }
        if p in files:
            return httpx.Response(200, text=(FIX / files[p]).read_text(encoding="utf-8"))
        return httpx.Response(200)

    f = _feeds(handler)
    assert (
        f.insider("HDFCBANK", dt.date(2026, 9, 1), dt.date(2026, 10, 4))[0]["symbol"] == "HDFCBANK"
    )
    assert "longterm" in f.asm()
    assert f.deals(dt.date(2026, 10, 1))[0]["buySell"] in ("BUY", "SELL")
    assert {r["category"] for r in f.fii_dii()} == {"DII", "FII/FPI"}
    assert nse_date(dt.date(2026, 1, 5)) == "05-01-2026"
    json.dumps(f.asm())
