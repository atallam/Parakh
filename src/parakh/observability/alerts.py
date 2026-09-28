"""Alerts for LLM failures and unexpected outputs (C4.4).

Every alert is logged at error level. Register sinks (Telegram, email, ntfy) with
`register_sink`; a failing sink never breaks the caller.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog

log = structlog.get_logger(__name__)
AlertSink = Callable[[str, dict[str, Any]], None]
_sinks: list[AlertSink] = []


def register_sink(sink: AlertSink) -> None:
    _sinks.append(sink)


def clear_sinks() -> None:
    _sinks.clear()


def alert(kind: str, **fields: Any) -> None:
    log.error("alert", alert_kind=kind, **fields)
    for sink in list(_sinks):
        try:
            sink(kind, fields)
        except Exception:  # noqa: BLE001 - alerting must never raise
            log.exception("alert.sink_failed", alert_kind=kind)
