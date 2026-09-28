"""Cost and rate guardrails per workflow run (C3.6)."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable


class BudgetExceeded(Exception):
    """The run has spent its budget; stop calling the LLM."""


class Budget:
    def __init__(self, max_usd: float) -> None:
        self.max_usd = max_usd
        self.spent_usd = 0.0
        self._lock = threading.Lock()

    def check(self) -> None:
        if self.spent_usd >= self.max_usd:
            raise BudgetExceeded(f"spent ${self.spent_usd:.4f} of ${self.max_usd:.2f}")

    def spend(self, usd: float) -> None:
        with self._lock:
            self.spent_usd += usd


class RateLimiter:
    """Sliding-window limiter: at most `per_minute` calls in any 60 seconds."""

    def __init__(
        self,
        per_minute: int,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.per_minute = per_minute
        self._clock = clock
        self._sleep = sleep
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = self._clock()
                while self._calls and now - self._calls[0] >= 60:
                    self._calls.popleft()
                if len(self._calls) < self.per_minute:
                    self._calls.append(now)
                    return
                wait = 60 - (now - self._calls[0])
            self._sleep(max(wait, 0.01))
