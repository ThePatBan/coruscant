"""Rate-limiter abstraction for the anonymous surfaces (Phase 7, Scope D).

The default is an in-process fixed-window limiter — dependency-free and correct for a
single instance / local dev. ``RateLimiter`` is the seam a shared/distributed limiter
(Redis, Memcached, a gateway) slots into for a horizontally-scaled deployment, where
per-instance counting would let ``N`` instances admit ``N×`` the budget. Keeping the
port here (not in the FastAPI app) means the limiter never imports the web framework
and stays unit-testable.

``build_rate_limiter`` selects the backend from config. Only ``memory`` is implemented
today; asking for another backend fails loudly (fail-closed) rather than silently
degrading to per-instance limiting.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import threading
import time


class RateLimiter(ABC):
    """A per-key request budget over a fixed window.

    Implementations MUST be safe under concurrent calls. ``allow`` registers one hit
    for ``key`` and returns whether it stays within budget — never raises, so callers
    own the HTTP concern (a 429)."""

    @abstractmethod
    def allow(self, key: str) -> bool:
        """Register one hit for ``key``; return ``False`` if it exceeds the budget."""
        raise NotImplementedError


class InProcessFixedWindowRateLimiter(RateLimiter):
    """Per-key fixed-window limiter held in process memory.

    Right-sized for a single-instance launch; a horizontally-scaled deployment would
    move to a shared backend (see ``build_rate_limiter``). ``limit_per_minute <= 0``
    disables limiting (every call is allowed)."""

    def __init__(self, limit_per_minute: int) -> None:
        self.limit = limit_per_minute
        self._lock = threading.Lock()
        self._buckets: dict[str, tuple[int, int]] = {}  # key -> (window_minute, count)

    def allow(self, key: str) -> bool:
        if self.limit <= 0:
            return True
        now_minute = int(time.time() // 60)
        with self._lock:
            window, count = self._buckets.get(key, (now_minute, 0))
            if window != now_minute:  # new window: reset
                window, count = now_minute, 0
            count += 1
            self._buckets[key] = (window, count)
            return count <= self.limit


def build_rate_limiter(limit_per_minute: int, *, backend: str = "memory") -> RateLimiter:
    """Construct the limiter for ``backend``.

    ``memory`` (default) is the in-process fixed-window limiter. A shared/distributed
    backend is a documented seam: implement ``RateLimiter`` against the store and wire
    it here. Selecting an unimplemented backend raises rather than silently limiting
    per-instance — a scaled deployment fails closed until the shared limiter is wired."""
    if backend == "memory":
        return InProcessFixedWindowRateLimiter(limit_per_minute)
    raise ValueError(
        f"unsupported rate-limit backend {backend!r}: only 'memory' is implemented — "
        "wire a shared RateLimiter (e.g. Redis) here before selecting a distributed backend"
    )
