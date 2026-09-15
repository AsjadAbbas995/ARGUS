"""Deterministic Task Planner (``08_ORCHESTRATOR.md`` §task queue/dedup/prioritization).

Phase-5 scope is "deterministic ordering only" — no scoring, no AI. This module produces a
*stable, repeatable* task order: parents before children, higher ``priority`` first, and a
deterministic tie-break, so the same inputs always yield the same plan.

Dedup contract (the anti-infinite-loop rule): a task's **fingerprint** is derived from
task type + target + relevant config + parent/context. A fingerprint that has already
*completed* in this run is never generated again; once the run has seen it, it stays
suppressed. In-flight/failed/pending fingerprints are re-issued (they represent retryable or
in-progress work), which is what makes crash-resume not lose tasks.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import Iterable, Optional
from uuid import UUID

from database.models.entities import Task

_FINISHED = {"completed"}


def task_fingerprint(
    task_type: str,
    target: str,
    config: Optional[dict] = None,
    parent: Optional[Task] = None,
) -> str:
    """Stable dedup key for a task.

    ``config`` is the run's configuration snapshot (or a per-task subset of it) so that two
    tasks scoped by different configs don't collapse into one; ``parent`` gives in-run
    context (a child is distinct from the same work offered as a root). The digest is
    deterministic across processes and machines.
    """
    digest = hashlib.sha256()
    for part in (
        task_type,
        target,
        _stable(config or {}),
        f"parent:{parent.id}" if parent is not None else "",
    ):
        digest.update((part if isinstance(part, str) else repr(part)).encode("utf-8"))
    return digest.hexdigest()


def _stable(value) -> object:
    """Recursively normalize a value so repr() is deterministic (dict key order fixed)."""
    if isinstance(value, dict):
        return {k: _stable(value[k]) for k in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_stable(item) for item in value]
    return value


def order_tasks(tasks: Iterable[Task]) -> list[Task]:
    """Return tasks in deterministic execution order.

    1. Parents always precede their children (topological by ``parent_task_id``).
    2. Higher ``priority`` first.
    3. Stable tie-break: ``(task type, target)`` so the same output every time.
    If the same set is planned twice the order is identical.
    """
    ordered: list[Task] = []
    seen: set[UUID] = set()
    by_id = {t.id: t for t in tasks}

    def visit(task_id: UUID) -> None:
        if task_id in seen:
            return
        seen.add(task_id)
        task = by_id[task_id]
        if task.parent_task_id and task.parent_task_id in by_id:
            visit(task.parent_task_id)
        ordered.append(task)

    for task in sorted(
        tasks,
        key=lambda t: (-_priority(t), t.type, t.target, str(t.id)),
    ):
        visit(task.id)
    return ordered


def _priority(task: Task) -> float:
    try:
        return float(task.priority or 0.0)
    except (TypeError, ValueError):
        return 0.0


def plan_tasks(
    run_id: UUID,
    planned: Iterable[Task],
    existing: Iterable[Task] = (),
    config: Optional[dict] = None,
) -> list[Task]:
    """Fingerprint, dedupe, and order a batch of planned tasks for ``run_id``.

    Tasks whose fingerprint already completed in ``existing`` are dropped (never
    regenerated); the rest are re-fingerprinted, assigned to ``run_id``, and returned in
    deterministic order. Pure function — no I/O — so it is trivially unit-testable.
    """
    parents = {t.id: t for t in existing}
    done = {t.fingerprint for t in existing if t.status in _FINISHED and t.fingerprint}

    candidates: list[Task] = []
    for task in planned:
        fing = task_fingerprint(
            task.type,
            task.target,
            config,
            parents.get(task.parent_task_id),
        )
        if fing in done:
            continue
        candidates.append(
            replace(task, run_id=run_id, fingerprint=fing)
        )
    return order_tasks(candidates)
