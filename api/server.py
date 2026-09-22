"""FastAPI application factory for the ARGUS read/control surface (Phase 10).

Composition contract (``10_IMPLEMENTATION_PLAN.md`` Phase 10): the app receives the
committed ``Orchestrator`` (or an injected double exposing the same read seam:
``create_run`` / ``get_run`` / ``list_tasks``) and exposes run creation, run status, task
inspection and report retrieval over HTTP. Every handler funnels through the injected
orchestrator; there is no route that executes a tool, adapter or subprocess directly, so the
Phase-10 objective "no endpoint may bypass the safety architecture" holds by construction.
The liveness probe is deliberately unauthenticated; every other route requires a Bearer API
key compared in constant time against ``app.state.argus_api_key``.
"""

from __future__ import annotations

from typing import Mapping, Optional
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path as _ArgusRoot

from core.orchestrator import Orchestrator
from reports import html_report, json_report, markdown_report

_LIVENESS = "/_healthz"
_BEARER_PREFIX = "bearer "
_API_KEY = "phase-10"


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



def _hypothesis_payload(h) -> Mapping[str, object]:
    return {
        "id": str(h.get("id")),
        "run_id": str(h.get("run_id")),
        "statement": str(h.get("statement")),
        "truth_label": str(h.get("truth_label")),
        "confidence": float(h.get("confidence", 0.0)),
        "priority": str(h.get("priority", "")),
        "severity": str(h.get("severity", "")),
        "target": str(h.get("target", "")),
        "validation_step": str(h.get("validation_step", "")),
        "status": str(h.get("status", "pending")),
        "reason": str(h.get("reason", "")),
    }

def _hypothesis_payload(h) -> dict:
    return {
        "id": str(h["id"]),
        "run_id": str(h["run_id"]),
        "statement": str(h["statement"]),
        "truth_label": str(h["truth_label"]),
        "confidence": float(h.get("confidence", 0.0)),
        "target": str(h.get("target", "")),
        "status": str(h.get("status", "pending")),
        "priority": str(h.get("priority", "")),
        "validation_step": str(h.get("validation_step", "")),
    }


def _hypotheses_payload(run_id, hyps) -> dict:
    return {
        "count": len(hyps),
        "run_id": str(run_id),
        "hypotheses": [_hypothesis_payload(h) for h in hyps],
    }
