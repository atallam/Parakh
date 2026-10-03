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
    def send(
        self,
        text: str,
        *,
        silent: bool = False,
        buttons: list[list[tuple[str, str]]] | None = None,
    ) -> Delivery: ...


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

    def send(
        self,
        text: str,
        *,
        silent: bool = False,
        buttons: list[list[tuple[str, str]]] | None = None,
    ) -> Delivery:
        """Send one message. `buttons` is rows of (label, callback_data) for an inline keyboard."""
        if len(text) > MAX_LEN:
            return Delivery(False, error=f"message is {len(text)} chars (> {MAX_LEN})")
        payload: dict[str, object] = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_notification": silent,
            "link_preview_options": {"is_disabled": True},
        }
        if buttons:
            payload["reply_markup"] = {
                "inline_keyboard": [
                    [{"text": label, "callback_data": data} for label, data in row]
                    for row in buttons
                ]
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

    # -- receiving (Phase 3: each scheduled job first applies pending taps; plan 03 §4.3) -------
    def get_updates(self, offset: int | None = None, limit: int = 100) -> list[dict[str, object]]:
        """Pending updates (messages and button taps). Telegram keeps them 24 hours."""
        params: dict[str, int] = {"limit": limit, "timeout": 0}
        if offset is not None:
            params["offset"] = offset
        try:
            resp = self.client.get(f"{API}/bot{self._token}/getUpdates", params=params)
            body = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TelegramError(self._scrub(f"{type(exc).__name__}: {exc}")) from exc
        if resp.status_code != 200 or not body.get("ok"):
            raise TelegramError(
                self._scrub(f"HTTP {resp.status_code}: {body.get('description', '')}")
            )
        result = body.get("result", [])
        return result if isinstance(result, list) else []

    def answer_callback(self, callback_id: str, text: str = "") -> bool:
        """Stop the spinner on a tapped button; best effort."""
        try:
            resp = self.client.post(
                f"{API}/bot{self._token}/answerCallbackQuery",
                json={"callback_query_id": callback_id, "text": text[:180]},
            )
        except httpx.HTTPError:
            return False
        return resp.status_code == 200


class TelegramError(RuntimeError):
    """A receive-side failure; the message never contains the token."""
