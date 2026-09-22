"""Phase-10 route seam (``10_IMPLEMENTATION_PLAN.md``).

These handlers are pure projections over an injected ``orchestrator`` double exposing the
``create_run`` / ``get_run`` / ``list_tasks`` seam. They never import a tool, adapter or
subprocess, and they never execute anything themselves: they are the exact surface the
FastAPI layer (``api.server.create_app``) is wired to, so the "no endpoint may bypass the
safety architecture" guarantee is inherited, not reimplemented, by the HTTP layer.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional
from uuid import UUID

from core.orchestrator import Orchestrator


def run_payload(run) -> Mapping[str, str]:
    return {
        "id": str(run.id),
        "program_id": str(run.program_id),
        "target": str(run.target),
        "status": str(run.status),
    }


def task_payload(task) -> Mapping[str, str]:
    return {
        "id": str(task.id),
        "run_id": str(task.run_id),
        "type": str(task.type),
        "target": str(task.target),
        "status": str(task.status),
    }


def create_run_handler(orchestrator: Orchestrator, target: str, program_id: str = "") -> Mapping[str, str]:
    run = orchestrator.create_run(program_id=program_id, target=target)
    return run_payload(run)


def get_run_handler(orchestrator: Orchestrator, run_id: UUID) -> Optional[Mapping[str, str]]:
    run = orchestrator.get_run(run_id)
    if run is None:
        return None
    return run_payload(run)


def list_tasks_handler(orchestrator: Orchestrator, run_id: UUID) -> Mapping[str, Any]:
    tasks = orchestrator.list_tasks(run_id)
    return {
        "run_id": str(run_id),
        "count": len(tasks),
        "tasks": [task_payload(t) for t in tasks],
    }
