"""AGENT.qualitative: one concall transcript read against the thesis (F06; plan 15 §5; D13).

The agent reads cached text through `data.get_document` and returns a summary, guidance, per-item
thesis assessments and a tone diff. The job around it enforces the limits:
- every quote must appear word for word in the transcript, or the read is discarded (AC-F06.2);
- the result is cached on (document hash, prompt pin), so an unchanged transcript costs no tokens (AC-F06.3);
- a run that hits its turn or token limit leaves the stock "qualitative pending" (AC-F06.5);
- a STRESSED or BREAKS assessment sets the thesis to WATCH through a `thesis_flag` proposal and never BROKEN (AC-F06.4);
- text in the transcript is data: an injection attempt is logged and changes nothing (AC-F06.6).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

from parakh.agents.roster import agent_enabled, build_spec, run_agent
from parakh.agents.runtime.base import AgentRunner, AgentTask
from parakh.audit.context import RunContext
from parakh.audit.emit import AuditSink
from parakh.audit.events import AUD
from parakh.configs import ConfigBundle
from parakh.prompts import active_version
from parakh.services.documents import CachedDoc
from parakh.watch.state import StateStore

AGENT_ID = "AGENT.qualitative"
VERSION = "0.1.0"
CACHE = "qualitative_cache"
INJECTION = re.compile(
    r"ignore (all |any )?(previous|prior|above) instructions|disregard .{0,30}instructions"
    r"|you are now |system prompt|reveal your",
    re.I,
)


class GuidanceItem(BaseModel):
    statement: str = Field(max_length=300)
    due: str = Field(default="", max_length=40)
    quote: str = Field(max_length=400)


class Assessment(BaseModel):
    item_id: str = Field(pattern=r"^(KM|BR)[1-5]$")
    verdict: Literal["SUPPORTED", "NEUTRAL", "STRESSED", "BREAKS"]
    quote: str = Field(default="", max_length=400)


class QualOutput(BaseModel):
    readable: bool = True
    summary: str = Field(default="", max_length=700)
    guidance: list[GuidanceItem] = Field(default_factory=list, max_length=8)
    thesis_assessments: list[Assessment] = Field(default_factory=list, max_length=10)
    tone_change: Literal["MORE_CONFIDENT", "SAME", "MORE_CAUTIOUS", "NOT_COMPARABLE"] = (
        "NOT_COMPARABLE"
    )
    tone_reason: str = Field(default="", max_length=200)


def _norm(text: str) -> str:
    return (
        re.sub(r"\s+", " ", text.replace("“", '"').replace("”", '"').replace("’", "'"))
        .strip()
        .lower()
    )


def unverified_quotes(out: QualOutput, text: str) -> list[str]:
    """Quotes that are not in the transcript, word for word (whitespace and curly quotes aside)."""
    haystack = _norm(text)
    quotes = [g.quote for g in out.guidance] + [a.quote for a in out.thesis_assessments if a.quote]
    return [q for q in quotes if _norm(q) not in haystack]


def has_injection(text: str) -> bool:
    return bool(INJECTION.search(text))


@dataclass
class QualResult:
    isin: str
    status: Literal["ok", "cached", "pending", "failed", "skipped"]
    overlay: dict[str, Any] = field(default_factory=dict)
    flags: list[Assessment] = field(default_factory=list)  # STRESSED / BREAKS, for the thesis flag
    reason: str = ""


def pending_overlay(reason: str) -> dict[str, Any]:
    return {"status": "pending", "reason": f"qualitative pending: {reason}"}


def run_qualitative(
    runner: AgentRunner,
    bundle: ConfigBundle,
    ctx: RunContext,
    sink: AuditSink,
    *,
    isin: str,
    symbol: str,
    doc: CachedDoc | None,
    previous: CachedDoc | None = None,
    store: StateStore | None = None,
) -> QualResult:
    if not agent_enabled(bundle, AGENT_ID):
        return QualResult(isin, "skipped", reason="agent disabled")
    if doc is None:
        return QualResult(isin, "pending", pending_overlay("no transcript"), reason="no transcript")
    store = store or StateStore()
    pin = f"qualitative.{active_version('qualitative')}"
    key = f"{isin}|{doc.sha256}|{pin}"
    cache = store.load(CACHE)
    if key in cache:  # same document, same prompt: no tokens (AC-F06.3)
        overlay = cache[key]
        return QualResult(isin, "cached", overlay, _flags(overlay))
    if has_injection(doc.text):
        sink.emit(
            ctx, AUD.LLM_INJECTION_SUSPECTED, entity_type="document", entity_id=doc.sha256,
            isin=isin, details={"agent_id": AGENT_ID, "symbol": symbol},
        )  # fmt: skip
    spec = build_spec(AGENT_ID, bundle, version=VERSION, output_model=QualOutput)
    task = AgentTask(
        task_id=f"{ctx.run_id}.qual.{isin}",
        kind="read_transcript",
        inputs={
            "isin": isin,
            "symbol": symbol,
            "doc_type": "transcript",  # data_get_document needs isin + doc_type, not a hash
            "prior_doc_type": "prior_transcript" if previous is not None else None,
        },
    )
    result = run_agent(runner, spec, task, ctx, sink, bundle)
    if result.status != "ok" or result.output is None:
        reason = result.reason or result.status
        return QualResult(isin, "pending", pending_overlay(reason), reason=reason)
    out = QualOutput.model_validate(result.output)
    if not out.readable:
        return QualResult(
            isin, "pending", pending_overlay("transcript unreadable"), reason="unreadable"
        )
    bad = unverified_quotes(out, doc.text)
    if bad:
        sink.emit(
            ctx, AUD.LLM_CITATION_UNVERIFIED, entity_type="document", entity_id=doc.sha256,
            isin=isin, details={"agent_id": AGENT_ID, "unverified": len(bad)},
        )  # fmt: skip
        return QualResult(
            isin,
            "failed",
            pending_overlay("a quote could not be verified"),
            reason="unverified quote",
        )
    overlay = {
        "status": "ok",
        "document_id": doc.sha256,
        "call_period": doc.period,
        "source_url": doc.source_url,
        "prompt": pin,
        "summary": out.summary,
        "guidance": [g.model_dump() for g in out.guidance],
        "thesis_assessments": [a.model_dump() for a in out.thesis_assessments],
        "tone_change": out.tone_change if previous else "NOT_COMPARABLE",
        "tone_reason": out.tone_reason if previous else "",
        "verified": True,
    }
    cache[key] = overlay
    store.save(CACHE, dict(list(cache.items())[-2000:]))
    return QualResult(isin, "ok", overlay, _flags(overlay))


def _flags(overlay: dict[str, Any]) -> list[Assessment]:
    return [
        Assessment.model_validate(a)
        for a in overlay.get("thesis_assessments", [])
        if a["verdict"] in ("STRESSED", "BREAKS")
    ]


def thesis_effect(flags: list[Assessment]) -> str | None:
    """A concall can only put a thesis on WATCH; only the owner's rules can break it (AC-F06.4)."""
    return "WATCH" if flags else None
