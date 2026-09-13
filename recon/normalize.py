"""Shared normalization layer (``10_IMPLEMENTATION_PLAN.md`` Phase 4).

Canonicalizes cross-tool observations into a single deduplicated asset surface.
Hostname canonicalization deliberately delegates to the already-green
``core.scope_guard.normalize_host`` so path/scope validation and normalization
never disagree. Deduplication is intentionally **narrow** - only exact
canonical-equivalent variants collapse (case, surrounding whitespace, one
trailing root dot); ``www.example.com`` vs ``example.com`` remain DISTINCT
(Phase 4 risk: over-aggressive normalization must never merge genuinely
different assets).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

from core.scope_guard import normalize_host


def normalize_hostname(host: str | None) -> str | None:
    """Canonical form of a single hostname (lowercase, no trailing dot).

    Delegates to the scope guard's normalization so DNS/httpx/subfinder and the
    Scope Guard resolve to the same canonical surface. Returns ``None`` for
    empty/whitespace-only input.
    """
    if host is None:
        return None
    return normalize_host(host) or None


def canonical_assets(hosts: Iterable[str | None]) -> Iterator[str]:
    """Yield deduplicated, normalized hostnames (first-seen wins, order kept)."""
    seen: set[str] = set()
    for host in hosts:
        canon = normalize_hostname(host)
        if canon is None or canon in seen:
            continue
        seen.add(canon)
        yield canon


def dedupe_observations(
    observations: Iterable[Any],
    *,
    host_key: str = "host",
) -> Iterator[Any]:
    """Collapse duplicate asset variants (one canonical host per program).

    ``host_key`` names the attribute holding the (possibly unnormalized)
    hostname on each observation; values normalizing to the same canonical
    host are emitted only for their first occurrence. Preserves document
    order.
    """
    seen: set[str] = set()
    for obs in observations:
        host = getattr(obs, host_key, None)
        canon = normalize_hostname(host)
        if canon is not None:
            if canon in seen:
                continue
            seen.add(canon)
        yield obs
