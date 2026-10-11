"""Streamlit AppTest smoke suite: every page and section renders from fixtures, offline (AC-F15.11, F15.12, F22.4)."""

from __future__ import annotations

import socket
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from parakh import config
from tests.conftest import called_from_socketpair
from tests.unit.test_reports import months

APP = Path(__file__).resolve().parents[2] / "app"
PAGES = [
    "Home.py",
    "pages/1_Watchlist_Review.py",
    "pages/2_Holdings.py",
    "pages/3_Segment_Dashboard.py",
    "pages/4_Stock_Detail.py",
    "pages/5_Audit_Governance.py",
    "pages/6_Calibration.py",
    "pages/99_Components.py",
]


@pytest.fixture(scope="module")
def output_root(tmp_path_factory, module_isolation):
    _, _, tmp = months(tmp_path_factory.mktemp("app_pilot"), 3)
    return tmp


@pytest.fixture
def env(output_root, monkeypatch, tmp_path):
    monkeypatch.setenv("PARAKH_OUTPUT_DIR", str(output_root))
    monkeypatch.setenv("PARAKH_WATCH_STATE_DIR", str(tmp_path / "watch"))
    config.get_settings.cache_clear()

    real_connect = socket.socket.connect

    def no_network(self, *a, **k):  # AC-F15.11: nothing may open a connection while a page renders
        # why: on Windows asyncio's event loop connects a socketpair over 127.0.0.1 (same
        # exemption as the global guard in tests/conftest.py); that is not network access
        if called_from_socketpair():
            return real_connect(self, *a, **k)
        raise AssertionError("network access during render")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    yield
    config.get_settings.cache_clear()


def run(page: str) -> AppTest:
    at = AppTest.from_file(str(APP / page), default_timeout=60)
    at.run()
    return at


@pytest.mark.ac("AC-F15.12")
@pytest.mark.ac("AC-F15.11")
@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders_offline(page, env) -> None:
    at = run(page)
    assert not at.exception, [e.value for e in at.exception]


@pytest.mark.ac("AC-F22.4")
def test_the_gallery_renders_every_component(env) -> None:
    from app.ui import components as UI  # noqa: PLC0415

    at = run("pages/99_Components.py")
    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    for token in (
        "OWNED",
        "CONFIRMS",
        "CHALLENGES",
        "FLAGGED",
        "UNKNOWN",
        "BROKEN",
        "NOT SET",
        "MOMENTUM ONLY",
    ):
        assert token in text, token
    assert len(UI.GALLERY) >= 20


@pytest.mark.ac("AC-F15.13")
def test_privacy_view_hides_amounts_on_holdings(env) -> None:
    at = run("pages/2_Holdings.py")
    assert at.toggle(key="privacy").value is True  # masked by default
    frames = [df.value.columns.tolist() for df in at.dataframe]
    assert frames and all("Qty" not in cols and "Value" not in cols for cols in frames)
    at.toggle(key="privacy").set_value(False).run()
    assert not at.exception
    shown = [df.value.columns.tolist() for df in at.dataframe]
    assert any("Qty" in cols for cols in shown)


@pytest.mark.ac("AC-F15.8")
def test_marking_reviewed_is_audited_and_counts_progress(env) -> None:
    from parakh.audit.emit import get_sink
    from parakh.audit.events import AUD

    at = run("Home.py")
    assert not at.exception
    buttons = [b for b in at.button if b.label == "Mark all reviewed"]
    if not buttons:
        pytest.skip("fixture produced no unseen items")
    buttons[0].click().run()
    assert not at.exception
    assert any(e.event_type == AUD.REVIEW_MARKED for e in get_sink().events())
    from parakh.services import app_api

    view = app_api.inbox()
    assert view.total and view.reviewed == view.total and not view.counts
    assert not [b for b in at.button if b.label == "Mark all reviewed"]


@pytest.mark.ac("AC-F15.10")
def test_stock_detail_sections_follow_the_plan_order(env) -> None:
    at = run("pages/4_Stock_Detail.py")
    assert not at.exception
    heads = [m.value for m in at.markdown if m.value.startswith("#####")]
    order = ["Why", "Action box", "Scores", "Thesis", "Checks", "Upcoming events", "Timeline"]
    idx = [next(i for i, h in enumerate(heads) if name in h) for name in order]
    assert idx == sorted(idx)


@pytest.mark.ac("AC-F17.4")
@pytest.mark.ac("AC-F17.5")
def test_calibration_page_saves_a_journal_entry_and_rates_an_alert(env) -> None:
    from parakh.configs import load_all
    from parakh.notify.log import AlertsLog
    from parakh.services import app_api

    AlertsLog(app_api.watch_store().root / "alerts").record(
        {
            "alert_id": "a1",
            "code": "M01",
            "decision": "sent",
            "kind": "signal",
            "isin": "X",
            "symbol": "TCS",
            "asof": "2026-10-01",
        }
    )
    at = run("pages/6_Calibration.py")
    assert not at.exception
    form = at.text_input
    sym = load_all().universe.pilot[0].symbol
    form[0].set_value(sym)
    form[1].set_value("order book up")
    form[2].set_value("beats the index")
    next(b for b in at.button if b.label == "Save").click().run()
    assert not at.exception
    assert len(app_api.journal_service().entries()) == 1
    next(b for b in at.button if "Useful" in b.label).click().run()
    assert app_api.calibration_view().precision["rated"] == 1
