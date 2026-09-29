"""Data-quality checks and results (plan 04 §4; plan 10 §13; AC-F02.x).

Every check produces a `DqResult` with an ID `DQ.<area>.<name>`; results go to the run's
`data_quality` block, the `dq_results` table, and `AUD.DATA.VALIDATION_FAIL` events on failure.
A failed check never silently "fixes" data: bad rows are reported, and the verdict for that stock
is blocked downstream (Phase 2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

DQ_ID = re.compile(r"^DQ\.[a-z_]+\.[a-z0-9_]+$")
Status = Literal["pass", "warn", "fail"]


@dataclass(frozen=True)
class DqResult:
    check_id: str
    isin: str  # "*" for run-level checks
    status: Status
    detail: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not DQ_ID.match(self.check_id):
            raise ValueError(f"malformed DQ check id {self.check_id!r} (want DQ.<area>.<name>)")


def worst(results: list[DqResult]) -> Status:
    statuses = {r.status for r in results}
    return "fail" if "fail" in statuses else "warn" if "warn" in statuses else "pass"
