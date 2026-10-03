"""Event Watcher on real NSE responses (fixtures): rules, once-only, failures (AC-F13.1–F13.4)."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from parakh.watch.events import EventWatcher, match_announcement, match_insider, parse_nse_date
from parakh.watch.momentum import Held
from parakh.watch.state import StateStore
from tests.helpers.notify import bundle

FIX = Path(__file__).parent.parent / "fixtures" / "sources" / "nse"


def _load(name: str) -> Any:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


class FixtureSource:
    def __init__(
        self, fail: str | None = None, extra_asm: Any = None, extra_deals: Any = None
    ) -> None:
        self.rows = _load("announcements_INDIGO_2026-10-04_sample.json")
        self.fail, self.extra_asm, self.extra_deals = fail, extra_asm, extra_deals
        self.insider_rows: list[dict[str, Any]] = []

    def announcements(self, symbol, start, end):  # type: ignore[no-untyped-def]
        if self.fail == "announcements":
            raise TimeoutError("nse down")
        return [r for r in self.rows if r["symbol"] == symbol]

    def insider(self, symbol, start, end):  # type: ignore[no-untyped-def]
        return self.insider_rows

    def asm(self):  # type: ignore[no-untyped-def]
        return self.extra_asm if self.extra_asm is not None else _load("asm_2026-10-04.json")

    def gsm(self):  # type: ignore[no-untyped-def]
        return _load("gsm_2026-10-04.json")

    def deals(self, day):  # type: ignore[no-untyped-def]
        return self.extra_deals or []


def _setup(tmp_path, held=None):  # type: ignore[no-untyped-def]
    b = bundle()
    indigo = next(s for s in b.universe.pilot if s.symbol == "INDIGO")
    return EventWatcher(b, StateStore(tmp_path), held or {}), indigo, b


def _codes(res) -> list[str]:  # type: ignore[no-untyped-def]
    return sorted(a.code for a in res.alerts)


def test_credit_rating_is_medium_event(tmp_path) -> None:  # type: ignore[no-untyped-def]
    w, indigo, _ = _setup(tmp_path)
    res = w.scan(dt.date(2026, 9, 26), [indigo], FixtureSource())
    assert _codes(res) == ["E07"] and res.alerts[0].severity.value == "Medium"


def test_generic_resignation_fails_loud_as_high(tmp_path) -> None:  # type: ignore[no-untyped-def]
    w, indigo, _ = _setup(tmp_path)
    res = w.scan(dt.date(2026, 7, 1), [indigo], FixtureSource())
    assert "E13" in _codes(res)
    by_desc = {a.extra["desc"]: a.severity.value for a in res.alerts if a.code == "E13"}
    assert by_desc["Resignation of Director/KMP/SMP"] == "High"
    assert by_desc["Change in Management"] == "Medium"


def test_results_once_per_period_and_refresh(tmp_path) -> None:  # type: ignore[no-untyped-def]
    w, indigo, _ = _setup(tmp_path)
    res = w.scan(dt.date(2026, 7, 24), [indigo], FixtureSource())
    assert _codes(res).count("E01") == 1
    assert res.refresh_isins == [indigo.isin]


def test_transcript_triggers_refresh(tmp_path) -> None:  # type: ignore[no-untyped-def]
    w, indigo, _ = _setup(tmp_path)
    res = w.scan(dt.date(2026, 7, 30), [indigo], FixtureSource())
    assert "E02" in _codes(res) and indigo.isin in res.refresh_isins


def test_each_filing_alerts_exactly_once(tmp_path) -> None:  # type: ignore[no-untyped-def]
    w, indigo, _ = _setup(tmp_path)
    first = w.scan(dt.date(2026, 9, 26), [indigo], FixtureSource())
    again = EventWatcher(w.bundle, StateStore(tmp_path)).scan(
        dt.date(2026, 9, 26), [indigo], FixtureSource()
    )
    assert first.alerts and again.alerts == []


def test_failed_source_is_reported_and_retried(tmp_path) -> None:  # type: ignore[no-untyped-def]
    w, indigo, _ = _setup(tmp_path)
    bad = w.scan(dt.date(2026, 9, 26), [indigo], FixtureSource(fail="announcements"))
    assert "announcements:INDIGO" in bad.errors and bad.alerts == []
    good = w.scan(dt.date(2026, 9, 26), [indigo], FixtureSource())
    assert _codes(good) == ["E07"], "the filing was not marked seen by the failed run"


def test_owned_stock_carries_position_percentages(tmp_path) -> None:  # type: ignore[no-untyped-def]
    b = bundle()
    indigo = next(s for s in b.universe.pilot if s.symbol == "INDIGO")
    w = EventWatcher(b, StateStore(tmp_path), {indigo.isin: Held(12.0, 18.4)})
    res = w.scan(dt.date(2026, 9, 26), [indigo], FixtureSource())
    assert res.alerts[0].owned and res.alerts[0].weight_pct == 12.0


def test_promoter_trade_and_pledge_rules() -> None:
    rules = bundle().events.rules
    buy = {
        "personCategory": "Promoter Group",
        "acqMode": "Market Purchase",
        "tdpTransactionType": "Buy",
        "did": "1",
    }
    pledge = {"personCategory": "Promoters", "acqMode": "Pledge Creation", "did": "2"}
    revoke = {"personCategory": "Promoters", "acqMode": "Pledge", "remarks": "Revoked", "did": "3"}
    other = {"personCategory": "Other", "acqMode": "Market Sale", "did": "4"}
    m = match_insider(rules, buy)
    assert m and m.rule.id == "E03" and m.valence == "positive"
    m = match_insider(rules, pledge)
    assert m and m.rule.id == "E06" and m.severity.value == "High"
    m = match_insider(rules, revoke)
    assert m and m.rule.id == "E06" and m.severity.value == "Medium" and m.valence == "positive"
    assert match_insider(rules, other) is None


def test_auditor_exit_vs_appointment() -> None:
    rules = bundle().events.rules
    gen = {
        "desc": "Change in Auditors",
        "attchmntText": "X has informed the Exchange regarding Change in Auditors of the company.",
        "seq_id": "1",
    }
    appt = {
        "desc": "Change in Auditors",
        "attchmntText": "Appointment of M/s KPSJ as statutory auditor",
        "seq_id": "2",
    }
    assert match_announcement(rules, gen).rule.id == "E04"  # type: ignore[union-attr]
    assert match_announcement(rules, appt).rule.id == "E12"  # type: ignore[union-attr]


def test_surveillance_and_deals_and_lockin(tmp_path) -> None:  # type: ignore[no-untyped-def]
    w, indigo, b = _setup(tmp_path)
    asm = {
        "longterm": {"data": [{"symbol": "INDIGO", "asmSurvIndicator": "Stage I"}]},
        "shortterm": {"data": []},
    }
    deals = [
        {
            "symbol": "INDIGO",
            "buySell": "BUY",
            "qty": "100000",
            "watp": "5000",
            "clientName": "ABC FUND",
            "date": "02-Oct-2026",
        }
    ]
    young = indigo.model_copy(update={"listed_on": dt.date(2026, 10, 5) - dt.timedelta(days=25)})
    res = w.scan(dt.date(2026, 10, 5), [young], FixtureSource(extra_asm=asm, extra_deals=deals))
    assert {"E08", "E10", "E11"} <= set(_codes(res))
    e8 = next(a for a in res.alerts if a.code == "E08")
    assert e8.severity.value == "High"


def test_old_listing_has_no_lockin(tmp_path) -> None:  # type: ignore[no-untyped-def]
    w, indigo, _ = _setup(tmp_path)
    res = w.scan(dt.date(2026, 10, 5), [indigo], FixtureSource())
    assert "E11" not in _codes(res)


def test_nse_dates() -> None:
    assert parse_nse_date("25-Sep-2026 19:37:53") == dt.date(2026, 9, 25)
    assert parse_nse_date("25-Sep-2026") == dt.date(2026, 9, 25)
    assert parse_nse_date("-") is None
