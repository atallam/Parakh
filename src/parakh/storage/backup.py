"""Encrypted logical backups of the Supabase database (plan 10 §11, plan 13 P9).

The Free plan has no backups of its own, so Parakh makes them:
- `dump`: every table in `public` as CSV (Postgres COPY), plus a manifest with row counts,
  per-table sha256 and the applied migration versions, in one tar.gz.
- `encrypt`: age (X25519) to the public keys in config/backup.yaml. Only the matching private
  key (kept by you, outside the repo and the database) can read a backup.
- Stored as `backups/<YYYY-MM-DD>T<HHMM>Z.tar.gz.age` in a private Storage bucket, and pruned to
  12 weekly + 12 monthly (plan 10 §12 retention).
- `restore`: decrypt, then COPY each table back in foreign-key order into a database whose
  schema came from the same migrations. The monthly restore test (Phase 3) uses this.

COPY needs no `pg_dump` binary, so the same code runs on your PC, a GitHub runner or in CI.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import tarfile
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol

import pyrage
from pyrage import x25519

FORMAT_VERSION = 1


class TableSource(Protocol):
    def tables(self) -> list[str]: ...
    def copy_out(self, table: str) -> bytes: ...
    def migrations(self) -> list[str]: ...


class TableTarget(Protocol):
    def copy_in(self, table: str, csv: bytes) -> int: ...


@dataclass(frozen=True)
class BackupInfo:
    name: str
    sha256: str
    bytes: int
    tables: int
    rows: int


def _rows(csv: bytes) -> int:
    """Data rows in a CSV with a header (COPY quotes embedded newlines, so count records)."""
    import csv as csvlib

    return max(0, sum(1 for _ in csvlib.reader(io.StringIO(csv.decode("utf-8")))) - 1)


def dump(source: TableSource, now: dt.datetime) -> tuple[bytes, dict[str, Any]]:
    buf = io.BytesIO()
    manifest: dict[str, Any] = {
        "format": FORMAT_VERSION,
        "created_at": now.isoformat(),
        "migrations": source.migrations(),
        "tables": {},
    }
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for table in source.tables():
            data = source.copy_out(table)
            manifest["tables"][table] = {
                "rows": _rows(data),
                "sha256": "sha256:" + hashlib.sha256(data).hexdigest(),
            }
            info = tarfile.TarInfo(f"{table}.csv")
            info.size = len(data)
            info.mtime = int(now.timestamp())
            tar.addfile(info, io.BytesIO(data))
        body = json.dumps(manifest, indent=1, sort_keys=True).encode()
        info = tarfile.TarInfo("manifest.json")
        info.size = len(body)
        info.mtime = int(now.timestamp())
        tar.addfile(info, io.BytesIO(body))
    return buf.getvalue(), manifest


def encrypt(data: bytes, recipients: Iterable[str]) -> bytes:
    keys = [x25519.Recipient.from_str(r) for r in recipients]
    if not keys:
        raise ValueError("no backup recipients configured (config/backup.yaml)")
    return pyrage.encrypt(data, keys)


def decrypt(data: bytes, identity: str) -> bytes:
    return pyrage.decrypt(data, [x25519.Identity.from_str(identity)])


def read_archive(archive: bytes) -> tuple[dict[str, Any], dict[str, bytes]]:
    files: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        for member in tar.getmembers():
            extracted = tar.extractfile(member)
            if extracted is not None:
                files[member.name] = extracted.read()
    manifest = json.loads(files.pop("manifest.json"))
    for name, data in files.items():
        expected = manifest["tables"][name.removesuffix(".csv")]["sha256"]
        if "sha256:" + hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f"backup corrupted: {name} does not match its manifest hash")
    return manifest, files


def restore(archive: bytes, target: TableTarget, order: list[str]) -> dict[str, int]:
    """Load every table in `order` (parents before children). Returns rows per table."""
    manifest, files = read_archive(archive)
    missing = set(manifest["tables"]) - set(order)
    if missing:
        raise ValueError(f"restore order lacks tables {sorted(missing)}")
    counts = {}
    for table in order:
        if f"{table}.csv" in files:
            counts[table] = target.copy_in(table, files[f"{table}.csv"])
    return counts


def backup_name(now: dt.datetime) -> str:
    return f"{now.astimezone(dt.UTC):%Y-%m-%dT%H%MZ}.tar.gz.age"


def keep_set(names: list[str], weekly: int = 12, monthly: int = 12) -> set[str]:
    """Names to keep: the newest per ISO week (last `weekly` weeks) and the newest per month
    (last `monthly` months). Everything else may be deleted."""
    dated = sorted(
        ((dt.datetime.strptime(n[:16], "%Y-%m-%dT%H%MZ"), n) for n in names), reverse=True
    )
    keep: set[str] = set()
    weeks: dict[tuple[int, int], str] = {}
    months: dict[tuple[int, int], str] = {}
    for when, name in dated:
        iso = when.isocalendar()
        weeks.setdefault((iso.year, iso.week), name)
        months.setdefault((when.year, when.month), name)
    keep.update(list(weeks.values())[:weekly])
    keep.update(list(months.values())[:monthly])
    return keep


def fk_order(edges: list[tuple[str, str]], tables: list[str]) -> list[str]:
    """Tables sorted so each comes after the tables it references (child, parent) edges."""
    parents: dict[str, set[str]] = {t: set() for t in tables}
    for child, parent in edges:
        if child in parents and parent in parents and child != parent:
            parents[child].add(parent)
    order: list[str] = []
    ready = sorted(t for t, p in parents.items() if not p)
    while ready:
        t = ready.pop(0)
        order.append(t)
        for child in sorted(parents):
            if t in parents[child]:
                parents[child].discard(t)
                if not parents[child] and child not in order and child not in ready:
                    ready.append(child)
        ready.sort()
    if len(order) != len(tables):
        raise ValueError("foreign keys form a cycle; cannot order the restore")
    return order


class PostgresTables:  # pragma: no cover - needs a database; exercised by the restore check
    """TableSource/TableTarget over a psycopg connection (schema `public`)."""

    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def tables(self) -> list[str]:
        cur = self.conn.execute(
            "select table_name from information_schema.tables "
            "where table_schema = 'public' and table_type = 'BASE TABLE' order by 1"
        )
        return [r[0] for r in cur.fetchall()]

    def fk_edges(self) -> list[tuple[str, str]]:
        cur = self.conn.execute(
            "select c.conrelid::regclass::text, c.confrelid::regclass::text from pg_constraint c "
            "join pg_namespace n on n.oid = c.connamespace where c.contype = 'f' and n.nspname = 'public'"
        )
        return [(a.removeprefix("public."), b.removeprefix("public.")) for a, b in cur.fetchall()]

    def migrations(self) -> list[str]:
        try:
            cur = self.conn.execute(
                "select version from supabase_migrations.schema_migrations order by 1"
            )
            return [r[0] for r in cur.fetchall()]
        except Exception:
            self.conn.rollback()
            return []

    def copy_out(self, table: str) -> bytes:
        out = bytearray()
        with (
            self.conn.cursor() as cur,
            cur.copy(f'copy public."{table}" to stdout with (format csv, header)') as cp,
        ):
            for chunk in cp:
                out += bytes(chunk)
        return bytes(out)

    def copy_in(self, table: str, csv: bytes) -> int:
        with self.conn.cursor() as cur:
            with cur.copy(f'copy public."{table}" from stdin with (format csv, header)') as cp:
                cp.write(csv)
            return cur.rowcount
