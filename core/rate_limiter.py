"""Deterministic Rate Limiter (``04_SCOPE_SAFETY.md`` §Rate Limiting).

Enforces global, per-host, and per-tool request-per-second and concurrency
limits (``02_ARCHITECTURE.md``). Time is injected so tests run without real
sleeping. Defaults come from ``core.config.LimitsConfig``
(``14_CONFIG_EXAMPLE.md`` §limits).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from core.config import LimitsConfig

#: Float tolerance: a bucket is "full enough" within this margin. Without it,
#: token refill can asymptotically approach ``1.0`` (float drift) and the wait
#: loop would spin forever. A sub-microtoken head-start per acquisition is
#: negligible next to whole-second rate budgets.
_EPSILON = 1e-9


@dataclass(frozen=True)
class RateLimits:
    requests_per_second: float = 10.0
    concurrency: int = 5

    @classmethod
    def from_config(cls, limits: LimitsConfig) -> "RateLimits":
        return cls(
            requests_per_second=limits.requests_per_second,
            concurrency=limits.concurrency,
        )


class _Bucket:
    """Token-bucket gate: capacity = concurrency, refill = rps.

    A token is consumed on acquire() and returned on release(), so in-flight
    work never exceeds ``concurrency`` while sustained throughput never exceeds
    ``requests_per_second``.
    """

    __slots__ = ("capacity", "refill", "tokens", "last_refill")

    def __init__(self, rps: float, concurrency: int):
        self.capacity = max(1, int(concurrency))
        self.refill = max(0.0, float(rps))
        self.tokens = float(self.capacity)
        self.last_refill = -1.0

    def accumulate(self, now: float) -> None:
        """Refill tokens from elapsed real time (injected clock)."""
        if self.last_refill < 0:
            self.last_refill = now
            return
        elapsed = max(0.0, now - self.last_refill)
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill)
        self.last_refill = now

    def wait_for_token(self, now: float) -> float:
        self.accumulate(now)
        if self.tokens >= 1.0 - _EPSILON:
            return 0.0
        if self.refill <= 0:
            return float("inf")
        return (1.0 - self.tokens) / self.refill


class RateLimiter:
    """Rate limit over a set of independent token buckets.

    ``global_limits`` always applies. Optional per-host and per-tool buckets
    are applied in addition (all must be satisfied before a permit is granted).
    """

    def __init__(
        self,
        global_limits: RateLimits,
        per_host: Optional[dict[str, RateLimits]] = None,
        per_tool: Optional[dict[str, RateLimits]] = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self._clock = clock
        self._sleep = sleeper
        self._global: RateLimits = global_limits
        self._per_host: dict[str, RateLimits] = dict(per_host or {})
        self._per_tool: dict[str, RateLimits] = dict(per_tool or {})
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_config(
        cls,
        limits: LimitsConfig,
        *,
        per_host: Optional[dict[str, RateLimits]] = None,
        per_tool: Optional[dict[str, RateLimits]] = None,
    ) -> "RateLimiter":
        return cls(
            RateLimits.from_config(limits),
            per_host=per_host,
            per_tool=per_tool,
        )

    # -- public API --------------------------------------------------------

    def acquire(self, host: Optional[str] = None, tool: Optional[str] = None) -> None:
        """Block until a permit for this host/tool is available, then consume it."""
        keys = ["global"]
        if host:
            keys.append(f"host:{host}")
        if tool:
            keys.append(f"tool:{tool}")
        buckets = [self._bucket(key, self._limits_for(key)) for key in keys]
        while True:
            now = self._clock()
            with self._lock:
                wait = max(b.wait_for_token(now) for b in buckets)
                if wait <= 0:
                    for b in buckets:
                        b.tokens -= 1.0
                    return
            self._sleep(wait)

    def release(self, host: Optional[str] = None, tool: Optional[str] = None) -> None:
        """Return a previously acquired permit."""
        keys = ["global"]
        if host:
            keys.append(f"host:{host}")
        if tool:
            keys.append(f"tool:{tool}")
        with self._lock:
            for key in keys:
                bucket = self._buckets.get(key)
                if bucket is not None:
                    bucket.tokens = min(bucket.capacity, bucket.tokens + 1.0)

    def limit(self, host: Optional[str] = None, tool: Optional[str] = None):
        """Context manager acquiring a permit on enter and releasing on exit."""

        class _Guard:
            def __enter__(self):
                self.acquire()
                return self

            def acquire(self) -> None:
                outer.acquire(host=host, tool=tool)

            def __exit__(self, *_exc) -> None:
                outer.release(host=host, tool=tool)

        outer = self
        return _Guard()

    # -- internals ---------------------------------------------------------

    def _limits_for(self, key: str) -> RateLimits:
        if key == "global":
            return self._global
        if key.startswith("host:"):
            host = key[5:]
            if host in self._per_host:
                return self._per_host[host]
            return self._global
        if key.startswith("tool:"):
            tool = key[5:]
            if tool in self._per_tool:
                return self._per_tool[tool]
            return self._global
        return self._global

    def _bucket(self, key: str, limits: RateLimits) -> _Bucket:
        bucket = self._buckets.get(key)
        if bucket is None:
            with self._lock:
                bucket = self._buckets.get(key)
                if bucket is None:
                    bucket = _Bucket(
                        rps=limits.requests_per_second,
                        concurrency=limits.concurrency,
                    )
                    self._buckets[key] = bucket
        return bucket

    def loose_per_host(self, host: str) -> RateLimits:
        """Per-host limits; used by tests to assert enforced rates."""
        if host in self._per_host:
            return self._per_host[host]
        return self._global