"""Safe Tool Runner (``06_TOOL_CONTRACTS.md`` §Tool Runner).

Executes approved commands as argument arrays via ``subprocess.run(..., shell=False)``
**never** as shell strings, captures stdout/stderr/exit code, enforces per-invocation
timeouts, controls environment and working directory, preserves raw output under
``storage/raw/<tool>/``, and returns structured error objects on failure.

Secrets are never written to logs: the runner only logs the tool name, timeout,
exit code, duration, and (redacted) diagnostics.
"""

from __future__ import annotations

import os
import secrets as _secrets_module
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from core.logging_setup import get_logger


class ToolRunnerError(Exception):
    """Base structured failure produced by the Tool Runner."""


class ToolUnavailableError(ToolRunnerError):
    """The executable could not be found/invoked."""


class ToolTimeoutError(ToolRunnerError):
    """The command exceeded its configured timeout and was terminated."""


@dataclass(frozen=True)
class CommandResult:
    """Captured outcome of one tool invocation.

    Non-zero exit codes are *reported, not raised*: the caller (adapter/
    orchestrator) logs and continues, per the degrade-gracefully policy.
    """

    tool: str
    command: list[str]
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    duration_ms: float = 0.0
    raw_output_ref: Optional[str] = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ToolRunner:
    """Controlled ``subprocess`` boundary.

    ``raw_dir`` is the preservation root (default ``storage/raw`` from
    ``14_CONFIG_EXAMPLE.md`` §storage.raw). ``timeout`` is the default per
    invocation; callers may override. ``env``/``cwd`` default to the current
    process environment / working directory but are always overridable so the
    caller fully controls what the tool sees.
    """

    raw_dir: Path = Path("storage/raw")
    timeout: float = 60.0
    env: Optional[dict] = None
    cwd: Optional[Path] = None
    secrets: Iterable[str] = ()
    logger: object = field(default_factory=lambda: get_logger("argus.tool_runner"))

    def __post_init__(self) -> None:
        # Keep the field iterable regardless of whether a tuple/list/... was passed.
        self.secrets = tuple(s for s in (self.secrets or ()) if s)

    # -- execution ----------------------------------------------------------

    def run_command(
        self,
        command: list[str],
        *,
        tool: str,
        timeout: Optional[float] = None,
        env: Optional[dict] = None,
        cwd: Optional[Path] = None,
    ) -> CommandResult:
        """Execute ``command`` as an argument array and capture its outcome.

        Raw output (stdout + stderr) is preserved under ``storage/raw/<tool>/``
        and referenced by ``result.raw_output_ref``. Raises
        :class:`ToolUnavailableError` if the executable is missing and
        :class:`ToolTimeoutError` if ``timeout`` is exceeded (partial output is
        still preserved). Non-zero exits are returned in
        :class:`CommandResult.exit_code` (not raised).
        """
        self._validate_command(command, tool)
        effective_timeout = self.timeout if timeout is None else timeout
        effective_env = self._merge_env(env)
        effective_cwd = cwd or self.cwd

        started = time.monotonic()
        raw_ref: Optional[str] = None
        try:
            proc = subprocess.run(
                command,
                shell=False,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                env=effective_env,
                cwd=str(effective_cwd) if effective_cwd else None,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ToolUnavailableError(
                f"{tool}: executable not found for command {self.redact(' '.join(command))}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            partial = (exc.stdout or "") + (exc.stderr or "")
            if partial:
                raw_ref = self.save_raw(
                    tool, partial, extension="out", tag="timeout"
                )
            duration_ms = (time.monotonic() - started) * 1000.0
            self._log_timeout(tool, effective_timeout, duration_ms, raw_ref)
            raise ToolTimeoutError(
                f"{tool}: timed out after {effective_timeout:g}s during "
                f"{self.redact(' '.join(command))}"
            ) from exc

        raw_content = (proc.stdout or "") + (proc.stderr or "")
        if raw_content:
            raw_ref = self.save_raw(tool, raw_content, extension="out", tag="tool")

        duration_ms = (time.monotonic() - started) * 1000.0
        result = CommandResult(
            tool=tool,
            command=list(command),
            exit_code=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            timed_out=False,
            duration_ms=duration_ms,
            raw_output_ref=raw_ref,
        )
        self._log_result(result, effective_timeout)
        return result

    # -- raw output preservation ---------------------------------------------

    def save_raw(
        self,
        tool: str,
        content: str,
        *,
        extension: str = "out",
        tag: str = "tool",
    ) -> str:
        """Persist raw tool output under ``storage/raw/<tool>/``.

        Returns the reference string stored in ``tool_runs.raw_output_ref``
        (``storage/raw/<tool>/<timestamp>_<tag>_<nonce>.out``).
        """
        safe_tool = _sanitize_filename(tool)
        safe_tag = _sanitize_filename(tag)
        directory = self.raw_dir / safe_tool
        directory.mkdir(parents=True, exist_ok=True)
        filename = (
            f"{_utcnow().strftime('%Y%m%dT%H%M%SZ')}_{safe_tag}_"
            f"{_secrets_module.token_hex(4)}.{_sanitize_filename(extension)}"
        )
        path = directory / filename
        path.write_text(content, encoding="utf-8")
        return str(path)

    # -- diagnostics ---------------------------------------------------------

    def redact(self, text: str) -> str:
        """Mask configured secrets before any text reaches a log."""
        result = text
        for secret in self.secrets or ():
            if secret:
                result = result.replace(secret, "<redacted>")
        return result

    # -- internals -----------------------------------------------------------

    def _validate_command(self, command: list[str], tool: str) -> None:
        if not isinstance(command, list) or not command:
            raise ToolRunnerError(
                f"{tool}: command must be a non-empty argument array (list[str]), "
                f"got {command!r}"
            )
        for arg in command:
            if not isinstance(arg, str):
                raise ToolRunnerError(
                    f"{tool}: command arguments must be strings, got {arg!r}"
                )

    def _merge_env(self, env: Optional[dict]) -> dict:
        base = dict(os.environ if self.env is None else self.env)
        if env:
            base.update(env)
        merged: dict = {}
        for key, value in base.items():
            merged[str(key)] = str(value)
        return merged

    def _log_result(self, result: CommandResult, timeout: float) -> None:
        details = (
            f"tool={result.tool} exit={result.exit_code} "
            f"duration_ms={result.duration_ms:,.0f} timeout={timeout:g}"
        )
        if result.raw_output_ref:
            details += f" raw={result.raw_output_ref}"
        if result.timed_out or (result.exit_code is not None and result.exit_code != 0):
            self.logger.warning(f"tool run non-zero/failed: {details}")
        else:
            self.logger.info(f"tool run ok: {details}")

    def _log_timeout(
        self, tool: str, timeout: float, duration_ms: float, raw_ref: Optional[str]
    ) -> None:
        details = (
            f"tool run timeout: tool={tool} timeout={timeout:g} "
            f"duration_ms={duration_ms:,.0f}"
        )
        if raw_ref:
            details += f" raw={raw_ref}"
        self.logger.warning(details)


def is_executable_on_path(name: str) -> bool:
    """Whether ``name`` resolves to an executable on ``PATH`` (platform-neutral)."""
    return shutil.which(name) is not None


def _sanitize_filename(value: str) -> str:
    """Keep a value safe for use as a filename/path segment."""
    cleaned = "".join(c if c.isalnum() or c in "._-" else "_" for c in value)
    return cleaned.strip("._") or "tool"