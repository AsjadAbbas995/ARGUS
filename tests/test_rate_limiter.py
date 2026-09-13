"""Rate Limiter tests (``04_SCOPE_SAFETY.md`` §Rate Limiting).

Deterministic: time is injected, so no real sleeps. Verifies global,
per-host, and per-tool request/concurrency limits, and the ``limit()`` context
manager release behavior.
"""

from __future__ import annotations

import threading

import pytest

from core.config import LimitsConfig
from core.rate_limiter import RateLimiter, RateLimits


class FakeClock:
    def __init__(self, start: float = 0.0):
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, delta: float) -> None:
        self.t += delta


class FakeSleeper:
    def __init__(self, clock: FakeClock):
        self.clock = clock
        self.calls: list[float] = []

    def __call__(self, duration: float) -> None:
        self.calls.append(duration)
        self.clock.advance(duration)

    @property
    def total(self) -> float:
        return sum(self.calls)


def make(rps: float = 10.0, concurrency: int = 5, **overrides) -> tuple[RateLimiter, FakeClock, FakeSleeper]:
    clock = FakeClock()
    sleeper = FakeSleeper(clock)
    limiter = RateLimiter(
        RateLimits(requests_per_second=rps, concurrency=concurrency),
        clock=clock,
        sleeper=sleeper,
        **overrides,
    )
    return limiter, clock, sleeper


def exhausted(limiter: RateLimiter, host: str, n: int) -> None:
    for _ in range(n):
        limiter.acquire(host=host)


def test_burst_capacity_immediate() -> None:
    limiter, clock, sleeper = make(rps=10.0, concurrency=5)
    for _ in range(5):
        limiter.acquire()
    assert sleeper.calls == []
    assert clock.t == 0.0


def test_rate_limit_after_capacity_exhausted() -> None:
    limiter, clock, sleeper = make(rps=10.0, concurrency=5)
    exhausted(limiter, "example.com", 5)
    limiter.acquire(host="example.com")
    assert clock.t == pytest.approx(0.1)
    assert sleeper.total == pytest.approx(0.1)


def test_rate_accumulates_over_time() -> None:
    limiter, clock, sleeper = make(rps=10.0, concurrency=2)
    for _ in range(2):
        limiter.acquire()
    for _ in range(10):
        limiter.acquire()
    assert clock.t == pytest.approx(1.0)
    assert len(sleeper.calls) == 10


def test_concurrency_is_respected() -> None:
    limiter, clock, sleeper = make(rps=5.0, concurrency=2)
    limiter.acquire(host="example.com")
    limiter.acquire(host="example.com")
    # No permits available: third acquire must wait.
    limiter.acquire(host="example.com")
    assert clock.t > 0
    assert sleeper.total > 0


def test_release_returns_permit() -> None:
    limiter, clock, sleeper = make(rps=1.0, concurrency=2)
    limiter.acquire(host="example.com")
    limiter.acquire(host="example.com")
    limiter.release(host="example.com")
    before = clock.t
    limiter.acquire(host="example.com")
    assert clock.t == before  # permit returned → immediate


def test_per_host_tighter_than_global() -> None:
    limiter, clock, sleeper = make(
        rps=10.0, concurrency=5, per_host={"slow.example.com": RateLimits(requests_per_second=1.0, concurrency=1)}
    )
    prior = sleeper.total
    exhausted(limiter, "slow.example.com", 1)
    limiter.acquire(host="slow.example.com")
    total_slow = sleeper.total - prior
    assert total_slow >= 1.0  # 1 rps
    # A different host uses global limits, no extra delay at burst.
    clock.advance(10.0)
    sleeper_start = sleeper.total
    for _ in range(5):
        limiter.acquire(host="fast.example.com")
    assert sleeper.total == sleeper_start  # burst permits within global capacity


def test_per_tool_limit_applies_in_addition_to_global() -> None:
    limiter, clock, sleeper = make(
        rps=10.0, concurrency=5, per_tool={"subfinder": RateLimits(requests_per_second=1.0, concurrency=1)}
    )
    exhausted(limiter, "example.com", 1)
    limiter.acquire(host="example.com", tool="subfinder")  # burst token
    limiter.acquire(host="example.com", tool="subfinder")  # must wait 1s
    assert sleeper.total >= 1.0


def test_limit_context_manager_releases() -> None:
    limiter, clock, sleeper = make(rps=1.0, concurrency=2)
    with limiter.limit(host="example.com") as guard:
        pass
    assert guard is not None
    before = clock.t
    limiter.acquire(host="example.com")
    assert clock.t == before


def test_from_config_builds_limiter() -> None:
    config = LimitsConfig(requests_per_second=20, concurrency=8)
    limiter = RateLimiter.from_config(config)
    assert limiter._global == RateLimits(requests_per_second=20, concurrency=8)


def test_no_permits_with_zero_rps_block_forever() -> None:
    # rps=0 must not spin; acquirer sleeps indefinitely (never returns).
    clock = FakeClock()
    slept_inf = threading.Event()

    def sleeper(duration: float) -> None:
        if duration == float("inf"):
            slept_inf.set()
            slept_inf.wait()  # block forever, do not advance the clock
        else:
            clock.advance(duration)

    limiter = RateLimiter(
        RateLimits(requests_per_second=0.0, concurrency=1),
        clock=clock,
        sleeper=sleeper,
    )
    limiter.acquire(host="example.com")  # consume the single initial token

    def attempt():
        limiter.acquire(host="example.com")

    t = threading.Thread(target=attempt, daemon=True)
    t.start()
    assert slept_inf.wait(timeout=1.0)
    t.join(timeout=0.1)
    assert t.is_alive()