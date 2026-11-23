"""A small circuit breaker for calls to a partner.

closed     calls go through; count failures in a row
open       calls are refused at once until the
           cool-down has passed
half_open  one trial call goes through; success
           closes the breaker, failure opens it again
"""

import time
from collections.abc import Callable


class CircuitBreaker:
    def __init__(
        self,
        failures: int,
        reset_after_s: float,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.max_failures = failures
        self.reset_after_s = reset_after_s
        self.clock = clock
        self.state = "closed"
        self.failures = 0
        self.changed_at = clock()

    def allow(self) -> bool:
        if self.state == "closed":
            return True
        waited = self.clock() - self.changed_at
        if waited < self.reset_after_s:
            return False  # open, or a trial is running
        # Cool-down over (or a trial never reported
        # back): let exactly one call through.
        self._move("half_open")
        return True

    def record_success(self) -> None:
        self.failures = 0
        if self.state != "closed":
            self._move("closed")

    def record_failure(self) -> None:
        self.failures += 1
        if (self.state == "half_open"
                or self.failures >= self.max_failures):
            self._move("open")

    def _move(self, state: str) -> None:
        self.state = state
        self.changed_at = self.clock()
