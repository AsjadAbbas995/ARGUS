"""Tool Runner Command Safety Tests (``13_TESTING_STRATEGY.md`` §Command Safety Tests).

Verifies: ``shell=False`` everywhere a subprocess is invoked, commands are
argument arrays never shell strings, no command-injection path from untrusted
target input, timeouts are enforced, stdout/stderr/exit code are captured, raw
output is preserved under ``storage/raw/<tool>/``, env/cwd are controlled, and
secrets never reach logs. No test depends on a live external target or tool
binary: every command runs through ``sys.executable``.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

from core.tool_runner import (
    CommandResult,
    ToolRunner,
    ToolRunnerError,
    ToolTimeoutError,
    ToolUnavailableError,
)
from recon.base import ToolAdapter, ToolExecution, ToolUnavailable
from recon.base import ScopeViolation


PY = sys.executable
PASS = [PY, "-c", "import sys; sys.exit(0)"]
ECHO_STDOUT = [PY, "-c", "import sys; sys.stdout.write('hello-world')"]
ECHO_STDERR = [PY, "-c", "import sys; sys.stderr.write('boom-diagnostic')"]
EXIT_3 = [PY, "-c", "import sys; sys.exit(3)"]
SLEEP_LONG = [PY, "-c", "import time; time.sleep(30)"]


@pytest.fixture
def runner(tmp_path: Path) -> ToolRunner:
    return ToolRunner(raw_dir=tmp_path / "storage/raw", timeout=2.0)


def test_uses_shell_false_never_shell_true(monkeypatch, runner: ToolRunner) -> None:
    captured: dict = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs

        class Proc:
            returncode = 0
            stdout = ""
            stderr = ""

        return Proc()

    monkeypatch.setattr("core.tool_runner.subprocess.run", fake_run)
    runner.run_command([PY, "-c", "pass"], tool="fake")
    assert "shell" in captured["kwargs"] and captured["kwargs"]["shell"] is False


def test_command_is_argument_array_never_shell_string(runner: ToolRunner) -> None:
    # A shell would expand/interpret `$(...)`, `;`, `&`, and globs. As an
    # argument array they must arrive verbatim.
    probe = "$(touch pwned) ; & * | > < `ls`"
    result = runner.run_command(
        [PY, "-c", "import sys; sys.stdout.write(sys.argv[1])", probe],
        tool="argtest",
    )
    assert result.stdout == probe


def test_no_command_injection_from_untrusted_input(runner: ToolRunner) -> None:
    # Crafted host-like payload must stay a literal argument (never awaited,
    # never piped). Use .venv python to avoid any injection side effects.
    payload = "example.com; malicious" + chr(9) + "flag"
    result = runner.run_command(
        [PY, "-c", "import sys; sys.stdout.write(sys.argv[1])", payload],
        tool="inject",
    )
    assert result.stdout == payload


def test_stdout_stderr_and_exit_code_captured(runner: ToolRunner) -> None:
    result = runner.run_command(ECHO_STDOUT, tool="capture")
    assert result.exit_code == 0
    assert result.stdout == "hello-world"

    err_result = runner.run_command(ECHO_STDERR, tool="capture")
    assert err_result.exit_code == 0
    assert err_result.stderr == "boom-diagnostic"

    fail_result = runner.run_command(EXIT_3, tool="capture")
    assert fail_result.exit_code == 3  # reported, not raised


def test_timeout_is_enforced_and_raises(runner: ToolRunner) -> None:
    with pytest.raises(ToolTimeoutError):
        runner.run_command(SLEEP_LONG, tool="sleeper", timeout=0.2)


def test_timeout_preserves_partial_raw_output(tmp_path: Path) -> None:
    runner = ToolRunner(raw_dir=tmp_path / "storage/raw", timeout=2.0)
    slow_talker = [
        PY,
        "-c",
        "import sys, time; "
        "sys.stdout.write('partial-line-'); sys.stdout.flush(); time.sleep(30)",
    ]
    with pytest.raises(ToolTimeoutError):
        runner.run_command(slow_talker, tool="sleeper", timeout=0.2)
    refs = list((tmp_path / "storage/raw" / "sleeper").glob("*.out"))
    assert refs, "expected partial raw output preserved on timeout"
    assert (tmp_path / "storage/raw" / "sleeper").exists()


def test_raw_output_preserved_under_storage_raw(runner: ToolRunner) -> None:
    result = runner.run_command(ECHO_STDOUT, tool="rawtest")
    assert result.raw_output_ref
    raw_path = Path(result.raw_output_ref)
    assert raw_path.exists()
    assert raw_path.parent.name == "rawtest"
    assert raw_path.read_text(encoding="utf-8") == "hello-world"


def test_env_is_controlled(runner: ToolRunner) -> None:
    with_secret = [PY, "-c", "import os, sys; sys.stdout.write(os.environ.get('ARGUS_TEST_SECRET',''))"]
    result = runner.run_command(with_secret, tool="envtest", env={"ARGUS_TEST_SECRET": "topsecret"})
    assert result.stdout == "topsecret"

    without = runner.run_command(with_secret, tool="envtest", env={"ARGUS_TEST_SECRET": ""})
    assert without.stdout == ""


def test_cwd_is_controlled(tmp_path: Path, runner: ToolRunner) -> None:
    target = tmp_path / "storage" / "raw"
    target.mkdir(parents=True)
    result = runner.run_command(
        [PY, "-c", "import os, sys; sys.stdout.write(os.getcwd())"],
        tool="cwdt",
        cwd=target,
    )
    assert result.stdout.replace("/", "\\") == str(target).replace("/", "\\")


def test_missing_binary_raises_structured_unavailable(tmp_path: Path) -> None:
    runner = ToolRunner(raw_dir=tmp_path / "storage/raw", timeout=2.0)
    with pytest.raises(ToolUnavailableError):
        runner.run_command(["definitely-not-a-real-binary-argus"], tool="ghost")


def test_non_list_or_empty_command_rejected(runner: ToolRunner) -> None:
    with pytest.raises(ToolRunnerError):
        runner.run_command([], tool="bad")
    with pytest.raises(ToolRunnerError):
        runner.run_command(["ok", None], tool="bad")  # type: ignore[list-item]


def test_secrets_never_reach_logs(caplog, runner: ToolRunner) -> None:
    runner.secrets = ("super-secret-value",)
    with caplog.at_level(logging.DEBUG, logger="argus.tool_runner"):
        runner.run_command([PY, "-c", "import sys; sys.stderr.write('super-secret-value')"], tool="leak")
    assert "super-secret-value" not in caplog.text


def test_redact_masks_secrets(runner: ToolRunner) -> None:
    runner.secrets = ("hunter2",)
    assert "hunter2" not in runner.redact("password=hunter2 yes")


# ---------------------------------------------------------------------------
# Adapter contract skeleton (06_TOOL_CONTRACTS.md) smoke coverage
# ---------------------------------------------------------------------------


class _FakeAdapter(ToolAdapter):
    name = "fake"
    executables = ()

    def validate(self, task, scope):
        self._require_in_scope(getattr(task, "target", ""), scope)

    def build_command(self, task, config):
        return [PY, "-c", "import sys; sys.stdout.write('artifact-1\\nartifact-2')"]

    def parse(self, result: CommandResult):
        return [line for line in result.stdout.splitlines() if line]


class _Task:
    def __init__(self, target: str):
        self.target = target


def test_adapter_execute_contract(
    tmp_path: Path,
) -> None:
    from core.scope_guard import ScopeGuard, ScopeRule

    runner = ToolRunner(raw_dir=tmp_path / "storage/raw", timeout=2.0)
    scope = ScopeGuard([ScopeRule(rule_type="domain", value="example.com", allowed=True)])
    exec_result = _FakeAdapter().execute(_Task("www.example.com"), runner, None, scope)
    assert isinstance(exec_result, ToolExecution)
    assert exec_result.exit_code == 0
    assert exec_result.artifacts == ("artifact-1", "artifact-2")
    assert exec_result.raw_output_ref and Path(exec_result.raw_output_ref).exists()


def test_adapter_scope_violation(tmp_path: Path) -> None:
    from core.scope_guard import ScopeGuard, ScopeRule

    runner = ToolRunner(raw_dir=tmp_path / "storage/raw", timeout=2.0)
    scope = ScopeGuard([ScopeRule(rule_type="domain", value="example.com", allowed=True)])
    with pytest.raises(ScopeViolation):
        _FakeAdapter().execute(_Task("evil.example.org"), runner, None, scope)


def test_adapter_unavailable(tmp_path: Path) -> None:
    from core.scope_guard import ScopeGuard, ScopeRule

    class _MissingTool(_FakeAdapter):
        name = "missing"
        executables = ("definitely-not-a-real-binary-argus",)

    runner = ToolRunner(raw_dir=tmp_path / "storage/raw", timeout=2.0)
    scope = ScopeGuard([ScopeRule(rule_type="domain", value="example.com", allowed=True)])
    with pytest.raises(ToolUnavailable):
        _MissingTool().execute(_Task("www.example.com"), runner, None, scope)