"""Price history as Parquet, one file per ISIN and year, queried with DuckDB (ADR-004, D11).

Layout: `prices/<ISIN>/<YYYY>.parquet`. The blobs live in Supabase Storage for cloud runs
(`SupabaseBlobs`) or a local folder for dev and tests (`LocalBlobs`); DuckDB reads cached
copies, so a run downloads only the files it needs.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import duckdb
import pandas as pd

PRICE_COLUMNS = [
    "isin",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
    "source",
]


class Blobs(Protocol):
    def put(self, path: str, data: bytes) -> None: ...
    def get(self, path: str) -> bytes | None: ...


class LocalBlobs:
    def __init__(self, root: Path) -> None:
        self.root = root

    def put(self, path: str, data: bytes) -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def get(self, path: str) -> bytes | None:
        target = self.root / path
        return target.read_bytes() if target.exists() else None


class SupabaseBlobs:
    """A Supabase Storage bucket (private). Uses the service key; never exposed to the UI."""

    def __init__(self, client: Any, bucket: str = "prices") -> None:
        self.storage = client.storage
        self.bucket = bucket

    def ensure_bucket(self) -> None:
        names = {b.name for b in self.storage.list_buckets()}
        if self.bucket not in names:
            self.storage.create_bucket(self.bucket, options={"public": False})

    def put(self, path: str, data: bytes) -> None:
        self.storage.from_(self.bucket).upload(
            path, data, {"content-type": "application/octet-stream", "upsert": "true"}
        )

    def get(self, path: str) -> bytes | None:
        try:
            return self.storage.from_(self.bucket).download(path)
        except Exception:  # storage3 raises on 404
            return None


@dataclass(frozen=True)
class WrittenFile:
    """Lineage for one Parquet file (the `price_files` row)."""

    isin: str
    year: int
    path: str
    sha256: str
    rows: int
    first: dt.date
    last: dt.date


def price_path(isin: str, year: int) -> str:
    return f"{isin}/{year}.parquet"


class ParquetPriceStore:
    def __init__(self, blobs: Blobs, cache_dir: Path) -> None:
        self.blobs = blobs
        self.cache = cache_dir
        self.cache.mkdir(parents=True, exist_ok=True)
        self.written: list[WrittenFile] = []

    def write(self, frame: pd.DataFrame) -> list[str]:
        """Write rows grouped by ISIN and year; replaces each touched file whole."""
        missing = set(PRICE_COLUMNS) - set(frame.columns)
        if missing:
            raise ValueError(f"price frame missing columns {sorted(missing)}")
        frame = pd.DataFrame(frame[PRICE_COLUMNS]).copy()
        stamps = pd.to_datetime(frame["trade_date"])
        frame["trade_date"] = stamps.dt.date
        frame["_year"] = stamps.dt.year
        written = []
        for key in sorted(
            {(str(i), int(y)) for i, y in zip(frame["isin"], frame["_year"], strict=True)}
        ):
            isin, year = key
            part = frame[(frame["isin"] == isin) & (frame["_year"] == year)].drop(columns="_year")
            buf = io.BytesIO()
            ordered = pd.DataFrame(part).sort_values(by="trade_date")
            ordered.to_parquet(buf, index=False)
            path = price_path(isin, year)
            self.blobs.put(path, buf.getvalue())
            self.written.append(
                WrittenFile(
                    isin,
                    year,
                    path,
                    "sha256:" + hashlib.sha256(buf.getvalue()).hexdigest(),
                    len(ordered),
                    min(ordered["trade_date"]),
                    max(ordered["trade_date"]),
                )
            )
            (self.cache / path).parent.mkdir(parents=True, exist_ok=True)
            (self.cache / path).write_bytes(buf.getvalue())
            written.append(path)
        return written

    def _local(self, path: str) -> Path | None:
        cached = self.cache / path
        if cached.exists():
            return cached
        data = self.blobs.get(path)
        if data is None:
            return None
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(data)
        return cached

    def query(self, isins: list[str], start: dt.date, end: dt.date) -> pd.DataFrame:
        files = [
            p
            for isin in isins
            for year in range(start.year, end.year + 1)
            if (p := self._local(price_path(isin, year))) is not None
        ]
        if not files:
            return pd.DataFrame(columns=PRICE_COLUMNS)
        con = duckdb.connect()
        try:
            return con.execute(
                "select * from read_parquet(?) where trade_date between ? and ? "
                "order by isin, trade_date",
                [[str(f) for f in files], start, end],
            ).df()
        finally:
            con.close()
