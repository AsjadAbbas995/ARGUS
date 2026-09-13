"""Scope Guard tests (``13_TESTING_STRATEGY.md`` §Scope Tests).

Covers: allowed target, excluded target, out-of-scope redirect, out-of-scope
discovered host, disallowed port, and the authoritative Redirect and
Discovered-Target Policy (``04_SCOPE_SAFETY.md``).
"""

from __future__ import annotations

import pytest

from core.config import ScopeConfig
from core.scope_guard import (
    ScopeDecision,
    ScopeGuard,
    ScopeRule,
    ScopeRuleType,
    extract_host,
    normalize_host,
)


def build_guard() -> ScopeGuard:
    return ScopeGuard.from_config(
        ScopeConfig(
            allowed_domains=("example.com",),
            allowed_ips=(),
            excluded=("internal-staging.example.com",),
        )
    )


ALLOWED = ["example.com", "www.example.com", "app.example.com"]
EXCLUDED = ["internal-staging.example.com", "a.internal-staging.example.com"]
OUT_OF_SCOPE_HOSTS = ["attacker.io", "example.net", "other-domain.example"]


@pytest.mark.parametrize("host", ALLOWED)
def test_allowed_target(host: str) -> None:
    assert build_guard().check_host(host).in_scope is True


@pytest.mark.parametrize("host", EXCLUDED)
def test_excluded_target(host: str) -> None:
    decision = build_guard().check_host(host)
    assert decision.in_scope is False
    assert "excluded" in decision.reason


@pytest.mark.parametrize("host", OUT_OF_SCOPE_HOSTS)
def test_out_of_scope_discovered_host(host: str) -> None:
    assert build_guard().check_host(host).in_scope is False


def test_out_of_scope_redirect_rejected() -> None:
    decision = build_guard().check_redirect(
        "https://example.com/", "https://other-domain.example/"
    )
    assert decision.allowed is False
    assert decision.destination_in_scope is False


def test_in_scope_redirect_allowed() -> None:
    decision = build_guard().check_redirect(
        "https://www.example.com/", "https://app.example.com/"
    )
    assert decision.allowed is True
    assert decision.destination_in_scope is True


def test_redirect_to_excluded_host_rejected() -> None:
    decision = build_guard().check_redirect(
        "https://example.com/", "https://internal-staging.example.com/"
    )
    assert decision.allowed is False
    assert decision.destination_in_scope is False


def test_dns_discovered_ip_out_of_cidr_rejected() -> None:
    guard = ScopeGuard.from_config(
        ScopeConfig(allowed_domains=("example.com",), allowed_ips=("203.0.113.0/24",))
    )
    assert guard.check_ip("203.0.113.17").in_scope is True
    assert guard.check_ip("198.51.100.9").in_scope is False


def test_exact_ip_allowed() -> None:
    guard = ScopeGuard.from_config(
        ScopeConfig(allowed_domains=(), allowed_ips=("198.51.100.7",))
    )
    assert guard.check_ip("198.51.100.7").in_scope is True
    assert guard.check_ip("198.51.100.8").in_scope is False


def test_explicit_ip_exclusion_wins() -> None:
    guard = ScopeGuard(
        [
            ScopeRule(rule_type=ScopeRuleType.CIDR, value="203.0.113.0/24", allowed=True),
            ScopeRule(rule_type=ScopeRuleType.IP, value="203.0.113.10", allowed=False),
        ]
    )
    assert guard.check_ip("203.0.113.11").in_scope is True
    assert guard.check_ip("203.0.113.10").in_scope is False


@pytest.mark.parametrize("port", [80, 443, 1000])
def test_allowed_port_in_range(port: int) -> None:
    guard = ScopeGuard(
        [ScopeRule(rule_type=ScopeRuleType.PORT, value="1-1000", allowed=True)]
    )
    assert guard.check_port(port).in_scope is True


def test_disallowed_port_rejected_outside_range() -> None:
    guard = ScopeGuard(
        [ScopeRule(rule_type=ScopeRuleType.PORT, value="1-1000", allowed=True)]
    )
    assert guard.check_port(8443).in_scope is False


def test_no_port_rules_means_unrestricted() -> None:
    assert build_guard().check_port(9999).in_scope is True
    assert build_guard().check_port(1).in_scope is True


def test_check_accepts_full_urls() -> None:
    guard = build_guard()
    assert guard.check("https://www.example.com:443/path?q=1").in_scope is True
    assert guard.check("http://example.com/admin").in_scope is True
    assert guard.check("attacker.io/login").in_scope is False


def test_normalize_host_strips_case_and_dot() -> None:
    assert normalize_host("WWW.Example.COM.") == "www.example.com"


def test_extract_host_from_url() -> None:
    assert extract_host("https://app.example.com/x") == "app.example.com"
    assert extract_host("203.0.113.7") == "203.0.113.7"
    assert extract_host("app.example.com:8080/path") == "app.example.com"


def test_same_domain_redirect_loop_allowed_both_ways() -> None:
    guard = build_guard()
    assert guard.check_redirect(
        "http://example.com/", "http://example.net/"
    ).allowed is False
    assert guard.check_redirect(
        "http://www.example.com/", "http://example.com/"
    ).allowed is True


def test_subdomain_rule_targeted() -> None:
    guard = ScopeGuard(
        [
            ScopeRule(
                rule_type=ScopeRuleType.SUBDOMAIN, value="app.example.com", allowed=True
            )
        ]
    )
    assert guard.check_host("app.example.com").in_scope is True
    assert guard.check_host("api.app.example.com").in_scope is True
    assert guard.check_host("example.com").in_scope is False
    assert guard.check_host("www.example.com").in_scope is False


def test_rejected_decision_is_loggable() -> None:
    guard = build_guard()
    decision = guard.check_host("example.net")
    assert isinstance(decision, ScopeDecision)
    assert decision.in_scope is False
    assert "example.net" in decision.reason


def test_empty_scope_rejects_everything() -> None:
    guard = ScopeGuard.from_config(ScopeConfig(allowed_domains=(), allowed_ips=()))
    assert guard.check_host("example.com").in_scope is False
    assert guard.check_host("anything.io").in_scope is False


def test_from_row_accepts_dicts_and_objects() -> None:
    row_dict = {"rule_type": "domain", "value": "Example.COM.", "allowed": True}
    row_obj = ScopeRule(rule_type="domain", value="EXAMPLE.com.", allowed=True)
    guard = ScopeGuard([row_dict, row_obj])
    assert guard.check_host("www.example.com").in_scope is True