def create_app(orchestrator: Orchestrator, api_key: str = _API_KEY) -> FastAPI:
    app = FastAPI(title="ARGUS API", version="0.3.0")
    app.state.argus_api_key = api_key

    import secrets

    def _authed(request: Request) -> None:
        header = request.headers.get("authorization")
        if not header or not header.lower().startswith(_BEARER_PREFIX):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing API key")
        token = header[len(_BEARER_PREFIX):].strip()
        expected = app.state.argus_api_key
        if not expected or not secrets.compare_digest(str(token), str(expected)):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API key")

    @app.get(_LIVENESS, include_in_schema=False)
    def liveness() -> PlainTextResponse:
        return PlainTextResponse("ok")

    @app.post("/api/v1/runs", dependencies=[Depends(_authed)], status_code=status.HTTP_201_CREATED)
    def create_run(payload: dict) -> JSONResponse:
        target = str(payload.get("target", "")).strip()
        program_id = str(payload.get("program_id", "")).strip()
        if not target:
            raise HTTPException(status_code=422, detail="target is required")
        run = orchestrator.create_run(program_id=program_id, target=target)
        return JSONResponse(_run_payload(run), status_code=status.HTTP_201_CREATED)

    @app.get("/api/v1/runs/{run_id}", dependencies=[Depends(_authed)])
    def get_run(run_id: UUID) -> JSONResponse:
        run = orchestrator.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return JSONResponse(_run_payload(run))

    @app.get("/api/v1/runs/{run_id}/tasks", dependencies=[Depends(_authed)])
    def list_tasks(run_id: UUID) -> JSONResponse:
        if orchestrator.get_run(run_id) is None:
            raise HTTPException(status_code=404, detail="run not found")
        tasks = orchestrator.list_tasks(run_id)
        return JSONResponse({"run_id": str(run_id), "count": len(tasks), "tasks": [_task_payload(t) for t in tasks]})

    @app.get("/api/v1/runs/{run_id}/reports/{fmt}", dependencies=[Depends(_authed)])
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


    @app.get("/api/v1/runs", dependencies=[Depends(_authed)])
    def list_runs() -> JSONResponse:
        runs = orchestrator.list_runs()
        return JSONResponse({"count": len(runs), "runs": [_run_payload(r) for r in runs]})

    @app.get("/api/v1/runs/{run_id}/hypotheses", dependencies=[Depends(_authed)])
    def list_hypotheses(run_id: UUID) -> JSONResponse:
        run = orchestrator.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        hs = orchestrator.list_hypotheses(run_id)
        return JSONResponse({"run_id": str(run_id), "count": len(hs), "hypotheses": [_hypothesis_payload(h) for h in hs]})

    @app.post("/api/v1/runs/{run_id}/hypotheses/{hypothesis_id}/approve", dependencies=[Depends(_authed)])
    def approve_hypothesis(run_id: UUID, hypothesis_id: UUID) -> JSONResponse:
        run = orchestrator.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        h = orchestrator.approve_hypothesis(run_id, hypothesis_id)
        if h is None:
            raise HTTPException(status_code=404, detail="hypothesis not found")
        return JSONResponse(_hypothesis_payload(h))

    @app.post("/api/v1/runs/{run_id}/hypotheses/{hypothesis_id}/reject", dependencies=[Depends(_authed)])
    def reject_hypothesis(run_id: UUID, hypothesis_id: UUID, reason: str = "") -> JSONResponse:
        run = orchestrator.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        h = orchestrator.reject_hypothesis(run_id, hypothesis_id, reason=reason)
        if h is None:
            raise HTTPException(status_code=404, detail="hypothesis not found")
        return JSONResponse(_hypothesis_payload(h))

    # Phase 11: serve the dependency-free operator dashboard from disk.
    _dash = _ArgusRoot() / "dashboard"
    if _dash.is_dir():
        app.mount("/dashboard", StaticFiles(directory=str(_dash), html=True), name="dashboard")

    @app.get("/api/v1/runs/{run_id}/hypotheses", dependencies=[Depends(_authed)])
    def list_hypotheses(run_id: UUID) -> JSONResponse:
        if orchestrator.get_run(run_id) is None:
            raise HTTPException(status_code=404, detail="run not found")
        hyps = orchestrator.list_hypotheses(run_id)
        return JSONResponse(_hypotheses_payload(run_id, hyps))

    @app.post("/api/v1/runs/{run_id}/hypotheses/{hypothesis_id}/approve", dependencies=[Depends(_authed)])
    def approve_hypothesis(run_id: UUID, hypothesis_id: UUID) -> JSONResponse:
        if orchestrator.get_run(run_id) is None:
            raise HTTPException(status_code=404, detail="run not found")
        h = orchestrator.approve_hypothesis(run_id, hypothesis_id)
        if h is None:
            raise HTTPException(status_code=404, detail="hypothesis not found")
        return JSONResponse(_hypothesis_payload(h))

    @app.post("/api/v1/runs/{run_id}/hypotheses/{hypothesis_id}/reject", dependencies=[Depends(_authed)])
    def reject_hypothesis(run_id: UUID, hypothesis_id: UUID, payload: dict) -> JSONResponse:
        if orchestrator.get_run(run_id) is None:
            raise HTTPException(status_code=404, detail="run not found")
        h = orchestrator.reject_hypothesis(run_id, hypothesis_id, reason=str(payload.get("reason", "")))
        if h is None:
            raise HTTPException(status_code=404, detail="hypothesis not found")
        return JSONResponse(_hypothesis_payload(h))
    return app
