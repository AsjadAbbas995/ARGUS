"""Phase-8 adaptive-loop tests -- the orchestrator's deterministic "analysis pass" turns the
Phase-5 linear walk into the discovery -> hypothesis -> new-task cycle without manual
intervention (01_PRODUCT_SPEC.md section 10; 08_ORCHESTRATOR.md "adaptive loop";
10_IMPLEMENTATION_PLAN.md Phase 8 DoD: "a lab run demonstrates at least one full discovery ->
hypothesis -> new task cycle without manual intervention, and task deduplication is verified
under repeated re-analysis").

These test the REAL Orchestrator with the Phase-8 "analysis" hook set, against the same
in-memory fake storage the Phase-5 suite uses, so they exercise the fingerprint-deduplicated
adaptive loop -- and its safety limit -- without touching PostgreSQL:

* a full discovery -> hypothesis -> new-task cycle completes with no manual step in between;
* re-analysis that would regenerate already-fingerprinted work is deduplicated (the loop
  terminates the moment a pass adds nothing new, so no duplicate fingerprints are ever stored);
* when a pathological analysis hook keeps proposing brand-new fingerprints, the run stops
  advancing further scheduled tasks at the safety limit (max_loop_passes) in a CANCELLED
  terminal state, with all already-planned Phase-5 work preserved; and
* the passes are deterministic across repeated runs on identical evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Callable, Iterable, Optional
from uuid import UUID, uuid4

import pytest

from core.orchestrator import Orchestrator, OrchestratorError, Storage
from core.task_planner import order_tasks, task_fingerprint
from database.models.entities import Run, Task, ToolRun


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class FakeStorage(Storage):
    """In-memory storage honouring the orchestrator's contract (tests never touch PostgreSQL)."""

    runs: dict[UUID, Run] = field(default_factory=dict)
    tasks: dict[UUID, Task] = field(default_factory=dict)
    tool_runs: dict[UUID, ToolRun] = field(default_factory=dict)
    run_status_calls: list[tuple[UUID, str]] = field(default_factory=list)
    task_status_calls: list[tuple[UUID, str]] = field(default_factory=list)

    # -- runs ---------------------------------------------------------------

    def create_run(self, run: Run) -> Run:
        self.runs[run.id] = replace(run)
        return self.runs[run.id]

    def get_run(self, run_id: UUID) -> Optional[Run]:
        return self.runs.get(run_id)

    def set_run_status(self, run_id: UUID, status: str) -> None:
        if run_id in self.runs:
            self.runs[run_id] = replace(self.runs[run_id], status=status)
        self.run_status_calls.append((run_id, status))

    # -- tasks --------------------------------------------------------------

    def insert_tasks(self, tasks: Iterable[Task]) -> None:
        for task in tasks:
            self.tasks[task.id] = replace(task)

    def list_tasks(self, run_id: UUID) -> list[Task]:
        return [t for t in self.tasks.values() if t.run_id == run_id]

    def list_tasks_by_status(self, run_id: UUID, status: str) -> list[Task]:
        return [t for t in self.list_tasks(run_id) if t.status == status]

    def set_task_status(self, task_id: UUID, status: str) -> None:
        if task_id in self.tasks:
            self.tasks[task_id] = replace(self.tasks[task_id], status=status)
        self.task_status_calls.append((task_id, status))

    # -- tool runs ----------------------------------------------------------

    def insert_tool_run(self, tr: ToolRun) -> ToolRun:
        self.tool_runs[tr.id] = replace(tr)
        return self.tool_runs[tr.id]

    def finalize_tool_run(
        self, tool_run_id: UUID, exit_code: int, raw_output_ref: Optional[str]
    ) -> None:
        if tool_run_id in self.tool_runs:
            tr = self.tool_runs[tool_run_id]
            self.tool_runs[tool_run_id] = replace(tr, exit_code=exit_code)


def _run() -> Run:
    return Run(
        id=uuid4(),
        program_id=uuid4(),
        status="CREATED",
        target="example.com",
        configuration_snapshot={"scope": {"domains": ["example.com"]}},
    )


def _task(run_id: UUID, type_: str = "subdomain_enum", target: str = "example.com",
          parent: Optional[Task] = None, priority: float = 0) -> Task:
    return Task(
        id=uuid4(),
        run_id=run_id,
        type=type_,
        target=target,
        parent_task_id=parent.id if parent else None,
        priority=priority,
        status="pending",
        fingerprint=task_fingerprint(type_, target),
        reason="planned",
    )


def _tool_run(task: Task) -> ToolRun:
    return ToolRun(
        id=uuid4(),
        task_id=task.id,
        tool_name=task.type,
        command=["argus", task.type, task.target],
        exit_code=0,
        raw_output_ref=f"storage/raw/{task.type}/out.txt",
    )


