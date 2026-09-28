"""Cost and rate guardrails (C3.6)."""

import pytest

from parakh.guardrails import Budget, BudgetExceeded, RateLimiter


def test_budget_stops_spending() -> None:
    budget = Budget(max_usd=0.01)
    budget.check()
    budget.spend(0.02)
    with pytest.raises(BudgetExceeded):
        budget.check()


def test_rate_limiter_waits_when_full() -> None:
    now = [0.0]
    slept: list[float] = []

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        now[0] += seconds

    limiter = RateLimiter(per_minute=2, clock=lambda: now[0], sleep=sleep)
    limiter.acquire()
    limiter.acquire()
    limiter.acquire()  # third call must wait for the window
    assert slept and slept[0] == pytest.approx(60)
