"""Proposals: what an agent may write (AG-03). A proposal is a row waiting for you, nothing more.

The MCP `propose_*` tools write here and the `parakh_mcp` database role can only INSERT into the
`proposals` table, so an agent can neither approve its own proposal nor touch a list. The monthly job
then *ingests* watchlist proposals through the same rules as everything else (capacity, minimum stay,
dedupe), turning the valid ones into pending suggestions marked 🤖 (plan 06 §3.1b).
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from parakh.audit.ids import new_ulid
from parakh.watch.state import StateStore

STATE_NAME = "proposals"
Kind = Literal["watchlist", "thesis_flag", "journal"]
Status = Literal["pending", "approved", "rejected", "snoozed", "expired"]


class Proposal(BaseModel):
    proposal_id: str = Field(default_factory=new_ulid)
    kind: Kind
    isin: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    reason: str
    evidence_refs: list[str] = Field(default_factory=list)
    agent_run_id: str | None = None
    client: str = "agent:unknown"
    status: Status = "pending"
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.UTC))
    decided_by: str | None = None
    decided_at: dt.datetime | None = None
    expires_at: dt.datetime | None = None


class ProposalStore(Protocol):
    def all(self) -> list[Proposal]: ...
    def add(self, p: Proposal) -> Proposal: ...
    def save(self, proposals: list[Proposal]) -> None: ...


class LocalProposalStore:
    def __init__(self, store: StateStore | None = None) -> None:
        self.store = store or StateStore()

    def all(self) -> list[Proposal]:
        return [Proposal.model_validate(r) for r in self.store.load(STATE_NAME).get("rows", [])]

    def save(self, proposals: list[Proposal]) -> None:
        self.store.save(STATE_NAME, {"rows": [p.model_dump(mode="json") for p in proposals]})

    def add(self, p: Proposal) -> Proposal:
        rows = self.all()
        rows.append(p)
        self.save(rows)
        return p

    def pending(self, kind: Kind | None = None) -> list[Proposal]:
        return [p for p in self.all() if p.status == "pending" and (kind is None or p.kind == kind)]
