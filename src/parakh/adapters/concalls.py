"""Concall transcripts: Screener's Concalls list → BSE-filed transcript PDF (plan 13 D7).

Ported from Drishti's concall engine (archive/11 §3 row 2): the PDF extractor, the transcript
validator and Q&A-preserving truncation. Changes from Drishti:
- One provider, ScreenerConcallsProvider: the page lists each quarter's "Transcript" link, which
  points at the exchange filing (T1). Drishti's NSE/BSE API providers are dead (404/403).
- The validator returns its reasons, not just True/False, so a rejection is explainable.
- Every candidate is validated and the chain moves on when one fails (Drishti stopped at the
  first "found" source).
- No LLM here. Text is returned as untrusted content with its SHA-256 (AG-06, AC-F24.7).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
from dataclasses import dataclass, field
from urllib.parse import quote

import httpx
from bs4 import BeautifulSoup, Tag

SCREENER = "https://www.screener.in"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)
# Drishti's keyword list: at least MIN_KEYWORDS must appear in a real transcript.
TRANSCRIPT_KEYWORDS = (
    "revenue", "growth", "quarter", "management", "analyst", "guidance", "margin", "board",
    "crore", "ebitda", "profit", "operator", "participants", "conference", "results",
)  # fmt: skip
MIN_CHARS = 2_000  # why: shorter texts were link lists or cover pages in Drishti's live checks
MIN_KEYWORDS = 3
MAX_NON_ASCII_RATIO = 0.15  # why: garbled encodings exceed this
WORD_LEN_RANGE = (3.0, 15.0)  # why: average word length of real English prose
MAX_TRANSCRIPT_CHARS = 48_000
QA_MARKERS = (
    "question and answer", "q&a session", "questions from", "we will now begin",
    "open for questions", "analyst questions", "we will now take questions",
)  # fmt: skip
MONTHS = {
    m: i
    for i, m in enumerate(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1
    )
}


@dataclass(frozen=True)
class ConcallLink:
    """One quarter's row in Screener's Concalls list."""

    period: dt.date  # first day of the call month
    label: str  # "Jul 2026"
    transcript_url: str | None
    ppt_url: str | None = None
    recording_url: str | None = None


@dataclass(frozen=True)
class Validation:
    ok: bool
    reasons: tuple[str, ...] = ()


@dataclass
class Transcript:
    symbol: str
    period: dt.date
    source_url: str  # the Screener "Transcript" link
    final_url: str  # after redirects: bseindia.com/xml-data/corpfiling/AttachHis/…
    sha256: str
    pages: int
    text: str
    validation: Validation
    tier: str = "T1"
    notes: list[str] = field(default_factory=list)


def screener_url(symbol: str, consolidated: bool = True) -> str:
    """Screener company page; the symbol is URL-encoded (M&M → M%26M)."""
    return f"{SCREENER}/company/{quote(symbol, safe='')}/" + (
        "consolidated/" if consolidated else ""
    )


def _period(label: str) -> dt.date | None:
    m = re.fullmatch(r"\s*([A-Z][a-z]{2})\s+(\d{4})\s*", label)
    if not m or m.group(1) not in MONTHS:
        return None
    return dt.date(int(m.group(2)), MONTHS[m.group(1)], 1)


def parse_concalls(html: str) -> list[ConcallLink]:
    """Rows of the Concalls list, newest first. Rows without a transcript are kept (None)."""
    soup = BeautifulSoup(html, "html.parser")
    box = soup.select_one("div.documents.concalls")
    if box is None:
        return []
    links: list[ConcallLink] = []
    for li in box.select("ul.list-links > li"):
        label_div = li.find("div")
        label = label_div.get_text(strip=True) if isinstance(label_div, Tag) else ""
        period = _period(label)
        if period is None:
            continue
        found: dict[str, str | None] = {"Transcript": None, "PPT": None, "REC": None}
        for a in li.find_all("a"):
            text = a.get_text(strip=True)
            href = a.get("href")
            if text in found and isinstance(href, str):
                found[text] = href
        links.append(ConcallLink(period, label, found["Transcript"], found["PPT"], found["REC"]))
    return sorted(links, key=lambda link: link.period, reverse=True)


def validate_transcript(text: str) -> Validation:
    """Drishti's four heuristics, with reasons. All must pass."""
    reasons = []
    if not text or len(text) < MIN_CHARS:
        reasons.append(f"too short ({len(text or '')} chars < {MIN_CHARS})")
        return Validation(False, tuple(reasons))
    lower = text.lower()
    hits = sum(1 for kw in TRANSCRIPT_KEYWORDS if kw in lower)
    if hits < MIN_KEYWORDS:
        reasons.append(f"only {hits} concall keywords (< {MIN_KEYWORDS})")
    non_ascii = sum(1 for c in text if ord(c) > 127) / len(text)
    if non_ascii > MAX_NON_ASCII_RATIO:
        reasons.append(f"non-ASCII ratio {non_ascii:.2f} > {MAX_NON_ASCII_RATIO}")
    words = text.split()[:500]
    if words:
        avg = sum(len(w) for w in words) / len(words)
        if not WORD_LEN_RANGE[0] <= avg <= WORD_LEN_RANGE[1]:
            reasons.append(f"average word length {avg:.1f} outside {WORD_LEN_RANGE}")
    return Validation(not reasons, tuple(reasons))


