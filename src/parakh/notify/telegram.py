"""Notifier interface and the Telegram adapter (ADR-008; plan 03 §4).

Agents never call this directly; they go through `notify.queue` (AG-05, Phase 3). The adapter:
- sends HTML-formatted text (escaped: company names contain `&`, e.g. M&M);
- supports silent sends (the ⚪-only digests and the Sunday heartbeat are silent);
- honours Telegram's 429 `retry_after` once, then reports failure instead of looping;
- never logs the token (it is in the URL, so errors are scrubbed before they surface).
"""

from __future__ import annotations

import html
import time
from dataclasses import dataclass
from typing import Protocol

import httpx

API = "https://api.telegram.org"
MAX_LEN = 4096  # why: Telegram's message length limit


@dataclass(frozen=True)
class Delivery:
    ok: bool
    provider_msg_id: str | None = None
    error: str | None = None


class Notifier(Protocol):
    def send(self, text: str, *, silent: bool = False) -> Delivery: ...


def escape(text: str) -> str:
    """Escape user or data text for Telegram HTML mode."""
    return html.escape(text, quote=False)


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, client: httpx.Client | None = None) -> None:
        self._token = token
        self.chat_id = chat_id
        self.client = client or httpx.Client(timeout=20)

    def _scrub(self, text: str) -> str:
        return text.replace(self._token, "[TOKEN]")

    def send(self, text: str, *, silent: bool = False) -> Delivery:
        if len(text) > MAX_LEN:
            return Delivery(False, error=f"message is {len(text)} chars (> {MAX_LEN})")
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_notification": silent,
            "link_preview_options": {"is_disabled": True},
        }
        url = f"{API}/bot{self._token}/sendMessage"
        for attempt in range(2):
            try:
                resp = self.client.post(url, json=payload)
            except httpx.HTTPError as exc:
                return Delivery(False, error=self._scrub(f"{type(exc).__name__}: {exc}"))
            body = (
                resp.json()
                if resp.headers.get("content-type", "").startswith("application/json")
                else {}
            )
            if resp.status_code == 429 and attempt == 0:
                time.sleep(float(body.get("parameters", {}).get("retry_after", 1)))
                continue
            if resp.status_code == 200 and body.get("ok"):
                return Delivery(True, provider_msg_id=str(body["result"]["message_id"]))
            return Delivery(
                False, error=self._scrub(f"HTTP {resp.status_code}: {body.get('description', '')}")
            )
        return Delivery(False, error="rate limited twice")
