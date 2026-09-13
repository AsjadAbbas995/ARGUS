"""Live integration tests against a real PostgreSQL.

Skipped automatically when ``ARGUS_TEST_DATABASE_URL`` is unset/unreachable
(see conftest.py). These verify migrations apply/revert cleanly and that the
repository layer honors ``05_DATA_MODEL.md`` constraints.
"""

from __future__ import annotations

import psycopg
import pytest

from database.migrate import apply, migration_files, revert, version_of
from database.repositories.all import Repositories
from database.repositories.base import DatabaseConnection

from database.models.entities import (
    Asset,
    DnsRecord,
    Ip,
    Organization,
    Port,
    Program,
    Run,
    ScopeRule,
    Task,
    ToolRun,
    WebApp,
)


@pytest.fixture
def conn(database_url: str):
    c = psycopg.connect(database_url)
    yield c
    c.close()


@pytest.fixture
def schema(database_url: str):
    """Fully migrate a fresh test database, yield it, then revert."""
    c = psycopg.connect(database_url)
    revert(c, 0)
    applied = apply(c)
    assert applied == sorted(version_of(p) for p in migration_files())
    yield c
    revert(c, 0)
    c.close()


def test_migrations_apply_and_revert(schema) -> None:
    cur = schema.execute(
        "SELECT version, name FROM schema_migrations ORDER BY version"
    )
    rows = cur.fetchall()
    assert len(rows) == len(migration_files())
    assert rows[0][0] == 1
    assert schema.execute("SELECT to_regclass('public.organizations')").fetchone()[0]


def test_apply_is_idempotent(schema) -> None:
    before = schema.execute(
        "SELECT count(*) FROM schema_migrations"
    ).fetchone()[0]
    assert apply(schema) == []
    after = schema.execute("SELECT count(*) FROM schema_migrations").fetchone()[0]
    assert after == before


def _seed_org_program(schema) -> tuple[dict, dict]:
    repos = Repositories(schema)
    org = repos.organizations.upsert("Acme Corp")
    prog = repos.programs.upsert(org["id"], "Q4 Pentest")
    return org, prog


def test_run_insert_and_lifecycle(schema) -> None:
    repos = Repositories(schema)
    org, prog = _seed_org_program(schema)
    run = Run(
        program_id=prog["id"],
        target="example.com",
        configuration_snapshot={"scope": {"allowed_domains": ["example.com"]}},
    )
    created = repos.runs.insert(run)
    assert created["id"] == run.id
    assert created["status"] == "CREATED"
    assert created["configuration_snapshot"]["scope"]["allowed_domains"] == [
        "example.com"
    ]

    started = repos.runs.mark_started(run.id)
    assert started["status"] == "RECONNING"
    assert started["started_at"] is not None

    done = repos.runs.mark_completed(run.id)
    assert done["status"] == "COMPLETED"
    assert done["completed_at"] is not None


def test_task_and_tool_run_chain(schema) -> None:
    repos = Repositories(schema)
    org, prog = _seed_org_program(schema)
    run = Run(program_id=prog["id"], target="example.com")
    repos.runs.insert(run)

    task = Task(
        run_id=run.id,
        type="subdomain_discovery",
        target="example.com",
        fingerprint="sub:example.com",
    )
    task_row = repos.tasks.insert(task)
    assert task_row["run_id"] == run.id
    assert task_row["status"] == "pending"

    tool = ToolRun(
        task_id=task.id,
        tool_name="subfinder",
        command=["subfinder", "-d", "example.com"],
    )
    tool_row = repos.tool_runs.insert(tool)
    assert tool_row["task_id"] == task.id

    finalized = repos.tool_runs.finalize(tool.id, 0, "storage/raw/subfinder/x")
    assert finalized["exit_code"] == 0

    persisted = repos.tasks.get_by_fingerprint(run.id, "sub:example.com")
    assert persisted["id"] == task.id


def test_task_fingerprint_unique_per_run(schema) -> None:
    repos = Repositories(schema)
    org, prog = _seed_org_program(schema)
    run = Run(program_id=prog["id"], target="example.com")
    repos.runs.insert(run)

    repos.tasks.insert(
        Task(
            run_id=run.id,
            type="x",
            target="example.com",
            fingerprint="dup",
        )
    )
    with pytest.raises(psycopg.errors.UniqueViolation):
        repos.tasks.insert(
            Task(run_id=run.id, type="x", target="example.com", fingerprint="dup")
        )


def test_asset_dedup_and_dns(schema) -> None:
    repos = Repositories(schema)
    org, prog = _seed_org_program(schema)
    run = Run(program_id=prog["id"], target="example.com")
    repos.runs.insert(run)

    a1 = repos.assets.upsert(
        Asset(
            program_id=prog["id"],
            hostname="www.example.com",
            source="subfinder",
        )
    )
    a2 = repos.assets.upsert(
        Asset(
            program_id=prog["id"],
            hostname="www.example.com",
            source="amass",
        )
    )
    assert a1["id"] == a2["id"], "asset dedup violated unique constraint"

    ip = repos.ips.upsert("203.0.113.10")
    assert ip["address"] == "203.0.113.10"

    repos.dns_records.insert(
        DnsRecord(asset_id=a1["id"], record_type="A", value="203.0.113.10")
    )
    records = repos.dns_records.list_for_asset(a1["id"])
    assert len(records) == 1
    assert records[0]["record_type"] == "A"


def test_scope_rules_upsert(schema) -> None:
    repos = Repositories(schema)
    org, prog = _seed_org_program(schema)
    repos.scope_rules.upsert(
        ScopeRule(
            program_id=prog["id"],
            rule_type="domain",
            value="example.com",
            allowed=True,
        )
    )
    repos.scope_rules.upsert(
        ScopeRule(
            program_id=prog["id"],
            rule_type="domain",
            value="example.com",
            allowed=True,
        )
    )
    rules = repos.scope_rules.list_for_program(prog["id"])
    assert len(rules) == 1


def test_ip_and_port_and_webapp(schema) -> None:
    repos = Repositories(schema)
    org, prog = _seed_org_program(schema)
    asset = repos.assets.upsert(
        Asset(program_id=prog["id"], hostname="app.example.com", source="manual")
    )
    ip = repos.ips.upsert("198.51.100.7")
    port = repos.ports.upsert(
        Port(ip_id=ip["id"], port_number=443, protocol="tcp", state="open",
             service="https")
    )
    web = repos.web_apps.upsert(
        WebApp(
            asset_id=asset["id"],
            port_id=port["id"],
            status_code=200,
            title="Acme App",
            server_header="nginx",
        )
    )
    assert web["status_code"] == 200

    refreshed = repos.web_apps.upsert(
        WebApp(
            asset_id=asset["id"],
            port_id=port["id"],
            status_code=503,
            title="Acme App",
            server_header="nginx",
        )
    )
    assert refreshed["status_code"] == 503