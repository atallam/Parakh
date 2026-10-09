"""Audit event type IDs (`AUD.<DOMAIN>.<ACTION>`) and the audit record model (plan 10 §4, §4.1).

Rule 5 (plan 10 §14): a new event type needs an ID here; `docs/AUDIT_EVENTS.md` is generated
from this enum, so the docs can't drift from the code.
"""

from __future__ import annotations

import datetime as dt
from enum import StrEnum
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

IST = ZoneInfo("Asia/Kolkata")


class AUD(StrEnum):
    """Every audit event type. The value is the searchable ID."""

    # Run lifecycle
    RUN_START = "AUD.RUN.START"
    RUN_END = "AUD.RUN.END"
    RUN_ABORT = "AUD.RUN.ABORT"
    RUN_INVALIDATED = "AUD.RUN.INVALIDATED"
    # Data
    DATA_FETCH = "AUD.DATA.FETCH"
    DATA_FALLBACK_USED = "AUD.DATA.FALLBACK_USED"
    DATA_VALIDATION_FAIL = "AUD.DATA.VALIDATION_FAIL"
    DATA_CONFLICT = "AUD.DATA.CONFLICT"
    DATA_CORP_ACTION_APPLIED = "AUD.DATA.CORP_ACTION_APPLIED"
    DATA_RESTATEMENT_DETECTED = "AUD.DATA.RESTATEMENT_DETECTED"
    # Scoring
    SCORE_COMPUTED = "AUD.SCORE.COMPUTED"
    VETO_TRIGGERED = "AUD.VETO.TRIGGERED"
    VERDICT_CHANGED = "AUD.VERDICT.CHANGED"
    # LLM
    LLM_CALL = "AUD.LLM.CALL"
    LLM_VALIDATION_FAIL = "AUD.LLM.VALIDATION_FAIL"
    LLM_CITATION_UNVERIFIED = "AUD.LLM.CITATION_UNVERIFIED"
    LLM_BUDGET_STOP = "AUD.LLM.BUDGET_STOP"
    LLM_INJECTION_SUSPECTED = "AUD.LLM.INJECTION_SUSPECTED"
    # Agent runs
    AGENT_START = "AUD.AGENT.START"
    AGENT_END = "AUD.AGENT.END"
    AGENT_TURN_LIMIT = "AUD.AGENT.TURN_LIMIT"
    AGENT_PROPOSAL = "AUD.AGENT.PROPOSAL"
    # MCP
    MCP_TOOL_CALL = "AUD.MCP.TOOL_CALL"
    MCP_TOOL_DENIED = "AUD.MCP.TOOL_DENIED"
    JOB_REFRESH_REQUESTED = "AUD.JOB.REFRESH_REQUESTED"
    MCP_RATE_LIMITED = "AUD.MCP.RATE_LIMITED"
    # Signals and alerts
    SIGNAL_STATE_CHANGE = "AUD.SIGNAL.STATE_CHANGE"
    ALERT_SENT = "AUD.ALERT.SENT"
    ALERT_SUPPRESSED = "AUD.ALERT.SUPPRESSED"
    ALERT_DELIVERY_FAILED = "AUD.ALERT.DELIVERY_FAILED"
    # Watchlist
    WATCHLIST_AUTO_ADDED = "AUD.WATCHLIST.AUTO_ADDED"
    WATCHLIST_AUTO_REMOVED = "AUD.WATCHLIST.AUTO_REMOVED"
    WATCHLIST_SUGGESTED = "AUD.WATCHLIST.SUGGESTED"
    WATCHLIST_APPROVED = "AUD.WATCHLIST.APPROVED"
    WATCHLIST_REJECTED = "AUD.WATCHLIST.REJECTED"
    WATCHLIST_SNOOZED = "AUD.WATCHLIST.SNOOZED"
    WATCHLIST_EXPIRED = "AUD.WATCHLIST.EXPIRED"
    WATCHLIST_FLAGGED = "AUD.WATCHLIST.FLAGGED"
    WATCHLIST_MANUAL_ADD = "AUD.WATCHLIST.MANUAL_ADD"
    WATCHLIST_MANUAL_REMOVE = "AUD.WATCHLIST.MANUAL_REMOVE"
    # Holdings
    HOLDINGS_IMPORT = "AUD.HOLDINGS.IMPORT"
    HOLDINGS_LOT_ADDED = "AUD.HOLDINGS.LOT_ADDED"
    HOLDINGS_LOT_EDITED = "AUD.HOLDINGS.LOT_EDITED"
    HOLDINGS_SALE_RECORDED = "AUD.HOLDINGS.SALE_RECORDED"
    HOLDINGS_DELETED = "AUD.HOLDINGS.DELETED"
    # Human judgement
    OVERRIDE_SET = "AUD.OVERRIDE.SET"
    OVERRIDE_EXPIRED = "AUD.OVERRIDE.EXPIRED"
    THESIS_CHANGED = "AUD.THESIS.CHANGED"
    JOURNAL_ENTRY = "AUD.JOURNAL.ENTRY"
    # Change management
    CONFIG_CHANGED = "AUD.CONFIG.CHANGED"
    PROMPT_PROMOTED = "AUD.PROMPT.PROMOTED"
    PROMPT_ROLLED_BACK = "AUD.PROMPT.ROLLED_BACK"
    LENS_VERSION_BUMP = "AUD.LENS.VERSION_BUMP"
    HISTORY_RESCORED = "AUD.HISTORY.RESCORED"
    DEPLOY = "AUD.DEPLOY"
    # UI and channel interactions
    ALERT_FEEDBACK = "AUD.ALERT.FEEDBACK"
    ALERT_MUTED = "AUD.ALERT.MUTED"
    REVIEW_MARKED = "AUD.REVIEW.MARKED"
    BOT_COMMAND = "AUD.BOT.COMMAND"
    # Security and platform
    ACCESS_UI_LOGIN = "AUD.ACCESS.UI_LOGIN"
    ACCESS_BOT_REJECTED = "AUD.ACCESS.BOT_REJECTED"
    SECRET_ROTATED = "AUD.SECRET.ROTATED"
    BACKUP_COMPLETED = "AUD.BACKUP.COMPLETED"
    INTEGRITY_CHECK = "AUD.INTEGRITY.CHECK"

    @property
    def domain(self) -> str:
        return self.value.split(".")[1]


ActorType = Literal["scheduler", "user", "agent", "ci", "claude", "system"]
Channel = Literal["streamlit", "telegram", "cli", "mcp"]


def trading_date_ist(ts_utc: dt.datetime) -> dt.date:
    """The IST calendar date of a UTC timestamp (plan 04 §4 #12)."""
    return ts_utc.astimezone(IST).date()


class AuditEvent(BaseModel):
    """One audit record (plan 10 §4.1). Hashes are filled in by the sink, never by callers."""

    event_id: str
    event_type: AUD
    ts_utc: dt.datetime
    trading_date_ist: dt.date
    run_id: str | None = None
    step_id: str | None = None
    actor_type: ActorType
    actor_id: str
    channel: Channel | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    isin: str | None = None
    action: str | None = None
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    reason: str | None = None
    evidence_ref: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    code_version: str
    config_hash: str
    framework_version: str
    prev_hash: str = ""
    record_hash: str = ""

    def hashable(self) -> dict[str, Any]:
        """Everything except the two hash fields, as JSON-ready values."""
        return self.model_dump(mode="json", exclude={"prev_hash", "record_hash"})