def truncate_transcript(text: str, max_chars: int = MAX_TRANSCRIPT_CHARS) -> str:
    """Keep the preamble and the whole Q&A when possible; else head 60% + tail 40%."""
    if len(text) <= max_chars:
        return text
    lower = text.lower()
    for marker in QA_MARKERS:
        pos = lower.find(marker)
        if pos > 0:
            preamble = text[: min(pos, max_chars // 3)]
            return (preamble + "\n\n[...]\n\n" + text[pos:])[:max_chars]
    split = int(max_chars * 0.6)
    head, tail = text[:split], text[-(max_chars - split) :]
    last_stop = head.rfind(".")
    if last_stop > split - 200:
        head = head[: last_stop + 1]
    return head + "\n\n[... truncated ...]\n\n" + tail


def pdf_text(pdf: bytes) -> tuple[str, int]:
    """Text and page count via PyMuPDF. OCR for scanned PDFs is deferred (Phase 4, F06)."""
    import pymupdf

    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        pages = [str(page.get_text()) for page in doc]
    return "\n\n".join(pages), len(pages)


class ScreenerConcallsProvider:
    """Finds and fetches filed concall transcripts for one company."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or httpx.Client(
            headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True
        )

    def list_calls(self, symbol: str) -> list[ConcallLink]:
        resp = self.client.get(screener_url(symbol))
        resp.raise_for_status()
        return parse_concalls(resp.text)

    def fetch(self, symbol: str, link: ConcallLink) -> Transcript | None:
        if not link.transcript_url:
            return None
        resp = self.client.get(link.transcript_url)
        if resp.status_code != 200 or not resp.content.startswith(b"%PDF"):
            return None
        text, pages = pdf_text(resp.content)
        return Transcript(
            symbol=symbol,
            period=link.period,
            source_url=link.transcript_url,
            final_url=str(resp.url),
            sha256="sha256:" + hashlib.sha256(resp.content).hexdigest(),
            pages=pages,
            text=text,
            validation=validate_transcript(text),
        )

    def latest_valid(
        self, symbol: str, max_candidates: int = 4
    ) -> tuple[Transcript | None, list[str]]:
        """Newest transcript that passes validation; older calls are tried when one fails.

        Rows without a filed transcript are skipped but logged, so a stale choice is visible:
        MAZDOCK's five newest calls (Feb–Sep 2026) had presentations only (spike ②).
        """
        log: list[str] = []
        calls = self.list_calls(symbol)
        missing = [c.label for c in calls if not c.transcript_url]
        if calls and not calls[0].transcript_url:
            newer = [
                c.label
                for c in calls
                if c.period > next((x.period for x in calls if x.transcript_url), dt.date.min)
            ]
            log.append(f"no filed transcript for the newest call(s): {', '.join(newer)}")
        tried = 0
        for link in (c for c in calls if c.transcript_url):
            if tried >= max_candidates:
                break
            tried += 1
            transcript = self.fetch(symbol, link)
            if transcript is None:
                log.append(f"{link.label}: transcript link did not return a PDF")
                continue
            if transcript.validation.ok:
                log.append(
                    f"{link.label}: ok ({transcript.pages} pages, {len(transcript.text)} chars)"
                )
                if missing and calls[0].period > link.period:
                    transcript.notes.append(
                        f"stale: newest call {calls[0].label} has no filed transcript"
                    )
                return transcript, log
            log.append(f"{link.label}: rejected ({'; '.join(transcript.validation.reasons)})")
        return None, log
