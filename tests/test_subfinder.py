"""Subfinder adapter fixture tests (``13_TESTING_STRATEGY.md`` §Adapter Fixture Tests).

All parsing uses recorded output under ``tests/fixtures/subfinder/`` — no live
tool invocation, so CI never depends on an external subfinder binary or target.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.scope_guard import ScopeGuard, ScopeRule
from core.tool_runner import CommandResult
from recon.base import ScopeViolation
from recon.subdomains.subfinder import SubfinderAdapter

FIXTURES = Path(__file__).parent / "fixtures" / "subfinder"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _result(stdout: str, exit_code: int = 0) -> CommandResult:
    return CommandResult(tool="subfinder", command=[], stdout=stdout, exit_code=exit_code)


@pytest.fixture
def adapter() -> SubfinderAdapter:
    return SubfinderAdapter()


@pytest.fixture
def scope() -> ScopeGuard:
    return ScopeGuard(
        [ScopeRule(rule_type="domain", value="example.com", allowed=True)]
    )


@pytest.fixture
def config():
    class _Config:
        class _Recon:
            aggressive_subdomain_discovery = True

        recon = _Recon()

    return _Config()


class _Task:
    def __init__(self, target: str):
        self.target = target


# -- parse: normal ----------------------------------------------------------


def test_parse_normal_fixture(adapter: SubfinderAdapter) -> None:
    out = adapter.parse(_result(_read("normal.ndjson")))
    assert out == [
        "app.example.com",
        "api.example.com",
        "dev.example.com",
        "staging.example.com",
        "admin.example.com",
    ]


def test_parse_is_sorted_and_deduplicated(adapter: SubfinderAdapter) -> None:
    out = adapter.parse(
        _result('{"host": "b.example.com"}\n{"host": "a.example.com"}\n{"host": "b.example.com"}\n')
    )
    assert out == ["b.example.com", "a.example.com"]


# -- parse: malformed / partial --------------------------------------------


def test_parse_malformed_lines_skipped(adapter: SubfinderAdapter) -> None:
    out = adapter.parse(_result(_read("malformed.ndjson")))
    # Valid entries survive; non-JSON, wrong-type, broken, and duplicate lines drop.
    assert out == [
        "app.example.com",  # duplicate preserved once
        "mail.example.com",  # trailing spaces trimmed
        "www.example.com",  # trailing root dot stripped
        "api.example.com",
    ]


def test_parse_empty_output(adapter: SubfinderAdapter) -> None:
    assert adapter.parse(_result(_read("empty.ndjson"))) == []
    assert adapter.parse(_result("")) == []


def test_parse_partial_output_no_crash(adapter: SubfinderAdapter) -> None:
    out = adapter.parse(_result('{"host": "ok.example.com"}\npartial-tail'))
    assert out == ["ok.example.com"]


def test_parse_wildcards_excluded(adapter: SubfinderAdapter) -> None:
    out = adapter.parse(_result(_read("wildcard.ndjson")))
    assert out == ["real.example.com"]


def test_parse_nonzero_exit_still_parses_partial(adapter: SubfinderAdapter) -> None:
    out = adapter.parse(_result('{"host": "kept.example.com"}', exit_code=1))
    assert out == ["kept.example.com"]


# -- command construction ---------------------------------------------------


def test_build_command(adapter: SubfinderAdapter, config) -> None:
    command = adapter.build_command(_Task("Example.COM"), config)
    assert command[0] == "subfinder"
    assert command[1] == "-d"
    assert command[2] == "example.com"  # normalized command target
    assert command[3] == "-json"
    assert command[4] == "-all"  # aggressive discovery enabled


def test_build_command_without_all_flag(adapter: SubfinderAdapter) -> None:
    class _Config:
        class _Recon:
            aggressive_subdomain_discovery = False

        recon = _Recon()

    command = adapter.build_command(_Task("example.com"), _Config())
    assert command == ["subfinder", "-d", "example.com", "-json"]


def test_build_command_rejects_empty_target(adapter: SubfinderAdapter) -> None:
    with pytest.raises(ValueError):
        adapter.build_command(_Task("  "), None)


# -- scope ------------------------------------------------------------------


def test_validate_in_scope_ok(adapter: SubfinderAdapter, scope) -> None:
    adapter.validate(_Task("sub.example.com"), scope)


def test_validate_out_of_scope_raises(
    adapter: SubfinderAdapter, scope: ScopeGuard
) -> None:
    with pytest.raises(ScopeViolation):
        adapter.validate(_Task("evil.example.org"), scope)


# -- integration: execute through a fake runner -----------------------------


def test_execute_contract_end_to_end(adapter: SubfinderAdapter, config, scope) -> None:
    class _FakeRunner:
        def __init__(self):
            self.saved: list[tuple[str, str]] = []

        def run_command(self, command, *, tool):
            assert tool == "subfinder"
            assert command[0] == "subfinder"
            return _result(_read("normal.ndjson"))

        def save_raw(self, tool, content, *, extension="out", tag="tool"):
            self.saved.append((tool, content))
            return f"storage/raw/{tool}/fake.out"

    class _AvailableSubfinder(SubfinderAdapter):
        def is_available(self) -> bool:
            return True

    runner = _FakeRunner()
    execution = _AvailableSubfinder().execute(_Task("example.com"), runner, config, scope)
    assert execution.tool == "subfinder"
    assert execution.exit_code == 0
    assert "app.example.com" in execution.artifacts
    assert "real.example.com" not in execution.artifacts


def test_execute_unavailable_tool_is_skip_not_crash(tmp_path: Path, config, scope) -> None:
    from core.tool_runner import ToolRunner
    from recon.base import ToolUnavailable

    class _MissingSubfinder(SubfinderAdapter):
        executables = ("definitely-not-installed-subfinder-argus",)

    runner = ToolRunner(raw_dir=tmp_path / "storage/raw", timeout=2.0)
    with pytest.raises(ToolUnavailable):
        _MissingSubfinder().execute(_Task("example.com"), runner, config, scope)