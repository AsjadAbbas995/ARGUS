"""FastAPI application factory for the ARGUS read/control surface (Phase 10).

Composition contract (``10_IMPLEMENTATION_PLAN.md`` Phase 10): ``create_app`` takes the
committed ``Orchestrator`` (or any double exposing the same seam) and exposes run creation,
run status, task inspection and report retrieval over HTTP. Every handler funnels through an
injected ``orchestrator: Orchestrator``-shaped dependency; no endpoint executes a tool,
adapter or subprocess directly, so endpoint code can never bypass the Scope-Guarded safety
architecture it is handed. Authentication is Bearer-token (constant-time compare) and is
enforced per-request on every route except the liveness probe; liveness is deliberately open
so the health-check gate is not coupled to a secret.
"""

from __future__ import annotations

import secrets
from typing import Any, Mapping, Optional
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from core.orchestrator import Orchestrator
from reports import html_report, json_report, markdown_report

_LIVENESS = "/_healthz"
_BEARER_PREFIX = "bearer "


def _bearer_token(request: Request) -> Optional[str]:
    header = request.headers.get("authorization")
    if not header:
        return None
    value = header.strip()
    if not value.lower().startswith(_BEARER_PREFIX):
        return None
    return value[len(_BEARER_PREFIX):].strip()


def _make_auth_dependency(api_key: str):
    def dependency(request: Request) -> None:
        expected = request.app.state.argus_api_key
        token = _bearer_token(request)
        if not token or not expected or not secrets.compare_digest(token, expected):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="missing or invalid API key",
            )

    return dependency


def _run_payload(run) -> Mapping[str, str]:
    return {
        "id": str(run.id),
        "program_id": str(run.program_id),
        "target": str(run.target),
        "status": str(run.status),
    }


def _task_payload(task) -> Mapping[str, str]:
    return {
        "id": str(task.id),
        "run_id": str(task.run_id),
        "type": str(task.type),
        "target": str(task.target),
        "status": str(task.status),
    }


def create_app(orchestrator: Orchestrator, api_key: str = "") -> FastAPI:
    app = FastAPI(title="ARGUS API", version="0.3.0")
    app.state.argus_api_key = api_key
    app.state.argus_orchestrator = orchestrator
    authed = [Depends(_make_auth_dependency(api_key))]

    @app.get(_LIVENESS, include_in_schema=False)
    def liveness() -> PlainTextResponse:
        return PlainTextResponse("ok")

    @app.post("/api/v1/runs", dependencies=authed, status_code=201)
    def create_run(payload: dict) -> JSONResponse:
        target = str(payload.get("target", "")).strip()
        program_id = str(payload.get("program_id", "")).strip()
        if not target:
            raise HTTPException(status_code=422, detail="target is required")
        run = orchestrator.create_run(program_id=program_id, target=target)
        return JSONResponse(_run_payload(run))

    @app.get("/api/v1/runs/{run_id}", dependencies=authed)
    def get_run(run_id: UUID) -> JSONResponse:
        run = orchestrator.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return JSONResponse(_run_payload(run))

    @app.get("/api/v1/runs/{run_id}/tasks", dependencies=authed)
    def list_tasks(run_id: UUID) -> JSONResponse:
        if orchestrator.get_run(run_id) is None:
            raise HTTPException(status_code=404, detail="run not found")
        tasks = orchestrator.list_tasks(run_id)
        return JSONResponse(
            {"run_id": str(run_id), "count": len(tasks), "tasks": [_task_payload(t) for t in tasks]}
        )

    @app.get("/api/v1/runs/{run_id}/reports/{fmt}", dependencies=authed)
    def get_report(run_id: UUID, fmt: str):
        run = orchestrator.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        tasks = orchestrator.list_tasks(run_id)
        report = json_report.build_report(run=run, tasks=tasks)
        if fmt == "json":
            return PlainTextResponse(json_report.render(report), media_type="application/json")
        if fmt == "markdown":
            return PlainTextResponse(markdown_report.render(report), media_type="text/markdown")
        if fmt == "html":
            return HTMLResponse(html_report.render(report))
        raise HTTPException(status_code=404, detail="unsupported report format")

    return app
