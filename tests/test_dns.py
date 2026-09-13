"""DNS Resolver adapter fixture tests (``06_TOOL_CONTRACTS.md`` §DNS Resolver;
``13_TESTING_STRATEGY.md`` §Adapter Fixture Tests).

All parse/scope/execution tests drive the **in-process** DNS resolver
adapter (``recon.dns.resolver`) from recorded fixtures under
``tests/fixtures/dns/`` — no live resolver and no shelled binary are ever
touched, so CI is deterministic.

Covered cases per ``06_TOOL_CONTRACTS.md`` §DNS Resolver:

- ``normal.json``: A/AAAA (IP surface), MX, NS, TXT
- ``nxdomain.json``: NXDOMAIN carried in ``errors`` (no records, **not fatal**)
- ``partial_timeout.json``: partial records + a per-record-type timeout
  (partial output still returned)
- ``full_types.json``: every declared record type present
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import pytest

from core.scope_guard import ScopeDecision, ScopeGuard, ScopeRule, ScopeRuleType
from core.tool_runner import CommandResult, ToolRunner, ToolUnavailableError
from recon.base import ScopeViolation
from recon.dns.resolver import (
    DnsResolverAdapter,
    RECORD_TYPES,
    ResolutionResult,
    ip_observations,
    parse_resolution,
)

FIXTURES = Path(__file__).parent / "fixtures" / "dns"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _result(stdout: str, exit_code: int = 0) -> CommandResult:
    return CommandResult(
        tool="dns",
        command=["dns-resolve", "example.com"],
        stdout=stdout,
        stderr="",
        exit_code=exit_code,
        timed_out=False,
    )


@pytest.fixture
def adapter() -> DnsResolverAdapter:
    return DnsResolverAdapter()


@pytest.fixture
def scope() -> ScopeGuard:
    return ScopeGuard(
        [ScopeRule(rule_type=ScopeRuleType.DOMAIN, value="example.com", allowed=True)]
    )


@pytest.fixture
def config() -> Any:
    class _Config:
        class _Dns:
            timeout = 2.0
            record_types = RECORD_TYPES

        dns = _Dns()

    return _Config()


class _Task:
    def __init__(self, target: str):
        self.target = target


# -- parse: normal fixture --------------------------------------------------


def test_parse_normal_fixture(adapter: DnsResolverAdapter) -> None:
    out = adapter.parse(_result(_read("normal.json")))
    hosts = {o.hostname for o in out if hasattr(o, "hostname")}
    assert "example.com" in hosts
    types = {o.record_type for o in out if hasattr(o, "record_type")}
    assert {"A", "AAAA", "MX", "NS", "TXT"} <= types


def test_parse_normal_surfaces_ips(adapter: DnsResolverAdapter) -> None:
    out = adapter.parse(_result(_read("normal.json")))
    ips = {o.address for o in out if hasattr(o, "address")}
    assert "93.184.216.34" in ips
    assert "93.184.216.35" in ips
    assert "2606:2800:220:1::248:1893" in ips


def test_parse_normal_document_order_kept(adapter: DnsResolverAdapter) -> None:
    out = adapter.parse(_result(_read("normal.json")))
    records = [o for o in out if hasattr(o, "value") and hasattr(o, "record_type")]
    assert records[0].value == "93.184.216.34"  # first A record stays first


def test_parse_collapses_duplicate_pairs(adapter: DnsResolverAdapter) -> None:
    out = adapter.parse(_result(_read("normal.json")))
    seen: set[tuple[str, str]] = set()
    for o in out:
        if hasattr(o, "value") and hasattr(o, "record_type"):
            key = (o.record_type, o.value)
            assert key not in seen
            seen.add(key)


# -- parse: NXDOMAIN --------------------------------------------------------


def test_parse_nxdomain_not_fatal(adapter: DnsResolverAdapter) -> None:
    raw = _read("nxdomain.json")
    data = json.loads(raw)
    out = adapter.parse(_result(raw))
    records = [o for o in out if hasattr(o, "value") and hasattr(o, "record_type")]
    assert records == []  # NXDOMAIN yields no records
    assert data["errors"]  # error still carried on the raw resolution
    assert {"A", "AAAA"} <= set(data["errors"])


# -- parse: partial timeout --------------------------------------------------


def test_parse_partial_timeout_returns_partial(adapter: DnsResolverAdapter) -> None:
    raw = _read("partial_timeout.json")
    data = json.loads(raw)
    out = adapter.parse(_result(raw))
    records = [o for o in out if hasattr(o, "value") and hasattr(o, "record_type")]
    assert records  # partial records are still recovered
    assert any("TIMEOUT" in (v or "") for v in data.get("errors", {}).values())


def test_parse_partial_timeout_not_fatal_when_all_timed_out(
    adapter: DnsResolverAdapter,
) -> None:
    out = adapter.parse(_result('{"host": "dead.example.com", "errors": {"A": "TIMEOUT"}, "records": []}'))
    assert [o for o in out if hasattr(o, "address")] == []


# -- parse: full types ------------------------------------------------------


def test_parse_full_types_parse_resolution(adapter: DnsResolverAdapter) -> None:
    data = json.loads(_read("full_types.json"))
    observed = parse_resolution(data)
    types = {o.record_type for o in observed}
    assert types == set(RECORD_TYPES)


def test_parse_full_types_ip_observations(adapter: DnsResolverAdapter) -> None:
    data = json.loads(_read("full_types.json"))
    observed = parse_resolution(data)
    ips = {o.address for o in ip_observations(observed)}
    # RFC5737/3849 test-net addresses from the deterministic fixture
    # (never live-world ``example.com`` addresses: `13_TESTING_STRATEGY.md`
    # §Deterministic).
    assert ips >= {"198.51.100.7", "2001:db8::7"}


def test_parse_full_types_via_adapter(adapter: DnsResolverAdapter) -> None:
    out = adapter.parse(_result(_read("full_types.json")))
    assert out  # records + IP observations both surface


# -- scope -------------------------------------------------------------------


def test_validate_in_scope_ok(adapter: DnsResolverAdapter, scope: ScopeGuard) -> None:
    adapter.validate(_Task("sub.example.com"), scope)


def test_validate_out_of_scope_raises(
    adapter: DnsResolverAdapter, scope: ScopeGuard
) -> None:
    with pytest.raises(ScopeViolation):
        adapter.validate(_Task("evil.example.org"), scope)


def test_validate_empty_target_raises(adapter: DnsResolverAdapter, scope: ScopeGuard) -> None:
    with pytest.raises(ScopeViolation):
        adapter.validate(_Task(""), scope)


# -- build_command -------------------------------------------------------------


def test_build_command_marker(adapter: DnsResolverAdapter, config: Any) -> None:
    command = adapter.build_command(_Task("www.example.com"), config)
    assert command[0] == "dns-resolve"
    assert command[1] == "www.example.com"  # normalized target, never a shell string


# -- execution through the controlled runner -----------------------------------


class _FakeRunner:
    """Minimal ToolRunner-compatible double (in-process DNS: no subprocess)."""

    def __init__(self) -> None:
        self.saved: list[tuple[str, str]] = []

    def save_raw(
        self, tool: str, content: str, *, extension: str = "out", tag: str = "tool"
    ) -> str:
        self.saved.append((tool, content))
        return f"storage/raw/{tool}/{tag}.{extension}"


def test_execute_in_scope_preserves_raw(adapter: DnsResolverAdapter, scope: ScopeGuard, config: Any) -> None:
    runner = _FakeRunner()
    execution = adapter.execute(_Task("example.com"), runner, config, scope)
    assert execution.tool == "dns"
    assert execution.exit_code == 0
    assert runner.saved  # raw resolution preserved via controlled runner
    assert {tool for tool, _ in runner.saved} == {"dns"}


def test_execute_missing_library_raises_unavailable() -> None:
    class _NoDns(DnsResolverAdapter):
        def is_available(self) -> bool:
            return False

    with pytest.raises(ToolUnavailableError):
        _NoDns().execute(
            _Task("example.com"),
            _FakeRunner(),
            object(),
            ScopeGuard(
                [
                    ScopeRule(
                        rule_type=ScopeRuleType.DOMAIN,
                        value="example.com",
                        allowed=True,
                    )
                ]
            ),
        )
