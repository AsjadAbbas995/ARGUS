"""Tool Adapter base contract (``06_TOOL_CONTRACTS.md`` §Tool Adapter Interface).

Every adapter MUST, in order:
  1. verify availability            (``is_available``)
  2. validate the task against scope (``validate``)
  3. construct the command as an argument array (``build_command``)
  4. execute through the controlled Tool Runner (``core.tool_runner``)
  5. preserve raw output            (runner saves under ``storage/raw/<tool>/``)
  6. parse output                   (``parse``)
  7. normalize observations into canonical objects (returned objects)

``execute`` is provided here as a template so concrete adapters only implement
the tool-specific pieces; subclasses may override it when the execution shape
differs (e.g. the DNS resolver is an in-process library call, not a subprocess).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from core.scope_guard import ScopeGuard, extract_host
from core.tool_runner import CommandResult, ToolRunner, ToolUnavailableError


class ScopeViolation(ValueError):
    """Raised when a task target is not permitted by the task's scope."""


class ToolUnavailable(Exception):
    """Raised when an adapter's binary is not installed/available.

    Callers (orchestrator/task runner) catch this, log a warning, and continue
    with the other available discovery sources (``06_TOOL_CONTRACTS.md``
    §Missing-Tool Handling).
    """


@dataclass(frozen=True)
class ToolExecution:
    """Everything one tool execution produced, ready for normalization."""

    tool: str
    command: list[str]
    exit_code: Optional[int]
    raw_output_ref: Optional[str]
    artifacts: tuple[Any, ...] = field(default_factory=tuple)
    timed_out: bool = False
    error: Optional[str] = None


class ToolAdapter(ABC):
    """Interface implemented by every external-tool adapter."""

    name: str = "tool"

    #: Candidate executable names searched on PATH when the adapter shells out.
    executables: tuple[str, ...] = ()

    # -- availability -------------------------------------------------------

    def is_available(self) -> bool:
        """Whether the underlying binary can be found on PATH."""
        from core.tool_runner import is_executable_on_path

        if not self.executables:
            return True  # in-process adapters (DNS, crt, httpx-python) are always available
        return any(is_executable_on_path(name) for name in self.executables)

    # -- scope --------------------------------------------------------------

    @abstractmethod
    def validate(self, task: Any, scope: ScopeGuard) -> None:
        """Reject out-of-scope tasks by raising :class:`ScopeViolation`."""

    def _require_in_scope(self, target: str, scope: ScopeGuard) -> None:
        decision = scope.check(target)
        if not decision.in_scope:
            raise ScopeViolation(
                f"{self.name}: target {target!r} out of scope: {decision.reason}"
            )

    # -- command construction -----------------------------------------------

    @abstractmethod
    def build_command(self, task: Any, config: Any) -> list[str]:
        """Return the argument array to execute (never a shell string)."""

    # -- parse / normalize --------------------------------------------------

    @abstractmethod
    def parse(self, result: CommandResult) -> list[Any]:
        """Convert raw output into canonical, normalized objects.

        Accepts empty/malformed/partial output without raising; unusable lines
        are skipped and logged, not fatal (``13_TESTING_STRATEGY.md``).
        """

    # -- execution ----------------------------------------------------------

    def execute(
        self, task: Any, runner: ToolRunner, config: Any, scope: ScopeGuard
    ) -> ToolExecution:
        """Run the adapter contract against ``task`` via the Tool Runner.

        Order is enforced here; concrete adapters normally only override
        ``validate/build_command/parse``.
        """
        if not self.is_available():
            raise ToolUnavailable(
                f"{self.name}: none of {self.executables or ('?',)} found on PATH; "
                "skipping this discovery source"
            )
        self.validate(task, scope)
        command = self.build_command(task, config)
        result = runner.run_command(command, tool=self.name)
        artifacts = tuple(self.parse(result))
        return ToolExecution(
            tool=self.name,
            command=result.command,
            exit_code=result.exit_code,
            raw_output_ref=result.raw_output_ref,
            artifacts=artifacts,
            timed_out=result.timed_out,
        )


def target_host(task: Any) -> Optional[str]:
    """Extract the normalized host from a task (``task.target``)."""
    return extract_host(getattr(task, "target", ""))