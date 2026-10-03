"""A small, valid iCalendar writer for the monthly email (AC-F11.11).

    ics = build_ics([CalEntry(date(2026,11,5), "INDIGO: board meeting (results)", "BM-INDIGO-…")])

All-day events, CRLF line endings, 75-octet folding, escaped text. No time zones are needed
because the entries are dates.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class CalEntry:
    day: dt.date
    title: str
    kind: str = "event"  # results | board | exdate | event
    detail: str = ""

    @property
    def uid(self) -> str:
        h = hashlib.sha256(f"{self.day}|{self.kind}|{self.title}".encode()).hexdigest()[:20]
        return f"{h}@parakh.local"


def _esc(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r", "")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> list[str]:
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return [line]
    out: list[str] = []
    cur = b""
    for ch in line:
        b = ch.encode("utf-8")
        limit = 75 if not out else 74  # continuation lines start with one space
        if len(cur) + len(b) > limit:
            out.append(cur.decode("utf-8"))
            cur = b""
        cur += b
    out.append(cur.decode("utf-8"))
    return [out[0], *(" " + p for p in out[1:])]


def build_ics(entries: list[CalEntry], *, stamp: dt.datetime | None = None) -> bytes:
    now = (stamp or dt.datetime.now(dt.UTC)).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Parakh//Monthly review//EN",
        "CALSCALE:GREGORIAN",
    ]
    for e in sorted(entries, key=lambda x: (x.day, x.title)):
        lines += [
            "BEGIN:VEVENT",
            f"UID:{e.uid}",
            f"DTSTAMP:{now}",
            f"DTSTART;VALUE=DATE:{e.day.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{(e.day + dt.timedelta(days=1)).strftime('%Y%m%d')}",
            f"SUMMARY:{_esc(e.title)}",
        ]
        if e.detail:
            lines.append(f"DESCRIPTION:{_esc(e.detail)}")
        lines += [f"CATEGORIES:{_esc(e.kind.upper())}", "TRANSP:TRANSPARENT", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    folded: list[str] = []
    for ln in lines:
        folded.extend(_fold(ln))
    return ("\r\n".join(folded) + "\r\n").encode("utf-8")
