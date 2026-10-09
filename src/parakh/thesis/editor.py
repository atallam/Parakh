"""The thesis form's writer: THESIS.md front matter, saved only by the owner (plan 12 §5.3; AC-F15.9).

    result = save_thesis(path, symbol="INDIGO", isin="INE646L01027", draft=ThesisDraft(...), today=day)

The pipeline never opens THESIS.md for writing (AC-F09.4); this module is called from the Streamlit form
and the CLI, and nowhere in the monthly run. Rules:
- the first save fixes the `original` statement; later saves keep it byte for byte and bump `thesis_version`;
- a changed statement is kept as a dated "Revision" in the body, so the diff against the original stays visible;
- a metric breaker's rule must parse and use known variables, or nothing is written;
- every save emits one `AUD.THESIS.CHANGED` with version numbers only, never the thesis text.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError

from parakh.audit.context import RunContext
from parakh.audit.emit import AuditSink, get_sink
from parakh.audit.events import AUD
from parakh.thesis import rules
from parakh.thesis.model import Breaker, KeyMetric, ThesisFront, ThesisOriginal, read_thesis

MAX_ITEMS = 5


class BreakerDraft(BaseModel):
    text: str = Field(min_length=3)
    check: Literal["metric", "llm_flag", "manual"] = "llm_flag"
    rule: str | None = None


class ThesisDraft(BaseModel):
    statement: str = Field(min_length=10)  # why I bought
    key_metrics: list[str] = Field(default_factory=list, max_length=MAX_ITEMS)  # what to watch
    breakers: list[BreakerDraft] = Field(default_factory=list, max_length=MAX_ITEMS)
    sizing_rationale: str | None = None
    review_by: dt.date | None = None


@dataclass
class SaveResult:
    ok: bool
    version: int = 0
    errors: list[str] = field(default_factory=list)
    revised_statement: bool = False
    path: Path | None = None


def _breaker(i: int, d: BreakerDraft) -> Breaker:
    # "manual" breakers are the owner's own check: stored as llm_flag-free, rule-free reminders
    check = "llm_flag" if d.check == "manual" else d.check
    return Breaker(
        id=f"BR{i}", text=d.text, check=check, rule=d.rule if check == "metric" else None
    )


def save_thesis(
    path: Path,
    *,
    symbol: str,
    isin: str,
    draft: ThesisDraft,
    today: dt.date,
    known_variables: Iterable[str] | None = None,
    ctx: RunContext | None = None,
    sink: AuditSink | None = None,
) -> SaveResult:
    existing = read_thesis(path)
    version = (existing.front.thesis_version + 1) if existing.front else 1
    original = (
        existing.front.original
        if existing.front
        else ThesisOriginal(written_on=today, statement=draft.statement)
    )
    errors: list[str] = []
    try:
        front = ThesisFront(
            symbol=symbol,
            isin=isin,
            thesis_version=version,
            original=original,
            key_metrics=[
                KeyMetric(id=f"KM{i}", text=t) for i, t in enumerate(draft.key_metrics, 1)
            ],
            breakers=[_breaker(i, b) for i, b in enumerate(draft.breakers, 1)],
            sizing_rationale=draft.sizing_rationale or None,
            review_by=draft.review_by,
        )
    except (ValidationError, ValueError) as exc:
        if isinstance(exc, ValidationError):
            errors += [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()]
        else:
            errors.append(str(exc))
        return SaveResult(False, errors=errors)
    known = set(known_variables) if known_variables is not None else None
    for b in front.breakers:
        if b.check == "metric" and b.rule:
            try:
                unknown = rules.check_variables(b.rule, known) if known is not None else []
            except rules.RuleError as exc:
                errors.append(f"{b.id}: {exc}")
                continue
            if unknown:
                errors.append(f"{b.id}: unknown variable(s) {', '.join(unknown)}")
    if errors:
        return SaveResult(False, errors=errors)

    revised = bool(
        existing.front and draft.statement.strip() != existing.front.original.statement.strip()
    )
    body = (
        existing.body
        if existing.exists and existing.body
        else "## Why I own it\n\nWrite freely here.\n\n## Review log"
    )
    log = [
        f"- {today.isoformat()}: "
        + ("first written." if version == 1 else f"revised to version {version}.")
    ]
    if revised:
        body += f"\n\n## Revision {version} ({today.isoformat()})\n\n{draft.statement.strip()}"
    body = body.rstrip() + "\n" + "\n".join(log) + "\n"
    data = front.model_dump(mode="json", exclude_none=True)
    text = "---\n" + yaml.safe_dump(data, sort_keys=False, allow_unicode=True) + "---\n\n" + body
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

    sink = sink or get_sink()
    ctx = ctx or RunContext.create(mode="thesis-form", actor_type="user", actor_id="owner")
    sink.emit(
        ctx, AUD.THESIS_CHANGED, entity_type="thesis", entity_id=isin, isin=isin,
        before={"version": version - 1}, after={"version": version},
        details={"key_metrics": len(front.key_metrics), "breakers": len(front.breakers), "revised_statement": revised},
    )  # fmt: skip
    return SaveResult(True, version, revised_statement=revised, path=path)
