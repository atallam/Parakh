"""The journal service: add and review decision-journal entries, with an audit trail (AC-F17.4).

    svc = JournalService(store, bundle, ctx)
    svc.add("TCS", action="buy", reason="...", expected="...", channel="streamlit")
    svc.due(today)
    svc.review(entry_id, verdict="right", note="...")

Agents never call it: `propose_journal_entry` writes a proposal and the owner accepts it here (AG-03).
"""

from __future__ import annotations

import datetime as dt

from pydantic import ValidationError

from parakh.audit.context import RunContext
from parakh.audit.emit import AuditSink, get_sink
from parakh.audit.events import AUD, Channel
from parakh.calibration.journal import (
    JournalEntry,
    JournalError,
    JournalStore,
    new_entry,
    stats,
)
from parakh.configs import ConfigBundle


class JournalService:
    def __init__(
        self,
        store: JournalStore,
        bundle: ConfigBundle,
        ctx: RunContext,
        *,
        sink: AuditSink | None = None,
    ) -> None:
        self.store, self.bundle, self.ctx = store, bundle, ctx
        self.cfg = bundle.calibration.journal
        self.sink = sink or get_sink()

    def _resolve(self, query: str) -> tuple[str, str]:
        q = query.strip().upper()
        for sec in self.bundle.universe.active:
            if q in (sec.isin.upper(), sec.symbol.upper()):
                return sec.isin, sec.symbol
        raise JournalError(f"{query} is not in the universe; add it to the universe first")

    def add(
        self,
        stock: str,
        *,
        action: str,
        reason: str,
        expected: str,
        review_on: dt.date | None = None,
        channel: Channel = "cli",
        today: dt.date | None = None,
    ) -> JournalEntry:
        isin, symbol = self._resolve(stock)
        entry = new_entry(
            self.cfg,
            isin=isin,
            symbol=symbol,
            action=action,
            reason=reason,
            expected=expected,
            today=today or self.ctx.asof,
            review_on=review_on,
            channel=channel,
        )
        self.store.add(entry)
        self.sink.emit(
            self.ctx,
            AUD.JOURNAL_ENTRY,
            channel=channel,
            entity_type="journal_entry",
            entity_id=entry.entry_id,
            isin=isin,
            action=action,
            after={"review_on": entry.review_on.isoformat(), "status": entry.status},
        )
        return entry

    def review(
        self,
        entry_id: str,
        *,
        verdict: str,
        note: str = "",
        channel: Channel = "cli",
        today: dt.date | None = None,
    ) -> JournalEntry:
        entry = self.store.get(entry_id)
        if entry is None:
            raise JournalError(f"no journal entry {entry_id}")
        if entry.status == "reviewed":
            raise JournalError("that entry was already reviewed; add a new entry instead")
        if len(note) > self.cfg.max_field_chars:
            raise JournalError(f"the note is over {self.cfg.max_field_chars} characters")
        try:
            done = entry.model_copy(
                update={
                    "status": "reviewed",
                    "reviewed_on": today or self.ctx.asof,
                    "verdict": verdict,
                    "outcome_note": " ".join(note.split()),
                }
            )
            done = JournalEntry.model_validate(done.model_dump())
        except ValidationError as exc:
            raise JournalError(exc.errors()[0]["msg"].removeprefix("Value error, ")) from exc
        self.store.replace(done)
        self.sink.emit(
            self.ctx,
            AUD.JOURNAL_REVIEWED,
            channel=channel,
            entity_type="journal_entry",
            entity_id=entry_id,
            isin=entry.isin,
            before={"status": "open"},
            after={"status": "reviewed", "verdict": verdict},
        )
        return done

    def due(self, today: dt.date | None = None) -> list[JournalEntry]:
        return self.store.due(today or self.ctx.asof)

    def entries(self) -> list[JournalEntry]:
        return self.store.all()

    def stats(self) -> dict[str, object]:
        return stats(self.store.all())
