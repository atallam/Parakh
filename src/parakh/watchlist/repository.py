"""Where the watchlist lives (plan 06 §5.3, §7).

    repo = open_repository()          # Supabase when credentials exist and the backend allows it, else local
    state = repo.load()
    ...
    repo.save(state)

Two backends behind one protocol. `LocalWatchlistRepository` keeps one JSON file next to the other
watcher state, which GitHub Actions carries on the `parakh-data` branch. `SupabaseWatchlistRepository`
is the shared store for the Streamlit page and the Telegram listener (D11): entries and suggestions are
upserted, events are append-only and de-duplicated by `event_id`.
"""

from __future__ import annotations

import os
from typing import Any, Protocol

from parakh.watch.state import StateStore
from parakh.watchlist.models import Entry, Suggestion, WatchEvent, WatchlistState

STATE_NAME = "watchlist"
BACKEND_ENV = "PARAKH_WATCHLIST_BACKEND"  # local | supabase


class WatchlistRepository(Protocol):
    def load(self) -> WatchlistState: ...
    def save(self, state: WatchlistState) -> None: ...


class LocalWatchlistRepository:
    def __init__(self, store: StateStore | None = None) -> None:
        self.store = store or StateStore()

    def load(self) -> WatchlistState:
        raw = self.store.load(STATE_NAME)
        return WatchlistState.model_validate(raw) if raw else WatchlistState()

    def save(self, state: WatchlistState) -> None:
        self.store.save(STATE_NAME, state.model_dump(mode="json"))


ENTRY_COLUMNS = tuple(Entry.model_fields)
SUGGESTION_COLUMNS = tuple(Suggestion.model_fields)
EVENT_COLUMNS = tuple(WatchEvent.model_fields)
PAGE = 1000
BATCH = 500


class SupabaseWatchlistRepository:
    """Reads whole tables (a personal watchlist is a few hundred rows) and writes only what changed."""

    def __init__(self, client: Any) -> None:
        self.client = client
        self._seen: dict[str, dict[str, dict[str, Any]]] = {"e": {}, "s": {}}
        self._seen_events: set[str] = set()

    def _all(self, table: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        start = 0
        while True:
            batch = (
                self.client.table(table).select("*").range(start, start + PAGE - 1).execute().data
                or []
            )
            rows.extend(batch)
            if len(batch) < PAGE:
                return rows
            start += PAGE

    def load(self) -> WatchlistState:
        entries = [
            Entry.model_validate({k: r.get(k) for k in ENTRY_COLUMNS if k in r})
            for r in self._all("watchlist_entries")
        ]
        suggestions = [
            Suggestion.model_validate({k: r.get(k) for k in SUGGESTION_COLUMNS if k in r})
            for r in self._all("watchlist_suggestions")
        ]
        events = [
            WatchEvent.model_validate({k: r.get(k) for k in EVENT_COLUMNS if k in r})
            for r in self._all("watchlist_events")
        ]
        state = WatchlistState(
            entries={e.entry_id: e for e in entries},
            suggestions={s.sugg_id: s for s in suggestions},
            events=sorted(events, key=lambda ev: ev.at),
        )
        self._seen["e"] = {e.entry_id: e.model_dump(mode="json") for e in entries}
        self._seen["s"] = {s.sugg_id: s.model_dump(mode="json") for s in suggestions}
        self._seen_events = {ev.event_id for ev in events}
        return state

    def save(self, state: WatchlistState) -> None:
        changed_e = [
            d
            for e in state.entries.values()
            if self._seen["e"].get(e.entry_id) != (d := e.model_dump(mode="json"))
        ]
        changed_s = [
            d
            for s in state.suggestions.values()
            if self._seen["s"].get(s.sugg_id) != (d := s.model_dump(mode="json"))
        ]
        new_events = [
            ev.model_dump(mode="json")
            for ev in state.events
            if ev.event_id not in self._seen_events
        ]
        for table, rows, key in (
            ("watchlist_entries", changed_e, "entry_id"),
            ("watchlist_suggestions", changed_s, "sugg_id"),
        ):
            for i in range(0, len(rows), BATCH):
                self.client.table(table).upsert(rows[i : i + BATCH], on_conflict=key).execute()
        for i in range(0, len(new_events), BATCH):
            self.client.table("watchlist_events").upsert(
                new_events[i : i + BATCH], on_conflict="event_id", ignore_duplicates=True
            ).execute()
        self._seen["e"].update({d["entry_id"]: d for d in changed_e})
        self._seen["s"].update({d["sugg_id"]: d for d in changed_s})
        self._seen_events.update(d["event_id"] for d in new_events)


def open_repository(store: StateStore | None = None) -> WatchlistRepository:
    """Supabase only when `PARAKH_WATCHLIST_BACKEND=supabase`; otherwise the local JSON store."""
    if os.environ.get(BACKEND_ENV, "").lower() == "supabase":
        from parakh.db import get_supabase

        return SupabaseWatchlistRepository(get_supabase())
    return LocalWatchlistRepository(store)
