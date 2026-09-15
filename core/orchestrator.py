"""Initial Orchestrator (``08_ORCHESTRATOR.md`` §run state machine / task lifecycle / resumability).

Phase-5 scope: a deterministic run/task lifecycle **without AI**. The orchestrator owns:

* the run state machine (``CREATED → VALIDATING → INITIALIZING → RECONNING → ANALYZING →
  PLANNING → EXECUTING → CORRELATING → PRIORITIZING → WAITING_FOR_NEXT_TASK → COMPLETED``,
  plus ``FAILED``/``CANCELLED``);
* task scheduling: it hands the *planner* the same deterministic inputs and executes the
  returned order, so planning twice yields the same plan;
* **resumability** — on restart it re-evaluates tasks found ``running`` instead of treating
  them as complete, and the run re-enters the state machine at the checkpoint status recorded
  in ``runs.status``. The planner's completed-fingerprint suppression guarantees no duplicate
  work; re-issued in-flight/failed fingerprints guarantee no lost work.

The orchestrator is deliberately decoupled from the database: it takes a *storage* object
exposing ``runs``/``tasks``/``tool_runs`` (the ``Repositories`` facade implements it; tests
inject an in-memory fake), and a ``ToolRunner``-like ``run_tool`` callable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional
from uuid import UUID

from core.task_planner import order_tasks, plan_tasks
from database.models.entities import Run, Task, ToolRun

# Run-level state machine, in legal forward order (08_ORCHESTRATOR.md).
_RUN_STEPS = [
    "CREATED",
    "VALIDATING",
    "INITIALIZING",
    "RECONNING",
    "ANALYZING",
    "PLANNING",
    "EXECUTING",
    "CORRELATING",
    "PRIORITIZING",
    "WAITING_FOR_NEXT_TASK",
]
_RUN_TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}
_TASK_RUNNABLE = {"pending"}

# Toolless "analysis" task types are marked completed directly; the runner is only invoked for
# tasks whose type maps to an external tool (in Phase 5 this is driven explicitly).
TOOL_TASK_TYPES = {
    "subdomain_enum",
    "dns_resolve",
    "http_probe",
    "port_scan",
    "web_crawl",
    "tech_detect",
    "dictionary_bruteforce",
}


class OrchestratorError(Exception):
    """Base error for orchestration failures."""


class RunNotFoundError(OrchestratorError):
    """No such run in storage."""


class BadRunTransition(OrchestratorError):
    """A run tried to leave its legal state machine / terminal state."""


class Storage:
    """Minimal storage contract the orchestrator depends on (implemented by Repositories)."""

    def __init__(self) -> None:
        raise NotImplementedError

    def create_run(self, run: Run) -> Run: ...
    def get_run(self, run_id: UUID) -> Optional[Run]: ...
    def set_run_status(self, run_id: UUID, status: str) -> None: ...

    def insert_tasks(self, tasks: Iterable[Task]) -> None: ...
    def list_tasks(self, run_id: UUID) -> list[Task]: ...
    def list_tasks_by_status(self, run_id: UUID, status: str) -> list[Task]: ...
    def set_task_status(self, task_id: UUID, status: str) -> None: ...

    def insert_tool_run(self, tr: ToolRun) -> ToolRun: ...
    def finalize_tool_run(
        self, tool_run_id: UUID, exit_code: int, raw_output_ref: Optional[str]
    ) -> None: ...


@dataclass
class Orchestrator:
    storage: Storage
    run_tool: Callable[[Task], ToolRun]  # (task) -> ToolRun; Phase-5 deterministic demos

    # -- run lifecycle ------------------------------------------------------

    def create_run(self, run: Run, planned: Iterable[Task] = ()) -> Run:
        """Persist a new run (CREATED) and, if given, seed its first planned tasks."""
        stored = self.storage.create_run(run)
        self.storage.set_run_status(stored.id, "CREATED")
        if planned:
            self.plan(stored, planned)
        return stored

    def start(self, run_id: UUID) -> None:
        """Begin the run: the first deterministic state transition (CREATED → VALIDATING)."""
        self._advance_step(run_id)

    # -- planning / scheduling ----------------------------------------------

    def plan(self, run: Run, planned: Iterable[Task]) -> list[Task]:
        """Fingerprint/dedupe/order ``planned`` for ``run`` and persist them (if not already done).

        Returns the ordered task list. Tasks whose fingerprint already completed are dropped by
        the planner (``plan_tasks``); the orchestrator just persists whatever the planner emits.
        """
        existing = self.storage.list_tasks(run.id)
        ordered = plan_tasks(
            run.id,
            planned,
            existing,
            config=run.configuration_snapshot or {},
        )
        self.storage.insert_tasks(ordered)
        return ordered

    # -- deterministic walk ------------------------------------------------

    def _advance_step(self, run_id: UUID) -> str:
        run = self._require_run(run_id)
        if run.status in _RUN_TERMINAL:
            raise BadRunTransition(f"run {run_id} is terminal ({run.status})")
        if run.status == "WAITING_FOR_NEXT_TASK":
            self.storage.set_run_status(run_id, "COMPLETED")
            return "COMPLETED"
        idx = _RUN_STEPS.index(run.status) if run.status in _RUN_STEPS else -1
        next_step = _RUN_STEPS[idx + 1] if idx >= 0 and idx + 1 < len(_RUN_STEPS) else None
        if next_step is None:
            raise BadRunTransition(f"no step after {run.status}")
        self.storage.set_run_status(run_id, next_step)
        return next_step

    def advance(self, run_id: UUID, tool: Optional[str] = None) -> str:
        """Advance the run one deterministic step.

        At ``EXECUTING`` this runs the next pending tool task (when one exists and ``tool`` is
        supplied); otherwise it only transitions the run state, so state-machine transitions are
        observable and testable without executing any tool.
        """
        run = self._require_run(run_id)
        if run.status in _RUN_TERMINAL:
            return run.status
        if run.status == "EXECUTING":
            self._execute_pending(run, tool)
            return self._require_run(run_id)
        self._advance_step(run_id)
        return self._require_run(run_id)

    def run_to_completion(self, run_id: UUID, tool: Optional[str] = None) -> str:
        """Walk the whole state machine to COMPLETED, executing tasks at the EXECUTING step."""
        while True:
            run = self._require_run(run_id)
            if run.status in _RUN_TERMINAL:
                return run.status
            if run.status == "EXECUTING":
                if self._execute_pending(run, tool):
                    continue
                if not self._has_pending(run):
                    self._advance_step(run_id)
                continue
            self._advance_step(run_id)

    # -- resumability -------------------------------------------------------

    def resume(self, run_id: UUID) -> str:
        """Re-enter a run after a crash/interruption without losing or duplicating work.

        Tasks still ``running`` from an in-flight crash are **re-evaluated as failed** (never
        blindly assumed complete); the run returns to ``EXECUTING``/``CORRELATING`` so the next
        deterministic pass retries them. Completed fingerprints stay suppressed, so no task is
        regenerated; everything else is re-issued, so nothing is lost.
        """
        for task in self.storage.list_tasks_by_status(run_id, "running"):
            self.storage.set_task_status(task.id, "failed")
            self.storage.set_task_status(task.id, "pending")
            self.storage.set_task_status(task.id, "pending")
        run = self._require_run(run_id)
        if run.status in _RUN_TERMINAL:
            return run.status
        self.storage.set_run_status(run_id, "EXECUTING")
        return self.run_to_completion(run_id)

    # -- internals ----------------------------------------------------------

    def _require_run(self, run_id: UUID) -> Run:
        run = self.storage.get_run(run_id)
        if run is None:
            raise RunNotFoundError(f"unknown run {run_id}")
        return run

    def _has_pending(self, run: Run) -> bool:
        return any(t.status in _TASK_RUNNABLE for t in self.storage.list_tasks(run.id))

    def _execute_pending(self, run: Run, tool: Optional[str]) -> bool:
        pending = [t for t in self.storage.list_tasks(run.id) if t.status in _TASK_RUNNABLE]
        if not pending:
            return False
        ordered = order_tasks(pending)
        for task in ordered:
            self.storage.set_task_status(task.id, "running")
            tr = self.run_tool(task)
            self.storage.insert_tool_run(tr)
            self.storage.set_task_status(task.id, "completed")
        return True
