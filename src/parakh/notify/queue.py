"""`notify.queue`: the only way an agent gets a message to the owner (AG-05; AC-F24.8).

An agent calls the `notify_queue` MCP tool; the tool writes one row here and nothing more. A job
then drains the queue through the dispatcher, which applies the same routing, de-duplication,
cool-downs, masking and shadow mode as every other alert. So an agent can neither bypass the
policy nor spam: the severity it asks for is capped at the rule table's value for that event
code, the note is checked by `sanitize_note`, and each agent has a daily cap.

    NotifyQueue(store).enqueue(QueueRow(...))     # the MCP tool
    drain(queue, dispatcher, bundle)              # the job
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from parakh.audit.ids import new_ulid
from parakh.configs import ConfigBundle
from parakh.notify.model import Alert, Severity
from parakh.notify.templates import sanitize_note
from parakh.watch.state import StateStore

QUEUE_FILE = "notify_queue"  # JSON file under the watch state dir

TemplateId = Literal["event_note", "review_item", "thesis_watch"]


class QueueRow(BaseModel):
    queue_id: str = Field(default_factory=new_ulid)
    queued_at: str
    client: str  # agent:<name>
    kind: Literal["event", "review", "thesis"]
    template_id: TemplateId
    isin: str | None = None
    symbol: str | None = None
    event_id: str | None = None  # an Alert.dedupe_key, e.g. event:INE…:E07:12345
    code: str  # E07, REVIEW, THESIS.WATCH
    severity: Literal["High", "Medium", "Low"]
    requested_severity: Literal["High", "Medium", "Low"]
    note: str | None = None
    status: Literal["pending", "done"] = "pending"


def rule_ceiling(bundle: ConfigBundle, code: str) -> Severity | None:
    """Highest severity the rule table allows for an E-code; None for codes outside the table."""
    for rule in bundle.events.rules:
        if rule.id == code:
            return Severity(rule.max_severity)
    return None


def cap_severity(bundle: ConfigBundle, code: str, requested: Severity) -> Severity:
    """An agent never raises a severity above its rule's ceiling (AC-F25.4)."""
    ceiling = rule_ceiling(bundle, code)
    if ceiling is not None:
        return requested.capped(ceiling)
    if code.startswith(("REVIEW", "THESIS")):
        return requested.capped(
            Severity.MEDIUM
        )  # why: a review or a WATCH is never a High interrupt
    return Severity.LOW  # unknown code: the safest value


class NotifyQueue:
    def __init__(self, store: StateStore) -> None:
        self.store = store

    def _rows(self) -> list[dict[str, Any]]:
        return list(self.store.load(QUEUE_FILE).get("rows", []))

    def _save(self, rows: list[dict[str, Any]]) -> None:
        self.store.save(QUEUE_FILE, {"rows": rows[-500:]})

    def enqueue(self, row: QueueRow) -> QueueRow:
        rows = self._rows()
        rows.append(row.model_dump(mode="json"))
        self._save(rows)
        return row

    def pending(self) -> list[QueueRow]:
        return [QueueRow.model_validate(r) for r in self._rows() if r["status"] == "pending"]

    def mark_done(self, ids: set[str]) -> None:
        rows = self._rows()
        for r in rows:
            if r["queue_id"] in ids:
                r["status"] = "done"
        self._save(rows)


def row_to_alert(row: QueueRow, bundle: ConfigBundle, asof: dt.date) -> Alert:
    note = sanitize_note(row.note, include_amounts=bundle.notify.include_amounts)
    direction = "info"
    valence = "negative" if row.severity == "High" else "neutral"
    kind = {"event": "event", "review": "review", "thesis": "thesis"}[row.kind]
    group = row.event_id.rsplit(":", 1)[-1] if row.event_id else row.queue_id
    return Alert(
        kind=kind,  # type: ignore[arg-type]
        code=row.code,
        severity=cap_severity(bundle, row.code, Severity(row.severity)),
        headline=note or f"{row.code} flagged for review",
        asof=asof,
        isin=row.isin,
        symbol=row.symbol,
        direction=direction,  # type: ignore[arg-type]
        valence=valence,  # type: ignore[arg-type]
        group=group,
        source=row.client,
        note=note,
        extra={"queue_id": row.queue_id, "template_id": row.template_id},
    )


def drain(queue: NotifyQueue, dispatcher: Any, bundle: ConfigBundle, asof: dt.date) -> Any:
    """Send everything pending through the dispatcher (routing, cool-down, cap, shadow apply)."""
    rows = queue.pending()
    if not rows:
        return None
    result = dispatcher.submit(
        [row_to_alert(r, bundle, asof) for r in rows], title="Notes from the agents"
    )
    queue.mark_done({r.queue_id for r in rows})
    return result


def dump(queue: NotifyQueue) -> str:  # pragma: no cover - debugging aid
    return json.dumps(queue._rows(), indent=1)
