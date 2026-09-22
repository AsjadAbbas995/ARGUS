"""Phase-10 route projection handlers (``10_IMPLEMENTATION_PLAN.md``).

These handlers are the pure, tool-free control surface delegated to by the FastAPI layer:
they take only the injected orchestrator-shaped double and the committed report seam
(``build_report`` + deterministic renderers). They never import or invoke a tool, adapter or
subprocess, so the Scope-Guarded safety architecture is inherited, not reimplemented, by the
HTTP layer.
"""

from __future__ import annotations

from typing import Mapping, Optional
from uuid import UUID

from reports import json_report


def _task_payload(task) -> Mapping[str, str]:
    return {
        "id": str(task.id),
        "run_id": str(task.run_id),
        "type": str(task.type),
        "target": str(task.target),
        "status": str(task.status),
    }


def create_run_handler(orchestrator, payload: Mapping) -> Mapping[str, str]:
    target = str(payload.get("target", "")).strip()
    program_id = str(payload.get("program_id", "")).strip()
    run = orchestrator.create_run(program_id=program_id, target=target)
    return {
        "id": str(run.id),
        "program_id": str(run.program_id),
        "target": str(run.target),
        "status": str(run.status),
    }


def run_status_handler(orchestrator, run_id: UUID) -> Optional[Mapping[str, str]]:
    run = orchestrator.get_run(run_id)
    if run is None:
        return None
    return {
        "id": str(run.id),
        "program_id": str(run.program_id),
        "target": str(run.target),
        "status": str(run.status),
    }


def list_tasks_handler(orchestrator, run_id: UUID) -> Mapping[str, object]:
    run = orchestrator.get_run(run_id)
    if run is None:
        return {"run_id": str(run_id), "count": 0, "tasks": []}
    tasks = orchestrator.list_tasks(run_id)
    return {
        "run_id": str(run_id),
        "count": len(tasks),
        "tasks": [_task_payload(t) for t in tasks],
    }
