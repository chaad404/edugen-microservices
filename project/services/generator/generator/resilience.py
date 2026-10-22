"""
Protection around calls to a model host (course chapter 6.5-6.6):

- RateLimiter: spaces requests so a model never sees more than its `rpm` (ported from the thesis)
- CircuitBreaker: after repeated technical failures, fails fast for a while instead of hammering the host
- RetryPolicy: exponential backoff with full jitter; HTTP 429 waits out most of a rate-limit window
"""
import random
import threading
import time
from typing import Callable, Optional

from .providers.base import ProviderError


class RateLimiter:
    def __init__(self, rpm: float, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.min_interval = 60.0 / rpm if rpm else 0.0
        self._clock, self._sleep = clock, sleep
        self._lock = threading.Lock()
        self._next_slot = 0.0

    def wait(self) -> None:
        if not self.min_interval:
            return
        with self._lock:
            now = self._clock()
            slot = max(now, self._next_slot)
            self._next_slot = slot + self.min_interval
        if slot > now:
            self._sleep(slot - now)


class CircuitOpen(ProviderError):
    """Raised without calling the host while the breaker is open. Retryable: the host may recover."""


class CircuitBreaker:
    CLOSED, OPEN, HALF_OPEN = "closed", "open", "half_open"

    def __init__(self, failure_threshold: int = 5, reset_timeout: float = 30.0,
                 clock: Callable[[], float] = time.monotonic):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self._clock = clock
        self._lock = threading.Lock()
        self.state = self.CLOSED
        self.failures = 0
        self.opened_at = 0.0

    def before_call(self) -> None:
        with self._lock:
            if self.state == self.OPEN:
                if self._clock() - self.opened_at < self.reset_timeout:
                    raise CircuitOpen("Circuit open: the host failed repeatedly; not calling it for now.")
                self.state = self.HALF_OPEN  # let one trial call through

    def record_success(self) -> None:
        with self._lock:
            self.state, self.failures = self.CLOSED, 0

    def record_failure(self) -> None:
        with self._lock:
            self.failures += 1
            if self.state == self.HALF_OPEN or self.failures >= self.failure_threshold:
                self.state, self.opened_at = self.OPEN, self._clock()


class RetryPolicy:
    def __init__(self, base: float = 2.0, cap: float = 60.0, rng: Optional[random.Random] = None):
        self.base, self.cap = base, cap
        self.rng = rng or random.Random()

    def delay(self, attempt: int, error: Optional[Exception]) -> float:
        """Seconds to wait before attempt `attempt + 1`."""
        if isinstance(error, ProviderError) and error.status == 429:
            # Free tiers count requests per minute: wait out most of a window (thesis rule), or what the host asks
            return max(error.retry_after or 0.0, 20.0 * attempt + self.rng.uniform(0, 5))
        if isinstance(error, ProviderError) and error.retry_after:
            return min(self.cap, error.retry_after)
        return self.rng.uniform(0, min(self.cap, self.base * 2 ** attempt))
