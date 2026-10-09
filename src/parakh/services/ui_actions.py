"""Apply button taps and commands the Telegram webhook queued in `ui_actions` (plan 03 §4.3; AC-F15.1).

The Supabase Edge Function only verifies Telegram's secret header and inserts a row (one per Telegram
update id, so a retried webhook is a no-op). This module applies queued rows through the same
`WatchlistService` the app and the CLI use, so every decision has one audit trail whatever the channel.
A token that is expired, tampered with or for a suggestion already decided is marked rejected, not applied.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Protocol

from parakh.notify.tokens import TokenError, verify
from parakh.services.watchlist import WatchlistError, WatchlistService


class ActionStore(Protocol):
    def queued(self) -> list[dict[str, Any]]: ...
    def mark(self, action_id: str, status: str, result: str) -> None: ...


@dataclass
class ApplyResult:
    applied: int = 0
    rejected: int = 0
    failed: int = 0


def apply_queued(
    store: ActionStore, svc: WatchlistService, key: bytes, *, today: dt.date
) -> ApplyResult:
    out = ApplyResult()
    for row in store.queued():
        aid = row["action_id"]
        if row.get("kind") != "button":
            store.mark(aid, "rejected", "commands are answered by the bot, not queued")
            out.rejected += 1
            continue
        try:
            action, sugg_id = verify(key, str(row["payload"]), today)
            if action not in ("a", "r", "s"):
                raise TokenError("not a suggestion action")
        except TokenError as exc:
            store.mark(aid, "rejected", f"button {exc.reason}")
            out.rejected += 1
            continue
        try:
            fn = {"a": svc.approve, "r": svc.reject, "s": svc.snooze}[action]
            res = fn(sugg_id, channel="telegram", today=today)
        except WatchlistError as exc:
            store.mark(aid, "failed", str(exc))
            out.failed += 1
            continue
        if res.ok:
            store.mark(aid, "applied", res.message)
            out.applied += 1
        else:
            store.mark(aid, "rejected", res.message)
            out.rejected += 1
    return out


class SupabaseActionStore:
    def __init__(self, client: Any) -> None:
        self.c = client

    def queued(self) -> list[dict[str, Any]]:
        return (
            self.c.table("ui_actions")
            .select("*")
            .eq("status", "queued")
            .order("received_at")
            .execute()
            .data
        )  # type: ignore[no-any-return]

    def mark(self, action_id: str, status: str, result: str) -> None:
        self.c.table("ui_actions").update(
            {
                "status": status,
                "result": result[:300],
                "applied_at": dt.datetime.now(dt.UTC).isoformat(),
            }
        ).eq("action_id", action_id).execute()
