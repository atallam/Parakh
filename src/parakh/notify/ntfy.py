"""ntfy.sh loud lane for High alerts on owned stocks (AC-F11.10). Off at baseline (plan 13 D5)."""

from __future__ import annotations

import httpx
import structlog

from parakh.notify.telegram import Delivery

log = structlog.get_logger(__name__)


class NtfyClient:
    def __init__(self, server: str, topic: str, client: httpx.Client | None = None) -> None:
        self.url = f"{server.rstrip('/')}/{topic}"
        self.client = client or httpx.Client(timeout=15)

    def send(self, title: str, text: str, *, priority: str = "high") -> Delivery:
        try:
            r = self.client.post(
                self.url,
                content=text.encode("utf-8"),
                headers={
                    "Title": title.encode("ascii", "ignore").decode() or "Parakh",
                    "Priority": priority,
                },
            )
            r.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("ntfy.send_failed", error=type(exc).__name__)  # the URL holds the topic
            return Delivery(False, error=type(exc).__name__)
        return Delivery(True)
