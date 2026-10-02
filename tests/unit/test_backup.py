"""Encrypted backups: archive, encryption, integrity, restore order, retention. T-BAK-01…"""

from __future__ import annotations

import datetime as dt

import pyrage
import pytest
from pyrage import x25519

from parakh.storage.backup import (
    backup_name,
    decrypt,
    dump,
    encrypt,
    fk_order,
    keep_set,
    read_archive,
    restore,
)

NOW = dt.datetime(2026, 10, 4, 3, 30, tzinfo=dt.UTC)


class FakeDb:
    def __init__(self, data: dict[str, bytes]) -> None:
        self.data = data
        self.loaded: list[str] = []

    def tables(self) -> list[str]:
        return sorted(self.data)

    def copy_out(self, table: str) -> bytes:
        return self.data[table]

    def migrations(self) -> list[str]:
        return ["20260929000000", "20261001000000"]

    def copy_in(self, table: str, csv: bytes) -> int:
        self.loaded.append(table)
        self.data[table] = csv
        return csv.count(b"\n") - 1


DATA = {
    "securities": b"isin,symbol\nINE101A01026,M&M\nINE040A01034,HDFCBANK\n",
    "fundamentals": b'isin,metric_id,value\nINE101A01026,"annual_pl.Sales",1.0\n',
    "holdings_lots": b'lot_id,note\n01K0,"two\nlines"\n',
}


def test_round_trip_is_encrypted_and_verified() -> None:
    """T-BAK-01: only the private key reads it; the manifest carries counts and hashes."""
    key = x25519.Identity.generate()
    archive, manifest = dump(FakeDb(dict(DATA)), NOW)
    sealed = encrypt(archive, [str(key.to_public())])
    assert b"INE101A01026" not in sealed and b"holdings" not in sealed
    assert manifest["tables"]["holdings_lots"]["rows"] == 1  # quoted newline is one record
    assert manifest["migrations"][-1] == "20261001000000"
    m2, files = read_archive(decrypt(sealed, str(key)))
    assert m2 == manifest and files["securities.csv"] == DATA["securities"]
    with pytest.raises(pyrage.DecryptError):
        decrypt(sealed, str(x25519.Identity.generate()))


def test_a_tampered_archive_is_refused() -> None:
    """T-BAK-02"""
    import io
    import tarfile

    archive, _ = dump(FakeDb(dict(DATA)), NOW)
    files = {}
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        for m in tar.getmembers():
            f = tar.extractfile(m)
            assert f is not None
            files[m.name] = f.read()
    files["securities.csv"] = files["securities.csv"].replace(b"HDFCBANK", b"HACKED")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    with pytest.raises(ValueError, match="corrupted"):
        read_archive(buf.getvalue())


def test_restore_loads_parents_first() -> None:
    """T-BAK-03"""
    archive, _ = dump(FakeDb(dict(DATA)), NOW)
    order = fk_order(
        [("fundamentals", "securities"), ("holdings_lots", "securities")],
        ["holdings_lots", "fundamentals", "securities"],
    )
    assert order[0] == "securities"
    target = FakeDb({})
    counts = restore(archive, target, order)
    assert target.loaded == order and counts["securities"] == 2
    with pytest.raises(ValueError, match="lacks"):
        restore(archive, FakeDb({}), ["securities"])


def test_retention_keeps_12_weekly_and_12_monthly() -> None:
    """T-BAK-04 (plan 10 §12): two years of weekly backups → 12 + the older month-ends."""
    names = [backup_name(NOW - dt.timedelta(weeks=w)) for w in range(104)]
    keep = keep_set(names)
    newest_12 = set(names[:12])
    assert newest_12 <= keep
    assert 12 < len(keep) <= 24
    assert backup_name(NOW).startswith("2026-10-04T0330Z")


def test_backup_job_uploads_prunes_and_audits(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """T-BAK-05: AUD.BACKUP.COMPLETED carries the hash; old backups beyond retention go."""
    import dataclasses

    from parakh.audit.emit import get_sink
    from parakh.audit.events import AUD
    from parakh.configs import load_all
    from parakh.orchestration.backup import run_backup
    from parakh.storage.prices import LocalBlobs

    key = x25519.Identity.generate()
    bundle = load_all()
    bundle = dataclasses.replace(
        bundle, backup=bundle.backup.model_copy(update={"recipients": [str(key.to_public())]})
    )
    blobs = LocalBlobs(tmp_path)
    for w in range(1, 40):  # 39 older weekly backups already stored
        blobs.put(backup_name(NOW - dt.timedelta(weeks=w)), b"old")
    ctx, outcome, info = run_backup(bundle, FakeDb(dict(DATA)), blobs, now=NOW)
    assert info is not None and info.rows == 4 and info.tables == 3
    names = blobs.list()
    assert info.name in names and len(names) <= 24
    data = blobs.get(info.name)
    assert data is not None and read_archive(decrypt(data, str(key)))[0]["tables"]
    done = [
        e for e in get_sink().events_for_run(ctx.run_id) if e.event_type == AUD.BACKUP_COMPLETED
    ]
    assert len(done) == 1 and done[0].evidence_ref == info.sha256


def test_private_keys_are_refused_in_config() -> None:
    """T-BAK-06"""
    from parakh.configs.models import BackupConfig

    good = str(x25519.Identity.generate().to_public())
    BackupConfig(
        recipients=[good], pooler_host="h", bucket="backups", keep_weekly=12, keep_monthly=12
    )
    with pytest.raises(ValueError, match="private keys"):
        BackupConfig(
            recipients=[str(x25519.Identity.generate())],
            pooler_host="h",
            bucket="backups",
            keep_weekly=12,
            keep_monthly=12,
        )
