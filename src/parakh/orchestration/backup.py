"""Weekly encrypted backup job (plan 10 §11): dump → encrypt → upload → prune, audited.

    ctx, outcome, info = run_backup(bundle, PostgresTables(conn), SupabaseBlobs(client, "backups"))

Ends with `AUD.BACKUP.COMPLETED` carrying the archive's sha256, size, table and row counts, so
the audit trail proves every backup and its contents without revealing them.
"""

from __future__ import annotations

import datetime as dt
import hashlib

from parakh.audit.context import RunContext
from parakh.audit.emit import AuditSink, get_sink
from parakh.audit.events import AUD
from parakh.audit.steps import RunOutcome, audited_step, run_lifecycle
from parakh.configs import ConfigBundle
from parakh.storage.backup import BackupInfo, TableSource, backup_name, dump, encrypt, keep_set
from parakh.storage.prices import Blobs


def run_backup(
    bundle: ConfigBundle,
    source: TableSource,
    blobs: Blobs,
    now: dt.datetime | None = None,
    sink: AuditSink | None = None,
) -> tuple[RunContext, RunOutcome, BackupInfo | None]:
    sink = sink or get_sink()
    cfg = bundle.backup
    now = now or dt.datetime.now(dt.UTC)
    ctx = RunContext.create(mode="backup")
    info: BackupInfo | None = None
    with run_lifecycle(ctx, sink) as outcome:
        if not cfg.recipients:
            raise ValueError(
                "config/backup.yaml has no recipients: run `parakh backup keygen` first"
            )
        with audited_step(ctx, "dump") as step:
            archive, manifest = dump(source, now)
            rows = sum(t["rows"] for t in manifest["tables"].values())
            step.record_output(rows=rows, tables=len(manifest["tables"]))
        with audited_step(ctx, "encrypt_upload") as step:
            sealed = encrypt(archive, cfg.recipients)
            name = backup_name(now)
            blobs.put(name, sealed)
            sha = "sha256:" + hashlib.sha256(sealed).hexdigest()
            info = BackupInfo(name, sha, len(sealed), len(manifest["tables"]), rows)
            step.record_output(sha256=sha, bytes=len(sealed))
        with audited_step(ctx, "prune") as step:
            names = [n for n in blobs.list() if n.endswith(".tar.gz.age")]
            keep = keep_set(names, cfg.keep_weekly, cfg.keep_monthly)
            pruned = [n for n in names if n not in keep]
            for n in pruned:
                blobs.delete(n)
            step.record_output(kept=len(keep), pruned=len(pruned))
        sink.emit(
            ctx,
            AUD.BACKUP_COMPLETED,
            entity_type="backup",
            entity_id=info.name,
            evidence_ref=info.sha256,
            details={
                "bytes": info.bytes,
                "tables": info.tables,
                "rows": info.rows,
                "migrations": manifest["migrations"],
                "recipients": len(cfg.recipients),
            },
        )
        outcome.summary = {"backup": info.name, "rows": rows, "pruned": len(pruned)}
    return ctx, outcome, info
