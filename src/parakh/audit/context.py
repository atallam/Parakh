"""RunContext: the identity every step, log line, audit event and snapshot carries (plan 10 §3).

Create one per job with `RunContext.create(...)` and pass it everywhere. It binds `run_id`
into structlog's context, so every log line of the run can be found by searching the ID.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import structlog

from parakh import __version__
from parakh.audit.events import IST, ActorType
from parakh.audit.ids import new_ulid
from parakh.config import REPO_ROOT, config_dir, get_settings


@lru_cache(maxsize=1)
def code_version() -> str:
    """Git commit SHA of the running code: GITHUB_SHA in Actions, else `git rev-parse`."""
    sha = os.environ.get("GITHUB_SHA")
    if sha:
        return sha[:12]
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def config_hash(directory: Path | None = None) -> str:
    """SHA-256 over every config/*.yaml (path + bytes), so any config change changes the hash."""
    root = directory or config_dir()
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.yaml")) if root.exists() else []:
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


@dataclass
class StepRecord:
    """One row of the step ledger (plan 10 §5; `run_steps` table)."""

    step_id: str
    name: str
    seq: int
    started_at: dt.datetime
    ended_at: dt.datetime | None = None
    status: str = "running"  # running | ok | failed
    inputs: dict[str, object] = field(default_factory=dict)
    outputs: dict[str, object] = field(default_factory=dict)
    error: str | None = None

    @property
    def duration_ms(self) -> float | None:
        if self.ended_at is None:
            return None
        return round((self.ended_at - self.started_at).total_seconds() * 1000, 1)


@dataclass
class RunContext:
    """Identity and provenance for one job run."""

    run_id: str
    mode: str  # monthly | watch | events | dummy | mcp-session | …
    asof: dt.date
    env: str
    actor_type: ActorType
    actor_id: str
    trigger: str  # cron | manual | event
    code_version: str
    config_hash: str
    framework_version: str
    started_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.UTC))
    steps: list[StepRecord] = field(default_factory=list)
    _step_seq: int = 0

    @classmethod
    def create(
        cls,
        *,
        mode: str,
        asof: dt.date | None = None,
        actor_type: ActorType = "user",
        actor_id: str = "avinash",
        trigger: str = "manual",
    ) -> RunContext:
        ctx = cls(
            run_id=new_ulid(),
            mode=mode,
            asof=asof or dt.datetime.now(IST).date(),  # IST trading date (plan 04 §4 #12)
            env=get_settings().app_env,
            actor_type=actor_type,
            actor_id=actor_id,
            trigger=trigger,
            code_version=code_version(),
            config_hash=config_hash(),
            framework_version=__version__,
        )
        structlog.contextvars.bind_contextvars(run_id=ctx.run_id)
        return ctx

    def start_step(self, name: str, inputs: dict[str, object] | None = None) -> StepRecord:
        """Open a ledger row with id `<run_id>.<step_name>.<seq>` (plan 10 §3)."""
        self._step_seq += 1
        record = StepRecord(
            step_id=f"{self.run_id}.{name}.{self._step_seq:02d}",
            name=name,
            seq=self._step_seq,
            started_at=dt.datetime.now(dt.UTC),
            inputs=dict(inputs or {}),
        )
        self.steps.append(record)
        return record

    @property
    def actor(self) -> str:
        return f"{self.actor_type}:{self.actor_id}"
