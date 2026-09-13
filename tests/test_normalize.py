"""Normalization edge-case tests (``10_IMPLEMENTATION_PLAN.md`` Phase 4).

The Phase-4 acceptance criteria are:
- duplicate **variants** of the same asset collapse to one row
  (``WWW.example.com.`` / ``www.example.com`` -> ``www.example.com``);
- the documented **over-normalization risk** never fires: genuinely distinct
  assets (``www.example.com`` vs ``example.com``) must NOT merge;

and the Phase-4 risk ("over-aggressive normalization merging genuinely
distinct assets") is asserted explicitly so a future too-greedy rule fails
loudly instead of silently destroying cardinality.

Canonical form (single source of truth): ``scope_guard.normalize_host`` —
lowercase, no trailing dot, no leading/trailing whitespace.
"""

from __future__ import annotations

from recon.normalize import (
    canonical_assets,
    dedupe_observations,
    normalize_hostname,
)


# -- canonical form ------------------------------------------------------------


def test_normalize_hostname_lowercases() -> None:
    assert normalize_hostname("WWW.Example.com") == "www.example.com"


def test_normalize_hostname_strips_trailing_dot() -> None:
    assert normalize_hostname("www.example.com.") == "www.example.com"
    assert normalize_hostname("WWW.example.COM..") == "www.example.com"


def test_normalize_hostname_strips_whitespace() -> None:
    assert normalize_hostname("  www.example.com  ") == "www.example.com"


def test_normalize_hostname_none_and_empty() -> None:
    assert normalize_hostname(None) is None
    assert normalize_hostname("") is None
    assert normalize_hostname("   ") is None


def test_normalize_hostname_keeps_www_and_bare_distinct() -> None:
    """Documented over-normalization risk -- MUST NOT merge these."""
    assert normalize_hostname("www.example.com") != normalize_hostname(
        "example.com"
    )


# -- dedup ---------------------------------------------------------------------


def test_canonical_assets_collapses_variants() -> None:
    raw = ["WWW.example.com.", "www.example.com", "WWW.Example.COM.", "api.example.com"]
    assert list(canonical_assets(raw)) == [
        "www.example.com",
        "api.example.com",
    ]


def test_canonical_assets_preserves_first_seen_order() -> None:
    """Case/trailing-dot and genuinely distinct assets, first-seen order kept."""
    raw = ["b.api.example.com", "api.example.com", "A.api.example.com"]
    assert list(canonical_assets(raw)) == [
        "b.api.example.com",
        "api.example.com",
        "a.api.example.com",
    ]


def test_canonical_assets_keeps_www_and_bare_distinct() -> None:
    """Over-normalization risk: www vs bare must remain two rows."""
    raw = ["www.example.com", "example.com", "www.example.com."]
    assert list(canonical_assets(raw)) == [
        "www.example.com",
        "example.com",
    ]


def test_canonical_assets_handles_none_and_empty() -> None:
    assert list(canonical_assets(["", None, "  ", "app.example.com"])) == [
        "app.example.com"
    ]


# -- observation-level dedup ---------------------------------------------------


class _Obs:
    def __init__(self, key: str, host: str) -> None:
        self.key = key
        self.host = host


def test_dedupe_observations_collapses_by_host() -> None:
    raw = [
        _Obs("a", "WWW.example.com."),
        _Obs("b", "www.example.com"),
        _Obs("c", "api.example.com"),
    ]
    out = list(dedupe_observations(raw))
    assert [o.key for o in out] == ["a", "c"]


def test_dedupe_observations_missing_host_preserved() -> None:
    raw = [_Obs("x", "app.example.com"), object(), _Obs("y", "APP.example.com")]
    out = list(dedupe_observations(raw))
    assert [getattr(o, "key", None) for o in out] == ["x", None]