@pytest.fixture
def orchestrator() -> tuple[Orchestrator, FakeStorage]:
    storage = FakeStorage()
    orch = Orchestrator(storage=storage, run_tool=_tool_run)
    return orch, storage


# ---------------------------------------------------------------------------
# adaptive loop: the analysis hook closes the discovery -> hypothesis -> task cycle
# ---------------------------------------------------------------------------


def test_analysis_hook_drives_full_discovery_to_new_task_cycle(orchestrator) -> None:
    """Running with an ``analysis`` hook completes a cycle with zero manual steps.

    The hook proposes one new fingerprint on its first analysis pass and nothing afterwards;
    the orchestrator must fold that into a real task, execute it, and finish COMPLETED.
    """
    orch, storage = orchestrator

    def analysis(run: Run, current: list[Task]) -> list[Task]:
        # First pass: hypothesise a dependent task only if it is not already planned.
        if any(t.target.startswith("www.") for t in current):
            return []
        return [_task(run.id, "dns_resolve", target="www.example.com",
                      parent=current[0] if current else None)]

    orch.analysis = analysis
    run = orch.create_run(_run())
    orch.plan(run, [_task(run.id)])
    status = orch.run_to_completion(run.id)
    assert status == "COMPLETED"
    stored = storage.list_tasks(run.id)
    assert {t.type for t in stored} == {"subdomain_enum", "dns_resolve"}
    assert all(t.status == "completed" for t in stored)
    # the loop ran at least one full cycle: the hypothesis task is real and executed
    assert len(storage.tool_runs) == 2


def test_reanalysis_that_adds_nothing_is_deduplicated_and_terminates(orchestrator) -> None:
    """A converging analysis hook re-proposes only already-fingerprinted work.

    ``plan`` deduplicates by fingerprint, so re-analysis adds nothing new and the loop must
    terminate in COMPLETED without ever storing a duplicate fingerprint.
    """
    orch, storage = orchestrator
    proposals: list[Task] = []

    def analysis(run: Run, current: list[Task]) -> list[Task]:
        if not proposals:
            proposals.append(_task(run.id, "dns_resolve", target="www.example.com"))
            return proposals[:]
        # Re-analysis sees the same hypothesis again -> fingerprint already present -> nothing new.
        return proposals[:]

    orch.analysis = analysis
    run = orch.create_run(_run())
    orch.plan(run, [_task(run.id)])
    status = orch.run_to_completion(run.id)
    assert status == "COMPLETED"
    tasks = storage.list_tasks(run.id)
    fingerprints = [t.fingerprint for t in tasks]
    assert len(tasks) == len(set(fingerprints))  # never a duplicate fingerprint on disk


def test_unstable_analysis_hits_safety_limit_and_cancels_without_losing_planned_work(
    orchestrator,
) -> None:
    """A pathological hook that always proposes a *new* fingerprint must not loop forever.

    Each re-analysis re-proposes a fresh hypothesis (the target embeds the current plan size,
    so the fingerprint genuinely changes on every pass and can never be deduplicated into a
    completed run). The orchestrator must trip its safety limit and end the run CANCELLED,
    preserving the Phase-5 tasks already planned before the instability (no planned work lost).
    """
    orch, storage = orchestrator

    def analysis(run: Run, current: list[Task]) -> list[Task]:
        return [_task(run.id, "reprobe", target=f"fragment-{len(current)}.example.com")]

    orch.analysis = analysis
    orch.max_loop_passes = 4
    run = orch.create_run(_run())
    orch.plan(run, [_task(run.id)])
    status = orch.run_to_completion(run.id)
    assert status == "CANCELLED"
    planned = storage.list_tasks(run.id)
    assert len(planned) >= 1  # the original Phase-5 seed survived the safety limit
    assert planned[0].type == "subdomain_enum"
    assert all(t.status in ("completed", "pending") for t in planned)


def test_adaptive_loop_is_deterministic_across_repeated_runs(orchestrator) -> None:
    """Identical evidence + identical hooks must plan an identical fingerprint set.

    The probe is parentless, so each fingerprint depends only on task type + target; two
    identical runs with the same analysis hook must therefore plan byte-identical fingerprint
    sets, pinning the determinism guarantee of the Phase-8 adaptive loop.
    """
    results: list[list[str]] = []
    for _ in range(2):
        orch, storage = orchestrator

        def analysis(run: Run, current: list[Task]) -> list[Task]:
            if any(t.type == "dns_resolve" for t in current):
                return []
            return [_task(run.id, "dns_resolve", target="www.example.com")]

        orch.analysis = analysis
        run = orch.create_run(_run())
        orch.plan(run, [_task(run.id)])
        orch.run_to_completion(run.id)
        results.append(sorted(t.fingerprint for t in storage.list_tasks(run.id)))
    assert results[0] == results[1]


