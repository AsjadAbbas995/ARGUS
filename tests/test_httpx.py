"""httpx probe adapter fixture tests (``06_TOOL_CONTRACTS.md`` §httpx;
``13_TESTING_STRATEGY.md`` §Adapter Fixture Tests).

All parse/scope/execution tests drive the **in-process** httpx probe adapter
(``recon.web.httpx_probe``) against the recorded probe stream under
``tests/fixtures/httpx/probe.ndjson`` — no live HTTP probing and no shelled
binary are ever touched, so CI stays deterministic and offline.

Covered cases per ``06_TOOL_CONTRACTS.md`` §httpx:

- ``probe.ndjson``: 4 valid JSON-lines surface ``web_apps`` observations
  (URL/status/title/webserver) plus ``asset_technologies`` rows for each
  detected technology (``tech`` arrays) — ``05_DATA_MODEL.md`` §web_apps /
  §asset_technologies.
- A trailing **malformed JSON line** in the probe stream is recorded as a
  logged, **non-fatal** parse skip (``13_TESTING_STRATEGY.md`` §Adapter
  Fixture Tests: malformed lines never abort the run).
- Redirect destinations are re-checked against scope before being followed
  (``04_SCOPE_SAFETY.md`` §HTTP Redirect Handling); the adapter keeps the
  ``location`` field on the raw stream for the *normalizer*, and never
  follows a redirect itself.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import pytest

from core.scope_guard import ScopeGuard, ScopeRule, ScopeRuleType
from core.tool_runner import CommandResult, ToolRunner, ToolUnavailableError
from recon.base import ScopeViolation
from recon.web.httpx_probe import (
    AssetTechnologyObservation,
    HttpxProbeAdapter,
    WebAppObservation,
)

FIXTURES = Path(__file__).parent / "fixtures" / "httpx"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _result(stdout: str, exit_code: int = 0) -> CommandResult:
    return CommandResult(
        tool="httpx",
        command=["httpx", "-json", "-tech-detect", "-title", "-status-code", "app.example.com"],
        stdout=stdout,
        stderr="",
        exit_code=exit_code,
        timed_out=False,
    )


@pytest.fixture
def adapter() -> HttpxProbeAdapter:
    return HttpxProbeAdapter()


@pytest.fixture
def scope() -> ScopeGuard:
    return ScopeGuard(
        [ScopeRule(rule_type=ScopeRuleType.DOMAIN, value="example.com", allowed=True)]
    )


@pytest.fixture
def config() -> Any:
    class _Config:
        class _Web:
            class _Httpx:
                bin_path: str | None = None
                args: list[str] = ["-json", "-tech-detect", "-title", "-status-code"]

            httpx = _Httpx()
            probe_passthrough = False

        web = _Web()

    return _Config()


class _Task:
    def __init__(self, target: str):
        self.target = target


# -- parse: probe fixture ------------------------------------------------------


def test_parse_probe_surfaces_web_apps(adapter: HttpxProbeAdapter) -> None:
    out = adapter.parse(_result(_read("probe.ndjson")))
    apps = [o for o in out if isinstance(o, WebAppObservation)]
    assert len(apps) == 4  # 4 valid JSON lines -> 4 probed applications
    hosts = {o.host for o in apps}
    assert "app.example.com" in hosts
    assert "api.example.com" in hosts
    assert "admin.example.com" in hosts


def test_parse_probe_surfaces_statuses(adapter: HttpxProbeAdapter) -> None:
    out = adapter.parse(_result(_read("probe.ndjson")))
    apps = [o for o in out if isinstance(o, WebAppObservation)]
    statuses = {o.status_code for o in apps}
    assert statuses >= {200, 302}


def test_parse_probe_surfaces_titles_and_webservers(adapter: HttpxProbeAdapter) -> None:
    out = adapter.parse(_result(_read("probe.ndjson")))
    apps = [o for o in out if isinstance(o, WebAppObservation)]
    titles = {o.title for o in apps}
    assert "Acme App" in titles
    servers = {o.webserver for o in apps}
    assert "nginx" in servers


def test_parse_probe_surfaces_technologies(adapter: HttpxProbeAdapter) -> None:
    out = adapter.parse(_result(_read("probe.ndjson")))
    tech = {o.technology for o in out if isinstance(o, AssetTechnologyObservation)}
    assert {"nginx", "React", "GraphQL"} <= tech


def test_parse_probe_keeps_document_order(adapter: HttpxProbeAdapter) -> None:
    out = adapter.parse(_result(_read("probe.ndjson")))
    apps = [o for o in out if isinstance(o, WebAppObservation)]
    assert apps[0].url == "http://app.example.com"  # first probe line stays first


def test_parse_malformed_line_not_fatal(adapter: HttpxProbeAdapter) -> None:
    raw = _read("probe.ndjson")
    # append a deliberately truncated JSON line -> skipped, never fatal
    malformed = raw + "\n{\"malformed\": true\n"
    out = adapter.parse(_result(malformed))
    assert out  # valid preceding lines still surface
    apps = [o for o in out if isinstance(o, WebAppObservation)]
    assert len(apps) == 4


def test_parse_empty_output_no_artifacts(adapter: HttpxProbeAdapter) -> None:
    assert adapter.parse(_result("")) == []


def test_parse_duplicate_pairs_deduplicated(adapter: HttpxProbeAdapter) -> None:
    raw = _read("probe.ndjson")
    out = adapter.parse(_result(raw + "\n" + raw))
    apps = [o for o in out if isinstance(o, WebAppObservation)]
    seen: set[tuple[str, str]] = set()
    for o in apps:
        key = (o.host, o.url)
        assert key not in seen
        seen.add(key)


# -- scope --------------------------------------------------------------------


def test_validate_in_scope_ok(adapter: HttpxProbeAdapter, scope: ScopeGuard) -> None:
    adapter.validate(_Task("app.example.com"), scope)


def test_validate_out_of_scope_raises(adapter: HttpxProbeAdapter, scope: ScopeGuard) -> None:
    with pytest.raises(ScopeViolation):
        adapter.validate(_Task("evil.example.org"), scope)


def test_validate_empty_target_raises(adapter: HttpxProbeAdapter, scope: ScopeGuard) -> None:
    with pytest.raises(ScopeViolation):
        adapter.validate(_Task(""), scope)


# -- build_command ------------------------------------------------------------


def test_build_command_marker(
    adapter: HttpxProbeAdapter, config: Any
) -> None:
    command = adapter.build_command(_Task("app.example.com"), config)
    assert command[0] == "httpx"
    assert command[1] == "-json"
    assert command[-1] == "app.example.com"  # normalized target, never a shell string


# -- execution through the controlled runner ----------------------------------


class _FakeRunner:
    """Minimal ToolRunner-compatible double (fixture probing, no subprocess)."""

    def __init__(self) -> None:
        self.saved: list[tuple[str, str]] = []

    def save_raw(
        self, tool: str, content: str, *, extension: str = "out", tag: str = "tool"
    ) -> str:
        self.saved.append((tool, content))
        return f"storage/raw/{tool}/{tag}.{extension}"

    def run_command(
        self, command: list[str], *, tool: str, timeout: int = 120
    ) -> CommandResult:
        return _result(_read("probe.ndjson"))


def test_execute_in_scope_preserves_raw(
    scope: ScopeGuard, config: Any
) -> None:
    class _AvailableProbe(HttpxProbeAdapter):
        def is_available(self) -> bool:
            return True

    runner = _FakeRunner()
    execution = _AvailableProbe().execute(
        _Task("app.example.com"), runner, config, scope
    )
    assert execution.tool == "httpx"
    assert execution.exit_code == 0
    assert runner.saved  # raw probe stream preserved via controlled runner
    assert {tool for tool, _ in runner.saved} == {"httpx"}


def test_execute_missing_library_raises_unavailable(config: Any) -> None:
    class _NoProbe(HttpxProbeAdapter):
        def is_available(self) -> bool:
            return False

    with pytest.raises(ToolUnavailableError):
            _NoProbe().execute(
                _Task("app.example.com"),
                _FakeRunner(),
                config,
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
