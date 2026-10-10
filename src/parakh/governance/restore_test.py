"""Backup restore test: prove the newest backup can actually be read back (plan 10 §11; NFR-14).

    result = run_restore_test(bundle, blobs, identity, now=now, target=scratch_db, order=order)

A backup nobody has restored is a hope. The monthly job takes the newest archive, checks it is recent
enough (`restore.max_backup_age_days`), decrypts it with the private key, verifies every table against
the manifest hash and, when a scratch database is given, loads it there and compares row counts with the
manifest (`restore.min_rows_ratio`). Without a scratch database it still proves the key, the archive and
the hashes, and the result says the table load was not exercised. It never writes to the live database.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, field
from typing import Any

from parakh.audit.context import RunContext
from parakh.audit.emit import AuditSink, get_sink
from parakh.audit.events import AUD
from parakh.audit.steps import audited_step, run_lifecycle
from parakh.configs import ConfigBundle
from parakh.storage.backup import TableTarget, decrypt, read_archive, restore
from parakh.storage.prices import Blobs

SUFFIX = ".tar.gz.age"


@dataclass
class RestoreResult:
    status: str = "fail"  # pass | fail
    backup: str | None = None
    age_days: float | None = None
    tables: int = 0
    manifest_rows: int = 0
    restored_rows: int | None = None  # None: no scratch database was given
    problems: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_restore_test(
    bundle: ConfigBundle,
    blobs: Blobs,
    identity: str,
    *,
    now: dt.datetime,
    target: TableTarget | None = None,
    order: list[str] | None = None,
    sink: AuditSink | None = None,
) -> tuple[RunContext, RestoreResult]:
    sink = sink or get_sink()
    cfg = bundle.calibration.restore
    res = RestoreResult()
    ctx = RunContext.create(mode="restore_test", actor_type="ci", actor_id="restore-test")
    with run_lifecycle(ctx, sink) as outcome:
        with audited_step(ctx, "find_backup") as step:
            names = sorted(n for n in blobs.list() if n.endswith(SUFFIX))
            if not names:
                res.problems.append("no backup found")
            else:
                res.backup = names[-1]
                when = dt.datetime.strptime(res.backup[:16], "%Y-%m-%dT%H%MZ").replace(
                    tzinfo=dt.UTC
                )
                res.age_days = (now - when).total_seconds() / 86400
                if res.age_days > cfg.max_backup_age_days:
                    res.problems.append(
                        f"newest backup is {res.age_days:.0f} days old; "
                        f"the limit is {cfg.max_backup_age_days}"
                    )
            step.record_output(backup=res.backup, age_days=res.age_days)
        if res.backup:
            with audited_step(ctx, "verify_archive") as step:
                try:
                    sealed = blobs.get(res.backup)
                    if sealed is None:
                        raise ValueError("the backup listed could not be downloaded")
                    manifest, _files = read_archive(decrypt(sealed, identity))
                    res.tables = len(manifest["tables"])
                    res.manifest_rows = sum(t["rows"] for t in manifest["tables"].values())
                    if target is not None and order is not None:
                        got = restore(decrypt(sealed, identity), target, order)
                        res.restored_rows = sum(got.values())
                        if res.restored_rows < cfg.min_rows_ratio * res.manifest_rows:
                            res.problems.append(
                                f"restored {res.restored_rows} of {res.manifest_rows} rows"
                            )
                except Exception as exc:  # a wrong key, a corrupt archive or a failed load
                    res.problems.append(f"{type(exc).__name__}: {exc}")
                step.record_output(tables=res.tables, problems=len(res.problems))
        res.status = "fail" if res.problems else "pass"
        sink.emit(
            ctx,
            AUD.BACKUP_RESTORE_TESTED,
            entity_type="backup",
            entity_id=res.backup or "none",
            details={k: v for k, v in res.as_dict().items() if k != "problems"}
            | {"problems": len(res.problems)},
        )
        outcome.summary = {"status": res.status, "backup": res.backup}
    return ctx, res
