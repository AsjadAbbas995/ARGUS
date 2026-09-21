"""Reproducible JSON run summary (``15_FIRST_MILESTONE.md`` acceptance "valid, reproducible JSON").

Mirrors the report structure from ``09_OUTPUTS.md`` but stays **pure** — it is a pure function
from (run, tasks, tool_runs) rows to a JSON-serialisable dict, and ``render`` serialises with
``sort_keys=True`` plus a deterministic ``default=str`` for UUIDs/datetimes. Because key order,
indentation, and value coercion are all fixed, the same inputs always produce byte-identical,
machine-valid JSON. No randomness, no wall-clock, no module-level state.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Iterable, Mapping, Optional
from uuid import UUID

from database.models.entities import ToolRun, Task, Run

_RUN_SECTION = "run"
_TASKS_SECTION = "tasks"
_TOOL_RUNS_SECTION = "tool_runs"
_DEDUP_SECTION = "dedup"


def _row_rank(status: str) -> int:
    return {
        "completed": 0,
        "skipped": 1,
        "cancelled": 2,
        "failed": 3,
        "running": 4,
        "pending": 5,
    }.get(status, 6)


def _task_key(task: Task) -> tuple[Any, ...]:
    return (_row_rank(task.status), task.type, task.target, str(task.id))


def _tool_run_key(tr: ToolRun) -> tuple[Any, ...]:
    return (tr.tool_name, str(tr.id))


def build_json_summary(
    run: Run,
    tasks: Iterable[Task] = (),
    tool_runs: Iterable[ToolRun] = (),
    evidence_count: int = 0,
    asset_counts: Optional[Mapping[str, int]] = None,
) -> dict[str, Any]:
    """Build the summary dict for ``run``.

    Deterministic by construction: tasks/tool runs are sorted by a stable key before being
    serialised, so the shape is independent of repository/insertion order. Keys are fixed
    (``09_OUTPUTS.md`` structure), and nests are plain JSON values.
    """
    task_list = sorted(tasks, key=_task_key)
    tr_list = sorted(tool_runs, key=_tool_run_key)

    by_status: dict[str, int] = {}
    for task in task_list:
        by_status[task.status] = by_status.get(task.status, 0) + 1

    return {
        "schema_version": "1.0",
        "generator": "argus-json-summary",
        _RUN_SECTION: {
            "id": str(run.id),
            "program_id": str(run.program_id),
            "status": run.status,
            "target": run.target,
            "started_at": _iso(run.started_at),
            "completed_at": _iso(run.completed_at),
            "configuration_snapshot": run.configuration_snapshot or {},
        },
        "assets": {k: int(v) for k, v in sorted((asset_counts or {}).items())},
        _TASKS_SECTION: {
            "total": len(task_list),
            "by_status": by_status,
            "items": [_task_summary(t) for t in task_list],
        },
        _TOOL_RUNS_SECTION: {
            "total": len(tr_list),
            "by_tool": _by_tool(tr_list),
            "items": [_tool_run_summary(tr) for tr in tr_list],
        },
        "evidence_count": int(evidence_count),
        _DEDUP_SECTION: {"suppressed_completed_fingerprints": _suppressed_count(task_list)},
    }


def _task_summary(task: Task) -> dict[str, Any]:
    return {
        "id": str(task.id),
        "type": task.type,
        "target": task.target,
        "parent_task_id": str(task.parent_task_id) if task.parent_task_id else None,
        "priority": task.priority,
        "status": task.status,
        "reason": task.reason,
        "started_at": _iso(task.started_at),
        "completed_at": _iso(task.completed_at),
    }


def _tool_run_summary(tr: ToolRun) -> dict[str, Any]:
    return {
        "id": str(tr.id),
        "task_id": str(tr.task_id),
        "tool_name": tr.tool_name,
        "command": list(tr.command),
        "exit_code": tr.exit_code,
        "raw_output_ref": tr.raw_output_ref,
        "started_at": _iso(tr.started_at),
        "completed_at": _iso(tr.completed_at),
    }


def _by_tool(trs: Iterable[ToolRun]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for tr in trs:
        counts[tr.tool_name] = counts.get(tr.tool_name, 0) + 1
    return {k: counts[k] for k in sorted(counts)}


def _suppressed_count(task_list: Iterable[Task]) -> int:
    return sum(1 for t in task_list if t.status == "completed" and not t.reason)


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def render(summary: Mapping[str, Any]) -> str:
    """Serialise a summary dict to a single, reproducible JSON document."""
    return json.dumps(summary, indent=2, sort_keys=True, default=_json_default)


def _json_default(value: Any) -> Any:
    if isinstance(value, (UUID, datetime)):
        return str(value)
    raise TypeError(f"not JSON-serialisable: {type(value).__name__}")
