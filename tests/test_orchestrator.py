"""Orchestrator Phase-5 tests (``docs/08_ORCHESTRATOR.md`` §run state machine / task dedup /
resumability, and ``docs/15_FIRST_MILESTONE.md`` acceptance §resumability).

These test the **real** ``Orchestrator`` against an in-memory fake that honours the storage
contract, so they exercise the state machine, deterministic planning, crash-resume, and the
"no duplicate / no lost work" guarantee *without* needing PostgreSQL.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

import pytest

from core.orchestrator import Orchestrator, OrchestratorError, Storage
from core.task_planner import order_tasks, task_fingerprint
from database.models.entities import Run, Task, ToolRun


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class FakeStorage(Storage):
    """In-memory storage honoring the orchestrator's contract (tests never touch PostgreSQL)."""

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

    def insert_tasks(self, tasks) -> None:
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

    def insert_tool_run(self, tr: ToolRun) -> None:
        self.tool_runs[tr.id] = replace(tr)


def _run() -> Run:
    return Run(
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
        fingerprint="",
        reason="planned",
        created_at=_now(),
    )


def _tool_run(task: Task) -> ToolRun:
    return ToolRun(
        id=uuid4(),
        task_id=task.id,
        tool_name=task.type,
        command=["argus", task.type, task.target],
        exit_code=0,
        raw_output_ref=f"storage/raw/{task.type}/out.txt",
        started_at=_now(),
        completed_at=_now(),
    )


_orch_default = dict()


@pytest.fixture
def orchestrator():
    storage = FakeStorage()
    orch = Orchestrator(storage=storage, run_tool=_tool_run)
    return orch, storage


# ---------------------------------------------------------------------------
# run lifecycle: creation and terminal-state guard
# ---------------------------------------------------------------------------


def test_create_run_is_created_and_persisted(orchestrator) -> None:
    orch, storage = orchestrator
    run = _run()
    stored = orch.create_run(run)
    assert stored.status == "CREATED"
    assert storage.runs[stored.id].id == stored.id
    assert storage.run_status_calls[-1] == (stored.id, "CREATED")


def test_start_is_transition_then_completion_walk(orchestrator) -> None:
    orch, storage = orchestrator
    run = orch.create_run(_run())
    orch.start(run.id)
    final = orch.run_to_completion(run.id)
    assert final == "COMPLETED"
    assert storage.runs[run.id].status == "COMPLETED"


def test_terminal_run_rejects_further_advance(orchestrator) -> None:
    orch, storage = orchestrator
    run = orch.create_run(_run())
    orch.run_to_completion(run.id)
    status = orch.advance(run.id)
    assert status == "COMPLETED"


# ---------------------------------------------------------------------------
# deterministic planning: ordering + fingerprint dedup ("never regenerate done work")
# ---------------------------------------------------------------------------


def test_plan_is_deterministic_and_stable(order) -> None:
    run_id = uuid4()
    batch = [_task(run_id, "subdomain_enum"), _task(run_id, "dns_resolve", parent=_task(run_id))]
    first = order_tasks(batch)
    second = order_tasks(batch)
    assert [t.id for t in first] == [t.id for t in second]


def test_fingerprint_drops_already_completed_tasks(orchestrator) -> None:
    orch, storage = orchestrator
    run = orch.create_run(_run())
    t1 = _task(run.id)
    t2 = _task(run.id, type_="dns_resolve", target="www.example.com")
    orch.plan(run, [t1, t2])
    # mark both complete so a second plan must not regenerate them
    for task in storage.list_tasks(run.id):
        storage.set_task_status(task.id, "completed")
    planned_again = orch.plan(run, [t1, t2])
    assert planned_again == []


def test_fingerprint_respects_config_scope(orchestrator) -> None:
    orch, storage = orchestrator
    run = orch.create_run(_run())
    fp1 = task_fingerprint("subdomain_enum", "example.com", config={"scope": {"domains": ["example.com"]}})
    fp2 = task_fingerprint("subdomain_enum", "example.com", config={"scope": {"domains": ["example.net"]}})
    assert fp1 != fp2


def test_priority_orders_high_first(order) -> None:
    run_id = uuid4()
    low = _task(run_id, priority=1)
    high = _task(run_id, priority=10)
    ordered = order_tasks([low, high])
    assert ordered[0].id == high.id


# ---------------------------------------------------------------------------
# resumability: crash-mid-run resumes without duplicate or lost work
# ---------------------------------------------------------------------------


def test_resume_after_crash_marks_stale_running_failed_and_reexecutes(orchestrator) -> None:
    orch, storage = orchestrator
    run = orch.create_run(_run())
    # move to EXECUTING and leave a task stuck "running" (the crash checkpoint)
    orch.plan(run, [_task(run.id)])
    run = orch.advance(run.id)
    # simulate crash: a task is still running, not completed
    task = storage.list_tasks_by_status(run.id, "pending")[0]
    storage.set_task_status(task.id, "running")

    status = orch.resume(run.id)
    assert status == "COMPLETED"
    # the in-flight task was re-evaluated, not assumed complete: never duplicated, never lost
    assert len(storage.list_tasks(run.id)) == 1
    assert storage.list_tasks(run.id)[0].status == "completed"


def test_resume_never_duplicates_completed_fingerprint(orchestrator) -> None:
    orch, storage = orchestrator
    run = orch.create_run(_run())
    t = _task(run.id)
    orch.plan(run, [t])
    orch.run_to_completion(run.id)
    # crash + resume should not regenerate the completed task
    plan_after = orch.plan(run, [t])
    assert plan_after == []


def test_resume_completes_run_without_lost_or_duplicate_work(orchestrator) -> None:
    orch, storage = orchestrator
    run = orch.create_run(_run())
    tasks = [_task(run.id, "subdomain_enum"), _task(run.id, "http_probe", parent=_task(run.id))]
    orch.plan(run, tasks)
    # start, crash mid-run (leave run in EXECUTING with one task running)
    orch.advance(run.id)
    pending = storage.list_tasks_by_status(run.id, "pending")
    if pending:
        storage.set_task_status(pending[0].id, "running")
    status = orch.resume(run.id)
    assert status == "COMPLETED"
    stored = storage.list_tasks(run.id)
    assert len(stored) == 2
    assert all(t.status == "completed" for t in stored)
