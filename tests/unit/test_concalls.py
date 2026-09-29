"""Concall transcript adapter against recorded fixtures (spike ②; plan 14 §4.2). T-ADP-01…

No network: an httpx MockTransport replays the Screener pages and the BSE-filed PDF captured
on 29 Sep 2026.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import httpx
import pytest

from parakh.adapters.concalls import (
    ScreenerConcallsProvider,
    parse_concalls,
    pdf_text,
    screener_url,
    truncate_transcript,
    validate_transcript,
)

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "sources"
HDFC_HTML = (FIX / "screener" / "HDFCBANK_consolidated_2026-09-29.html").read_text(encoding="utf-8")
MAZDOCK_HTML = (FIX / "screener" / "MAZDOCK_consolidated_2026-09-29.html").read_text(
    encoding="utf-8"
)
PDF = (FIX / "bse" / "HDFCBANK_concall_2026-07_first6pages.pdf").read_bytes()


def test_screener_url_encodes_the_ampersand() -> None:
    """T-ADP-01: M&M is a real pilot symbol (CLAUDE.md: key on ISIN, but URLs need the symbol)."""
    assert screener_url("M&M") == "https://www.screener.in/company/M%26M/consolidated/"


def test_parse_concalls_newest_first_with_bse_links() -> None:
    """T-ADP-02"""
    calls = parse_concalls(HDFC_HTML)
    assert len(calls) >= 20
    assert calls == sorted(calls, key=lambda c: c.period, reverse=True)
    newest = calls[0]
    assert newest.period == dt.date(2026, 7, 1) and newest.label == "Jul 2026"
    assert newest.transcript_url is not None and "bseindia.com" in newest.transcript_url


def test_rows_without_transcripts_are_kept_as_none() -> None:
    """T-ADP-03: MAZDOCK's recent calls list presentations only."""
    calls = parse_concalls(MAZDOCK_HTML)
    assert calls[0].transcript_url is None and calls[0].ppt_url is not None
    assert any(c.transcript_url for c in calls)


def test_filed_pdf_extracts_and_validates() -> None:
    """T-ADP-04"""
    text, pages = pdf_text(PDF)
    assert pages == 6
    result = validate_transcript(text)
    assert result.ok, result.reasons


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("Concalls\nJul 2026 Transcript AI Summary PPT REC\n" * 10, "too short"),
        ("lorem ipsum dolor sit amet " * 200, "keywords"),
        ("revenue quarter margin " + "ÿþ" * 3000, "non-ASCII"),
        ("revenue quarter margin " + "a" * 40 + " " + "x" * 3000, "word length"),
    ],
)
def test_validator_rejects_with_a_reason(text: str, reason: str) -> None:
    """T-ADP-05: a link list, filler text, garbled encoding and run-on tokens."""
    result = validate_transcript(text)
    assert not result.ok
    assert any(reason in r for r in result.reasons)


def test_truncation_keeps_the_qa_section() -> None:
    """T-ADP-06"""
    text = (
        "Opening remarks. " * 3000
        + "We will now begin the question and answer session. "
        + "Q: margins? A: stable. " * 500
    )
    out = truncate_transcript(text, max_chars=20_000)
    assert len(out) <= 20_000
    assert "question and answer" in out and "[...]" in out


def _replay(pages: dict[str, httpx.Response]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        for prefix, response in pages.items():
            if str(request.url).startswith(prefix):
                return response
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_latest_valid_skips_calls_without_transcripts_and_flags_staleness() -> None:
    """T-ADP-07: the MAZDOCK case from spike ②."""
    client = _replay(
        {
            "https://www.screener.in/company/MAZDOCK/": httpx.Response(200, text=MAZDOCK_HTML),
            "https://www.bseindia.com/": httpx.Response(200, content=PDF),
        }
    )
    transcript, log = ScreenerConcallsProvider(client).latest_valid("MAZDOCK")
    assert transcript is not None and transcript.validation.ok
    assert transcript.period < parse_concalls(MAZDOCK_HTML)[0].period
    assert transcript.notes and "stale" in transcript.notes[0]
    assert log[0].startswith("no filed transcript for the newest call")
    assert transcript.sha256.startswith("sha256:") and transcript.tier == "T1"


def test_a_non_pdf_response_moves_on_to_the_next_call() -> None:
    """T-ADP-08: validate each candidate and continue down the chain (archive/11 §3 row 2)."""
    calls = parse_concalls(HDFC_HTML)
    first, second = calls[0].transcript_url, calls[1].transcript_url
    assert first and second

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://www.screener.in/"):
            return httpx.Response(200, text=HDFC_HTML)
        if url == first:
            return httpx.Response(200, text="<html>Access Denied</html>")
        if url == second:
            return httpx.Response(200, content=PDF)
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    transcript, log = ScreenerConcallsProvider(client).latest_valid("HDFCBANK")
    assert transcript is not None and transcript.period == calls[1].period
    assert "did not return a PDF" in log[0]
