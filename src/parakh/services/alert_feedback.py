"""Rate an alert useful or noise, from any channel (AC-F17.5).

The Telegram buttons and the Streamlit page both call `record_alert_feedback`, so a rating leaves the
same two traces whichever way it arrives: a `feedback` row in the alerts log (read by the precision
report) and an `AUD.ALERT.FEEDBACK` audit event. The newest rating per alert wins.
"""

from __future__ import annotations

from typing import Any

from parakh.audit.context import RunContext
from parakh.audit.emit import AuditSink
from parakh.audit.events import AUD, Channel
from parakh.configs.calibration_models import AlertConfig
from parakh.notify.log import AlertsLog

CARRY = ("asof", "isin", "symbol", "code", "kind", "severity", "source")


class FeedbackError(ValueError):
    """A refusal with a reason a person can act on (UX-10)."""


def record_alert_feedback(
    log: AlertsLog,
    sink: AuditSink,
    ctx: RunContext,
    cfg: AlertConfig,
    alert_id: str,
    *,
    useful: bool,
    channel: Channel,
    tag: str | None = None,
    row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write the rating and its audit event; returns the alert row it rated."""
    alert = row if row is not None else log.find(alert_id)
    if alert is None:
        raise FeedbackError(f"no alert {alert_id} in the log")
    if tag is not None and tag not in cfg.feedback_tags:
        raise FeedbackError(f"reason must be one of {', '.join(cfg.feedback_tags)}")
    if tag is not None and useful:
        raise FeedbackError("a reason applies to noise ratings only")
    verdict = "useful" if useful else "noise"
    log.record(
        {
            **{k: alert.get(k) for k in CARRY},
            "alert_id": alert_id,
            "run_id": ctx.run_id,
            "decision": "feedback",
            "reason": verdict,
            "channel": channel,
            "tag": tag,
            "payload_hash": alert.get("payload_hash", ""),
        }
    )
    sink.emit(
        ctx,
        AUD.ALERT_FEEDBACK,
        channel=channel,
        entity_type="alert",
        entity_id=alert_id,
        isin=alert.get("isin"),
        details={"verdict": verdict, "code": alert.get("code"), "tag": tag},
    )
    return alert
