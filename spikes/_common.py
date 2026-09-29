"""Shared helpers for the spikes: a polite HTTP client and a result recorder."""

from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "spikes" / "out"
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": BROWSER_UA,
    "Accept": "text/html,application/json,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
}


def client(**kwargs: Any) -> httpx.Client:
    return httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True, **kwargs)


def recent_weekdays(n: int = 6, today: dt.date | None = None) -> list[dt.date]:
    day = today or dt.date.today()
    out = []
    while len(out) < n:
        day -= dt.timedelta(days=1)
        if day.weekday() < 5:
            out.append(day)
    return out


class Recorder:
    """Collects one row per probe and writes results.json plus sample files."""

    def __init__(self, spike: str) -> None:
        self.dir = OUT / spike
        self.dir.mkdir(parents=True, exist_ok=True)
        self.rows: list[dict[str, Any]] = []

    def probe(self, name: str, fn: Any, *, sample_name: str | None = None) -> Any:
        start = time.perf_counter()
        row: dict[str, Any] = {"probe": name}
        try:
            resp = fn()
            row.update(
                status=resp.status_code,
                content_type=resp.headers.get("content-type", ""),
                bytes=len(resp.content),
                final_url=str(resp.url),
            )
            if sample_name and resp.status_code == 200 and resp.content:
                (self.dir / sample_name).write_bytes(resp.content[:2_000_000])
                row["sample"] = sample_name
            row["ok"] = resp.status_code == 200 and len(resp.content) > 200
            return resp
        except Exception as exc:  # spikes record failures, they don't raise
            row.update(ok=False, error=f"{type(exc).__name__}: {exc}"[:300])
            return None
        finally:
            row["ms"] = round((time.perf_counter() - start) * 1000)
            self.rows.append(row)
            print(json.dumps(row))

    def note(self, **fields: Any) -> None:
        self.rows.append(fields)
        print(json.dumps(fields, default=str))

    def save(self) -> None:
        (self.dir / "results.json").write_text(
            json.dumps(self.rows, indent=2, default=str), encoding="utf-8"
        )
