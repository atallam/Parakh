"""TOOL.notify.*: the one tier-N tool, `queue` (plan 15 §4.2; AG-05; AC-F24.8).

It writes a queue row and returns. Routing, de-duplication, cool-downs, masking and shadow mode are
applied when the job sends the queue, so nothing an agent says can reach the owner except through
the same policy as every other alert.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

from parakh.mcp.registry import ToolCall, Toolset
from parakh.notify.model import Severity
from parakh.notify.queue import NotifyQueue, QueueRow, TemplateId, cap_severity
from parakh.notify.templates import sanitize_note
from parakh.watch.state import StateStore

NOTIFY = Toolset("notify", version="0.1.0")


class QueueIn(BaseModel):
    kind: Literal["event", "review", "thesis"] = Field(
        description="'event' for a filing alert, 'review' for a monthly-review item, 'thesis' for a thesis WATCH."
    )
    code: str = Field(
        description="The rule code the item is about: an E-code such as E07, or REVIEW or THESIS.WATCH.",
        pattern=r"^(E\d{2}|REVIEW|THESIS\.WATCH)$",
    )
    severity: Literal["High", "Medium", "Low"] = Field(
        description="The severity you propose. It is capped at the rule table's value for the code; asking for more has no effect."
    )
    template_id: TemplateId = Field(description="Which message template renders it.")
    isin: str | None = Field(default=None, description="ISIN of the stock, e.g. INE646L01027.")
    symbol: str | None = Field(default=None, description="NSE symbol, e.g. INDIGO.")
    event_id: str | None = Field(
        default=None,
        description="The alert id of the filing, as given in the task inputs (event:<ISIN>:<E-code>:<group>).",
    )
    note: str | None = Field(
        default=None,
        description="One line, at most 140 characters, why it matters. No amounts, no links, no quantities.",
        max_length=400,
    )


class QueueOut(BaseModel):
    queued: bool
    queue_id: str | None = None
    severity_applied: str
    severity_capped: bool
    note_kept: bool
    message: str = ""


@NOTIFY.tool("queue", tier="N", title="Queue a notification")
def queue(params: QueueIn, call: ToolCall) -> QueueOut:
    """Queue one message for the owner. It is not sent now: the daily job sends the queue
    through the same routing as every other alert (de-duplication, 10-day cool-down, masking,
    a daily cap per agent, and shadow mode while it is on).

    Use it for the short "why it matters" of a filing the rules flagged, or for a monthly-review
    item. The severity you ask for is capped at the rule table's value for the code, so a Medium
    rule can never become a High interrupt. The note must be one plain line: amounts, quantities
    and links are removed and the note dropped. It cannot approve, reject, edit or send anything
    directly. Calling it twice for the same stock and event inside the cool-down sends one message.
    """
    from parakh.configs import load_all

    bundle = load_all()
    requested = Severity(params.severity)
    applied = cap_severity(bundle, params.code, requested)
    note = sanitize_note(params.note, include_amounts=bundle.notify.include_amounts)
    row = NotifyQueue(StateStore()).enqueue(
        QueueRow(
            queued_at=dt.datetime.now(dt.UTC).isoformat(),
            client=call.client,
            kind=params.kind,
            template_id=params.template_id,
            isin=params.isin,
            symbol=params.symbol,
            event_id=params.event_id,
            code=params.code,
            severity=applied.value,  # type: ignore[arg-type]
            requested_severity=params.severity,
            note=note,
        )
    )
    return QueueOut(
        queued=True,
        queue_id=row.queue_id,
        severity_applied=applied.value,
        severity_capped=applied is not requested,
        note_kept=note is not None or params.note is None,
        message="Queued. It is sent by the next job run, through routing.",
    )
