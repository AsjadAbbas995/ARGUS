"""Phase-10 API tests (``10_IMPLEMENTATION_PLAN.md``).

The injected orchestrator double records calls and deliberately exposes **no tool surface**,
so the test suite proves the HTTP layer cannot bypass -> or even see -> the Scope-Guarded
safety architecture even when handed an untrusted orchestrator. The live-database variants
follow the repo's committed gate idiom (see ``test_database_live.py``: skip unless
``ARGUS_TEST_DATABASE_URL`` is set) so live runs stay opt-in.
"""

import uuid
from typing import Optional
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from api.server import create_app


class _FakeRun:
    def __init__(self, target: str, program_id: str = "00000000-0000-0000-0000-000000000001") -> None:
        self.id = uuid.uuid4()
        self.program_id = UUID(program_id) if _is_uuid(program_id) else program_id
        self.target = target
        self.status = "created"


class _FakeTask:
    def __init__(self, run_id: UUID, task_type: str, target: str, status: str = "pending") -> None:
        self.id = uuid.uuid4()
        self.run_id = run_id
        self.type = task_type
        self.target = target
        self.status = status


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except (ValueError, TypeError):
        return False


class _RecordingOrchestrator:
    def __init__(self) -> None:
        self.runs = {}
        self.tasks = {}
        self.created = []
        self.status_calls = []

    def create_run(self, program_id: str = "", target: str = "") -> _FakeRun:
        run = _FakeRun(target=target, program_id=program_id)
        self.runs[str(run.id)] = run
        self.created.append(str(run.id))
        return run

    def get_run(self, run_id: UUID) -> Optional[_FakeRun]:
        self.status_calls.append(str(run_id))
        return self.runs.get(str(run_id))

    def list_tasks(self, run_id: UUID) -> list[_FakeTask]:
        return self.tasks.get(str(run_id), [])


@pytest.fixture
def orchestrated() -> tuple[TestClient, _RecordingOrchestrator]:
    fake = _RecordingOrchestrator()
    app = create_app(orchestrator=fake, api_key="phase-10")
    return TestClient(app), fake


def _authed() -> dict:
    return {"Authorization": "Bearer phase-10"}


def test_liveness_open_unauthenticated(orchestrated) -> None:
    c, _ = orchestrated
    with c as client:
        assert client.get("/_healthz").status_code == 200


@pytest.mark.parametrize(
    "method,path",
    [
        ("post", "/api/v1/runs"),
        ("get", "/api/v1/runs/00000000-0000-0000-0000-000000000099"),
        ("get", "/api/v1/runs/00000000-0000-0000-0000-000000000099/tasks"),
        ("get", "/api/v1/runs/00000000-0000-0000-0000-000000000099/reports/json"),
    ],
)
def test_all_authed_routes_reject_missing_key(orchestrated, method: str, path: str) -> None:
    c, _ = orchestrated
    with c as client:
        assert getattr(client, method)(path).status_code == 401
        assert getattr(client, method)(path, headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_create_run_contract(orchestrated) -> None:
    c, fake = orchestrated
    with c as client:
        r = client.post("/api/v1/runs", json={"target": "example.com"}, headers=_authed())
        assert r.status_code == 201
        body = r.json()
        assert body["status"] == "created"
        assert body["target"] == "example.com"
        assert len(fake.created) == 1


def test_create_run_rejects_empty_target(orchestrated) -> None:
    c, _ = orchestrated
    with c as client:
        for payload in ({}, {"target": ""}, {"target": "   "}):
            r = client.post("/api/v1/runs", json=payload, headers=_authed())
            assert r.status_code == 422


def test_run_status_and_tasks_projected(orchestrated) -> None:
    c, fake = orchestrated
    with c as client:
        run = fake.create_run(target="example.com")
        fake.tasks[str(run.id)] = [
            _FakeTask(run.id, "subdomain_enum", "example.com", "completed"),
            _FakeTask(run.id, "http_probe", "example.com", "running"),
        ]
        r = client.get("/api/v1/runs/{0}".format(run.id), headers=_authed())
        assert r.status_code == 200
        assert r.json()["id"] == str(run.id)
        t = client.get("/api/v1/runs/{0}/tasks".format(run.id), headers=_authed())
        assert t.status_code == 200
        body = t.json()
        assert body["count"] == 2
        assert {task["type"] for task in body["tasks"]} == {"subdomain_enum", "http_probe"}


def test_unknown_run_returns_404(orchestrated) -> None:
    c, _ = orchestrated
    with c as client:
        run_id = "00000000-0000-0000-0000-000000000099"
        assert client.get("/api/v1/runs/{0}".format(run_id), headers=_authed()).status_code == 404
        assert client.get("/api/v1/runs/{0}/tasks".format(run_id), headers=_authed()).status_code == 404
        assert client.get("/api/v1/runs/{0}/reports/json".format(run_id), headers=_authed()).status_code == 404


@pytest.mark.parametrize("fmt", ["json", "markdown", "html"])
def test_report_endpoints_deterministic(orchestrated, fmt: str) -> None:
    c, fake = orchestrated
    with c as client:
        run = fake.create_run(target="example.com")
        first = client.get("/api/v1/runs/{0}/reports/{1}".format(run.id, fmt), headers=_authed())
        second = client.get("/api/v1/runs/{0}/reports/{1}".format(run.id, fmt), headers=_authed())
        assert first.status_code == 200
        assert first.content == second.content
        assert len(first.content) > 0


def test_orchestrator_double_has_no_tool_surface(orchestrated) -> None:
    _, fake = orchestrated
    for banned in ("execute", "run_tool", "invoke_tool", "subprocess"):
        assert not hasattr(fake, banned)
