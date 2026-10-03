"""ics, email message and ntfy (AC-F11.10, F11.11)."""

from __future__ import annotations

import datetime as dt

import httpx

from parakh.notify.email import build_message
from parakh.notify.ics import CalEntry, build_ics
from parakh.notify.ntfy import NtfyClient


def test_ics_is_valid_crlf_and_escaped() -> None:
    data = build_ics(
        [CalEntry(dt.date(2026, 11, 5), "M&M, board; meeting", "board", "Results, with; commas")],
        stamp=dt.datetime(2026, 10, 5, tzinfo=dt.UTC),
    ).decode()
    assert data.startswith("BEGIN:VCALENDAR\r\n") and data.endswith("END:VCALENDAR\r\n")
    assert "DTSTART;VALUE=DATE:20261105" in data and "DTEND;VALUE=DATE:20261106" in data
    assert "SUMMARY:M&M\\, board\\; meeting" in data
    assert all(len(line.encode()) <= 75 for line in data.split("\r\n"))


def test_ics_folds_long_lines_and_uid_is_stable() -> None:
    e = CalEntry(dt.date(2026, 11, 5), "x" * 200)
    out = build_ics([e], stamp=dt.datetime(2026, 10, 5, tzinfo=dt.UTC)).decode()
    assert all(len(line.encode()) <= 75 for line in out.split("\r\n"))
    assert e.uid == CalEntry(dt.date(2026, 11, 5), "x" * 200).uid


def test_email_has_html_text_and_ics() -> None:
    msg = build_message(
        "a@x", "b@x", "Subj", "<b>hi</b>", "hi", [("r.ics", b"BEGIN", "text/calendar")]
    )
    kinds = [p.get_content_type() for p in msg.walk()]
    assert "text/plain" in kinds and "text/html" in kinds and "text/calendar" in kinds
    assert msg["Subject"] == "Subj"


def test_ntfy_ok_and_failure() -> None:
    seen = {}

    def ok(req: httpx.Request) -> httpx.Response:
        seen["h"] = dict(req.headers)
        return httpx.Response(200)

    c = NtfyClient("https://ntfy.sh", "t", httpx.Client(transport=httpx.MockTransport(ok)))
    assert c.send("INDIGO M21", "x").ok and seen["h"]["priority"] == "high"
    bad = NtfyClient(
        "https://ntfy.sh",
        "t",
        httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))),
    )
    assert not bad.send("a", "b").ok
