"""Initial Orchestrator (``08_ORCHESTRATOR.md`` ??run state machine / task lifecycle / resumability).
    # ---- Phase 11 additive seam: operator hypothesis review ledger --------------
    # Ships per-run, per-hypothesis human review on top of the existing run state.
    # Deliberately exposes per-step approve/reject only -- the dashboard contract
    # forbids any "approve all" / bulk control, and none exists here or upstream.

    def list_runs(self) -> list:
        return list(self._runs.values())

    def list_hypotheses(self, run_id) -> list:
        return [dict(h) for h in self._hypothesis_ledger().get(str(run_id), [])]

    def _hypothesis_ledger(self) -> dict:
        if getattr(self, "_seam_hypothesis_ledger", None) is None:
            self._seam_hypothesis_ledger = {}
        return self._seam_hypothesis_ledger

    def _record_hypothesis(self, run_id, hypothesis_id, statement, truth_label,
                           confidence, priority, severity, target, step) -> dict:
        rec = {
            "id": hypothesis_id,
            "run_id": run_id,
            "statement": statement,
            "truth_label": truth_label,
            "confidence": confidence,
            "priority": priority,
            "severity": severity,
            "target": target,
            "validation_step": step,
            "status": "pending",
            "reason": "",
        }
        self._hypothesis_ledger().setdefault(str(run_id), []).append(rec)
        return dict(rec)

    def approve_hypothesis(self, run_id, hypothesis_id) -> dict:
        for h in self._hypothesis_ledger().get(str(run_id), []):
            if str(h["id"]) == str(hypothesis_id):
                h["status"] = "approved"
                return dict(h)
        return None

    def reject_hypothesis(self, run_id, hypothesis_id, reason="") -> dict:
        for h in self._hypothesis_ledger().get(str(run_id), []):
            if str(h["id"]) == str(hypothesis_id):
                h["status"] = "rejected"
                h["reason"] = str(reason or "operator rejected")
                return dict(h)
        return None

Phase-5 scope: a deterministic run/task lifecycle **without AI**. The orchestrator owns:

* the run state machine (``CREATED ??? VALIDATING ??? INITIALIZING ??? RECONNING ??? ANALYZING ???
  PLANNING ??? EXECUTING ??? CORRELATING ??? PRIORITIZING ??? WAITING_FOR_NEXT_TASK ??? COMPLETED``,
  plus ``FAILED``/``CANCELLED``);
* task scheduling: it hands the *planner* the same deterministic inputs and executes the
  returned order, so planning twice yields the same plan;
* **resumability** ??? on restart it re-evaluates tasks found ``running`` instead of treating
  them as complete, and the run re-enters the state machine at the checkpoint status recorded
  in ``runs.status``. The planner's completed-fingerprint suppression guarantees no duplicate
  work; re-issued in-flight/failed fingerprints guarantee no lost work.

The orchestrator is deliberately decoupled from the database: it takes a *storage* object
exposing ``runs``/``tasks``/``tool_runs`` (the ``Repositories`` facade implements it; tests
inject an in-memory fake), and a ``ToolRunner``-like ``run_tool`` callable.

Phase-8 scope ("10_IMPLEMENTATION_PLAN.md" ??Phase 8 ??? Adaptive Recon Loop): an optional
``analysis`` hook turns the walk into the adaptive loop from ``08_ORCHESTRATOR.md`` / "03_RECON_PIPELINE.md"
??27 ??? at every ``ANALYZING`` step the hook proposes new tasks, the planner fingerprint-dedupes
them, and ``WAITING_FOR_NEXT_TASK`` re-enters ``RECONNING`` while passes keep generating new
work, reaching ``COMPLETED`` only when re-analysis adds nothing. Task-level fingerprinting
prevents infinite loops (08_ORCHESTRATOR.md ??Task Deduplication) and ``max_loop_passes`` is the
graceful instability/safety limit. Without a hook the phase-5 linear walk is unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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

# A Phase-8 adaptive-loop analysis hook: given the run and its current task list, it proposes
# new reconnaissance tasks (the planner re-fingerprints and dedupes them). ``None`` disables
# the loop entirely, preserving Phase-5 behaviour.
AnalysisHook = Callable[["Run", list["Task"]], list["Task"]]


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
    analysis: Optional[AnalysisHook] = None  # Phase-8 adaptive loop; None keeps Phase-5 behaviour
    max_loop_passes: int = 32  # instability/safety limit (01_PRODUCT_SPEC.md ??10)
    _loop_pass: int = field(default=0, init=False, repr=False, compare=False)
    _pass_new_tasks: bool = field(default=False, init=False, repr=False, compare=False)

    # -- run lifecycle ------------------------------------------------------

    def create_run(self, run: Run, planned: Iterable[Task] = ()) -> Run:
        """Persist a new run (CREATED) and, if given, seed its first planned tasks."""
        self._loop_pass = 0
        self._pass_new_tasks = False
        stored = self.storage.create_run(run)
        self.storage.set_run_status(stored.id, "CREATED")
        if planned:
            self.plan(stored, planned)
        return stored

    def start(self, run_id: UUID) -> None:
        """Begin the run: the first deterministic state transition (CREATED ??? VALIDATING)."""
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
        if run.status == "ANALYZING" and self.analysis is not None:
            self._run_analysis_pass(run_id)
        if run.status == "WAITING_FOR_NEXT_TASK":
            return self._next_pass(run_id)
        idx = _RUN_STEPS.index(run.status) if run.status in _RUN_STEPS else -1
        next_step = _RUN_STEPS[idx + 1] if idx >= 0 and idx + 1 < len(_RUN_STEPS) else None
        if next_step is None:
            raise BadRunTransition(f"no step after {run.status}")
        self.storage.set_run_status(run_id, next_step)
        return next_step

    def _run_analysis_pass(self, run_id: UUID) -> bool:
        """Run the analysis hook and enqueue its proposed (fingerprint-deduped) tasks.

        Returns whether the pass generated any *new* (never-seen-in-this-run) fingerprint ??? the
        adaptive-loop progress signal ("COMPLETED only when re-analysis adds nothing new",
        08_ORCHESTRATOR.md). ``plan`` deliberately re-issues pending/in-flight/failed
        fingerprints ("no lost work", Phase 5), so the signal is the set of fingerprints the
        pass introduced that were not present in *any* status before it.
        """
        self._loop_pass += 1
        run = self._require_run(run_id)
        before = {t.fingerprint for t in self.storage.list_tasks(run.id) if t.fingerprint}
        proposed = self.analysis(run, self.storage.list_tasks(run.id))
        self.plan(run, proposed)
        after = {t.fingerprint for t in self.storage.list_tasks(run.id) if t.fingerprint}
        self._pass_new_tasks = bool(after - before)
        return self._pass_new_tasks

    def _next_pass(self, run_id: UUID) -> str:
        """Adaptive-loop stop decision at ``WAITING_FOR_NEXT_TASK`` (08_ORCHESTRATOR.md).

        Re-enter ``RECONNING`` while a pass generated new (non-duplicate) tasks; reach
        ``COMPLETED`` once re-analysis produces nothing new. ``max_loop_passes`` is the
        instability/safety limit ??? exceeding it ends the run gracefully as ``CANCELLED``
        (01_PRODUCT_SPEC.md ??10). Without an ``analysis`` hook the run always completes,
        preserving Phase-5 behaviour.
        """
        if self.analysis is not None and self._pass_new_tasks:
            if self._loop_pass >= self.max_loop_passes:
                self.storage.set_run_status(run_id, "CANCELLED")
                return "CANCELLED"
            self.storage.set_run_status(run_id, "RECONNING")
            return "RECONNING"
        self.storage.set_run_status(run_id, "COMPLETED")
        return "COMPLETED"

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
