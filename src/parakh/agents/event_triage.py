"""AGENT.event_triage: one line on why a flagged filing matters (plan 03 §5b; plan 15 §5; F25.4).

The rules already decided that the filing matters and set its severity. The agent adds a line. The
job enforces the limits: the line passes `sanitize_note`; the severity never rises (the note is
attached to the rule's own alert, which keeps its rule severity); at most `MAX_TRIAGE_PER_RUN`
filings are triaged; and if the agent fails, runs out of budget or its output is invalid, the
rule-based alert goes out unchanged without the line. The agent can never suppress an alert.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from parakh.agents.roster import agent_enabled, build_spec, run_agent
from parakh.agents.runtime.base import AgentRunner, AgentTask
from parakh.audit.context import RunContext
from parakh.audit.emit import AuditSink
from parakh.configs import ConfigBundle
from parakh.notify.model import Alert
from parakh.notify.templates import sanitize_note

AGENT_ID = "AGENT.event_triage"
VERSION = "0.1.0"
MAX_TRIAGE_PER_RUN = 8  # why: bounds cost; the remaining alerts go out on the rule text alone


class TriageOutput(BaseModel):
    note: str = Field(max_length=400)
    material: bool
    refresh_suggested: bool = False


@dataclass
class TriageResult:
    alerts: list[Alert] = field(default_factory=list)  # same alerts, notes attached when live
    shadow: list[tuple[Alert, str]] = field(
        default_factory=list
    )  # (alert, note) for the shadow log
    triaged: int = 0
    pending: int = 0
    skipped_routine: int = 0
    refresh_suggested: list[str] = field(default_factory=list)


def triage(
    runner: AgentRunner,
    bundle: ConfigBundle,
    ctx: RunContext,
    sink: AuditSink,
    alerts: list[Alert],
) -> TriageResult:
    out = TriageResult(alerts=list(alerts))
    if not agent_enabled(bundle, AGENT_ID):
        return out
    spec = build_spec(AGENT_ID, bundle, version=VERSION, output_model=TriageOutput)
    live = not bundle.agents.dry_run
    candidates = [i for i, a in enumerate(alerts) if a.kind == "event" and a.source == "events"]
    for n, i in enumerate(candidates):
        alert = alerts[i]
        if n >= MAX_TRIAGE_PER_RUN:
            break
        task = AgentTask(
            task_id=f"{ctx.run_id}.triage.{n}",
            kind="triage_event",
            inputs={
                "event_id": alert.dedupe_key,
                "code": alert.code,
                "isin": alert.isin or "",
                "symbol": alert.symbol or "",
            },
        )
        result = run_agent(runner, spec, task, ctx, sink, bundle)
        if result.status != "ok" or result.output is None:
            out.pending += 1
            continue
        res = TriageOutput.model_validate(result.output)
        note = sanitize_note(res.note, include_amounts=bundle.notify.include_amounts)
        out.triaged += 1
        if res.refresh_suggested and alert.isin:
            out.refresh_suggested.append(alert.isin)
        if not res.material and alert.severity.value == "Low":
            out.skipped_routine += 1
        if note is None:
            continue
        if live:
            out.alerts[i] = dataclasses.replace(alert, note=note)
        else:
            out.shadow.append((alert, note))
    return out
