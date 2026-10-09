"""`jobs.request_refresh`: an agent may ask for a single-stock refresh, a few times a day (AG-05).

A request is a row, not an action. The daily event job drains the queue (`drain`) and runs the
qualitative refresh for each stock. At most `jobs.refresh_daily_cap` requests are accepted per IST
day, and none while a monthly run holds the lock (AC-F25.4), so an agent cannot spin the pipeline.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

from parakh.audit.ids import new_ulid
from parakh.services.view_models import RefreshOut
from parakh.watch.state import StateStore

NAME = "job_requests"
LOCK = "monthly_lock"
ReasonCode = Literal["new_transcript", "new_results", "material_filing", "data_gap"]
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


class JobRequest(BaseModel):
    request_id: str = Field(default_factory=new_ulid)
    isin: str
    reason_code: ReasonCode
    client: str
    day: dt.date
    requested_at: dt.datetime
    status: Literal["queued", "done", "skipped", "failed"] = "queued"
    result: str = ""


def ist_day(now: dt.datetime) -> dt.date:
    return now.astimezone(IST).date()


class JobRequests:
    def __init__(self, store: StateStore, daily_cap: int) -> None:
        self.store, self.daily_cap = store, daily_cap

    def all(self) -> list[JobRequest]:
        return [JobRequest.model_validate(r) for r in self.store.load(NAME).get("rows", [])]

    def _save(self, rows: list[JobRequest]) -> None:
        self.store.save(NAME, {"rows": [r.model_dump(mode="json") for r in rows[-500:]]})

    def monthly_running(self) -> bool:
        return bool(self.store.load(LOCK).get("running"))

    def lock_monthly(self, running: bool) -> None:
        self.store.save(LOCK, {"running": running})

    def request(
        self, isin: str, reason_code: ReasonCode, client: str, now: dt.datetime | None = None
    ) -> RefreshOut:
        now = now or dt.datetime.now(dt.UTC)
        day = ist_day(now)
        rows = self.all()
        used = [r for r in rows if r.day == day]
        if self.monthly_running():
            return RefreshOut(
                queued=False, remaining_today=max(0, self.daily_cap - len(used)),
                message="A monthly run is in progress; ask again after it finishes.",
            )  # fmt: skip
        if any(r.isin == isin and r.status == "queued" for r in rows):
            return RefreshOut(
                queued=False, remaining_today=max(0, self.daily_cap - len(used)),
                message="A refresh for this stock is already queued.",
            )  # fmt: skip
        if len(used) >= self.daily_cap:
            return RefreshOut(
                queued=False,
                remaining_today=0,
                message=f"Daily refresh cap of {self.daily_cap} reached; it resets at midnight IST.",
            )
        req = JobRequest(
            isin=isin, reason_code=reason_code, client=client, day=day, requested_at=now
        )
        self._save([*rows, req])
        return RefreshOut(
            queued=True,
            request_id=req.request_id,
            remaining_today=self.daily_cap - len(used) - 1,
            message="Queued. The daily job refreshes the qualitative read for this stock.",
        )

    def queued(self) -> list[JobRequest]:
        return [r for r in self.all() if r.status == "queued"]

    def finish(
        self, request_id: str, status: Literal["done", "skipped", "failed"], result: str
    ) -> None:
        rows = self.all()
        for r in rows:
            if r.request_id == request_id:
                r.status, r.result = status, result
        self._save(rows)
