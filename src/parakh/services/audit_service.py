"""Read access to run manifests and their audit events (plan 10 §5). No writes here."""

from __future__ import annotations

from parakh import __version__
from parakh.audit.emit import get_sink
from parakh.audit.manifest import list_run_ids, read_manifest
from parakh.services.view_models import RunLookup, RunView, Stamp, StepSummary

LATEST = "latest"


def get_run(run_id: str) -> RunLookup:
    """The manifest and audit event types of one run; `run_id="latest"` picks the newest."""
    if run_id == LATEST:
        ids = list_run_ids()
        if not ids:
            return RunLookup(
                stamp=Stamp(asof=None, run_id=None, framework_version=__version__),
                found=False,
                message="No runs recorded yet. Try `parakh run --mode dummy`.",
            )
        run_id = ids[-1]  # ULIDs sort by time
    manifest = read_manifest(run_id)
    if manifest is None:
        return RunLookup(
            stamp=Stamp(asof=None, run_id=run_id, framework_version=__version__),
            found=False,
            message=f"No manifest for run {run_id}.",
        )
    events = get_sink().events_for_run(run_id)
    view = RunView(
        run_id=manifest.run_id,
        mode=manifest.mode,
        env=manifest.env,
        asof=manifest.asof,
        status=manifest.status,
        trigger=manifest.trigger,
        triggered_by=manifest.triggered_by,
        started_at=manifest.started_at,
        finished_at=manifest.finished_at,
        code_version=manifest.code_version,
        config_hash=manifest.config_hash,
        steps=[
            StepSummary(name=s.name, status=s.status, duration_ms=s.duration_ms, outputs=s.outputs)
            for s in manifest.steps
        ],
        audit_event_types=[e.event_type.value for e in events],
        audit_pending=manifest.audit_pending,
    )
    return RunLookup(
        stamp=Stamp(
            asof=manifest.asof, run_id=manifest.run_id, framework_version=manifest.framework_version
        ),
        found=True,
        run=view,
    )
