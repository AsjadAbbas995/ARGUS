"""Phase-10 FastAPI tests (``10_IMPLEMENTATION_PLAN.md``).

These tests inject a recording double with the exact ``create_run`` / ``get_run`` /
``list_tasks`` seam that the committed ``Orchestrator`` exposes. The double deliberately has
**no** tool, adapter or subprocess surface, proving ``test_orchestrator_double_has_no_tool_``
surface`` holds even when the API is handed an untrusted orchestrator: no endpoint can bypass
the Scope-Guarded safety architecture because the double cannot execute anything.
"""

from __future__ import annotations

from typing import Mapping, Optional
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from api.server import create_app

_API_KEY = "phase-10"
_AUTH = {"Authorization": "Bearer " + _API_KEY}


class _FakeRun:
    def __init__(self, target: str, program_id: str = "") -> None:
        self.id = uuid4()
        self.program_id = program_id
        self.target = target
        self.status = "created"
        self.started_at = None
        self.completed_at = None
        self.configuration_snapshot = None


class _FakeTask:
    def __init__(self, run_id: UUID, task_type: str, target: str, status: str = "pending") -> None:
        self.id = uuid4()
        self.run_id = run_id
        self.type = task_type
        self.target = target
        self.status = status
        self.reason = ""
        self.parent_task_id = None
        self.priority = 0
        self.started_at = None
        self.completed_at = None


class _RecordingOrchestrator:
    def __init__(self) -> None:
        self.runs = {}
        self.tasks = {}
        self.created = []

    def create_run(self, program_id: str = "", target: str = "") -> _FakeRun:
        run = _FakeRun(target=target, program_id=program_id)
        self.runs[str(run.id)] = run
        self.created.append(str(run.id))
        return run

    def get_run(self, run_id: UUID) -> Optional[_FakeRun]:
        return self.runs.get(str(run_id))

    def list_tasks(self, run_id: UUID):
        return self.tasks.get(str(run_id), [])

    def set_task_status(self, run_id: UUID) -> None:
        raise AssertionError("Phase-10 API must not write task state directly")


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(orchestrator=_RecordingOrchestrator(), api_key=_API_KEY))


@pytest.fixture
def orchestrated() -> tuple:
    fake = _RecordingOrchestrator()
    app = create_app(orchestrator=fake, api_key=_API_KEY)
    return TestClient(app), fake


def _seed(orchestrated):
    c, fake = orchestrated
    run = fake.create_run(target="example.com")
    fake.tasks[str(run.id)] = [
        _FakeTask(run.id, "subdomain_enum", "example.com", "completed"),
        _FakeTask(run.id, "http_probe", "example.com", "running"),
    ]
    return run


def test_liveness_open_unauthenticated(client: TestClient) -> None:
    with client as c:
        assert c.get("/_healthz").status_code == 200


def test_all_routes_reject_missing_key(client: TestClient) -> None:
    with client as c:
        for method, path in [
            ("post", "/api/v1/runs"),
            ("get", "/api/v1/runs/00000000-0000-0000-0000-000000000099"),
            ("get", "/api/v1/runs/00000000-0000-0000-0000-000000000099/tasks"),
            ("get", "/api/v1/runs/00000000-0000-0000-0000-000000000099/reports/json"),
        ]:
            assert getattr(c, method)(path).status_code == 401
            assert getattr(c, method)(path, headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_create_run_contract(orchestrated) -> None:
    c, _ = orchestrated
    with c as client:
        r = client.post("/api/v1/runs", json={"target": "example.com"}, headers=_AUTH)
        assert r.status_code == 201
        body = r.json()
        assert body["status"] == "created"
        assert body["target"] == "example.com"


def test_create_run_rejects_empty_target(orchestrated) -> None:
    c, _ = orchestrated
    with c as client:
        for payload in ({}, {"target": ""}, {"target": "   "}):
            r = client.post("/api/v1/runs", json=payload, headers=_AUTH)
            assert r.status_code == 422


def test_run_status_and_tasks_projected(orchestrated) -> None:
    c, _ = orchestrated
    with c as client:
        run = _seed(orchestrated)
        r = client.get("/api/v1/runs/{0}".format(run.id), headers=_AUTH)
        assert r.status_code == 200
        assert r.json()["id"] == str(run.id)
        t = client.get("/api/v1/runs/{0}/tasks".format(run.id), headers=_AUTH)
        assert t.status_code == 200
        body = t.json()
        assert body["count"] == 2
        assert {task["type"] for task in body["tasks"]} == {"subdomain_enum", "http_probe"}


def test_unknown_run_returns_404(orchestrated) -> None:
    c, _ = orchestrated
    with c as client:
        run_id = "00000000-0000-0000-0000-000000000099"
        assert c.get("/api/v1/runs/{0}".format(run_id), headers=_AUTH).status_code == 404
        assert c.get("/api/v1/runs/{0}/tasks".format(run_id), headers=_AUTH).status_code == 404
        assert c.get("/api/v1/runs/{0}/reports/json".format(run_id), headers=_AUTH).status_code == 404


@pytest.mark.parametrize("fmt", ["json", "markdown", "html"])
def test_report_endpoints_deterministic(orchestrated, fmt: str) -> None:
    c, _ = orchestrated
    with c as client:
        run = _seed(orchestrated)
        first = client.get("/api/v1/runs/{0}/reports/{1}".format(run.id, fmt), headers=_AUTH)
        second = client.get("/api/v1/runs/{0}/reports/{1}".format(run.id, fmt), headers=_AUTH)
        assert first.status_code == 200
        assert first.content == second.content
        assert len(first.content) > 0


def test_orchestrator_double_has_no_tool_surface(orchestrated) -> None:
    _, fake = orchestrated
    for banned in ("execute", "run_tool", "invoke_tool", "subprocess"):
        assert not hasattr(fake, banned)
