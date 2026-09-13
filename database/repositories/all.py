"""Concrete repositories mapping models to their ``05_DATA_MODEL.md`` tables.

All persistence honors the documented UNIQUE/CHECK constraints; duplicate-safe
inserts (upserts) are used where the data model allows deduplication.
"""

from __future__ import annotations

from typing import Optional

import psycopg

from database.models.entities import (
    Asset,
    AssetIp,
    DnsRecord,
    Evidence,
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
from database.repositories.base import BaseRepository


class OrganizationRepository(BaseRepository):
    def upsert(self, name: str) -> dict:
        cur = self.conn.execute(
            "INSERT INTO organizations (name) VALUES (%s) "
            "ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name "
            "RETURNING *",
            (name,),
        )
        return cur.fetchone()

    def get(self, organization_id) -> Optional[dict]:
        return self._fetch_one(
            "SELECT * FROM organizations WHERE id = %s", (organization_id,)
        )


class ProgramRepository(BaseRepository):
    def upsert(self, organization_id, name: str, status: str = "active") -> dict:
        cur = self.conn.execute(
            "INSERT INTO programs (organization_id, name, status) VALUES (%s, %s, %s) "
            "ON CONFLICT (organization_id, name) "
            "DO UPDATE SET status = EXCLUDED.status "
            "RETURNING *",
            (organization_id, name, status),
        )
        return cur.fetchone()

    def get(self, program_id) -> Optional[dict]:
        return self._fetch_one("SELECT * FROM programs WHERE id = %s", (program_id,))


class RunRepository(BaseRepository):
    def insert(self, run: Run) -> dict:
        return self._insert(
            "runs",
            {
                "id": run.id,
                "program_id": run.program_id,
                "status": run.status,
                "target": run.target,
                "configuration_snapshot": psycopg.types.json.Jsonb(
                    run.configuration_snapshot
                ),
                "started_at": run.started_at,
                "completed_at": run.completed_at,
                "created_at": run.created_at,
                "updated_at": run.updated_at,
            },
        )

    def get(self, run_id) -> Optional[dict]:
        return self._fetch_one("SELECT * FROM runs WHERE id = %s", (run_id,))

    def update_status(self, run_id, status: str) -> dict:
        cur = self.conn.execute(
            "UPDATE runs SET status = %s, updated_at = now() WHERE id = %s RETURNING *",
            (status, run_id),
        )
        return cur.fetchone()

    def mark_started(self, run_id) -> dict:
        cur = self.conn.execute(
            "UPDATE runs SET status = 'RECONNING', started_at = now(), "
            "updated_at = now() WHERE id = %s RETURNING *",
            (run_id,),
        )
        return cur.fetchone()

    def mark_completed(self, run_id) -> dict:
        cur = self.conn.execute(
            "UPDATE runs SET status = 'COMPLETED', completed_at = now(), "
            "updated_at = now() WHERE id = %s RETURNING *",
            (run_id,),
        )
        return cur.fetchone()

    def mark_failed(self, run_id) -> dict:
        cur = self.conn.execute(
            "UPDATE runs SET status = 'FAILED', completed_at = now(), "
            "updated_at = now() WHERE id = %s RETURNING *",
            (run_id,),
        )
        return cur.fetchone()


class ScopeRuleRepository(BaseRepository):
    def upsert(self, rule: ScopeRule) -> dict:
        cur = self.conn.execute(
            "INSERT INTO scope_rules (program_id, rule_type, value, allowed) "
            "VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (program_id, rule_type, value) "
            "DO UPDATE SET allowed = EXCLUDED.allowed "
            "RETURNING *",
            (rule.program_id, rule.rule_type, rule.value, rule.allowed),
        )
        return cur.fetchone()

    def list_for_program(self, program_id) -> list[dict]:
        return self._fetch_all(
            "SELECT * FROM scope_rules WHERE program_id = %s", (program_id,)
        )


class AssetRepository(BaseRepository):
    def upsert(self, asset: Asset) -> dict:
        cur = self.conn.execute(
            "INSERT INTO assets (program_id, hostname, source, discovered_at) "
            "VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (program_id, hostname) "
            "DO UPDATE SET source = EXCLUDED.source "
            "RETURNING *",
            (asset.program_id, asset.hostname, asset.source, asset.discovered_at),
        )
        return cur.fetchone()

    def get_by_hostname(self, program_id, hostname: str) -> Optional[dict]:
        return self._fetch_one(
            "SELECT * FROM assets WHERE program_id = %s AND hostname = %s",
            (program_id, hostname),
        )

    def search_hostname(self, hostname: str) -> list[dict]:
        return self._fetch_all(
            "SELECT * FROM assets WHERE hostname = %s", (hostname,)
        )


class IpRepository(BaseRepository):
    def upsert(self, address: str) -> dict:
        cur = self.conn.execute(
            "INSERT INTO ips (address) VALUES (%s) "
            "ON CONFLICT (address) DO UPDATE SET address = EXCLUDED.address "
            "RETURNING id, address::text AS address, first_seen",
            (address,),
        )
        return cur.fetchone()


class AssetIpRepository(BaseRepository):
    def upsert(self, asset_id, ip_id) -> dict:
        cur = self.conn.execute(
            "INSERT INTO asset_ips (asset_id, ip_id) VALUES (%s, %s) "
            "ON CONFLICT (asset_id, ip_id) DO NOTHING RETURNING *",
            (asset_id, ip_id),
        )
        return cur.fetchone()


class DnsRecordRepository(BaseRepository):
    def insert(self, record: DnsRecord) -> dict:
        return self._insert(
            "dns_records",
            {
                "asset_id": record.asset_id,
                "record_type": record.record_type,
                "value": record.value,
                "resolved_at": record.resolved_at,
            },
            returning=("id", "asset_id", "record_type", "value"),
        )

    def list_for_asset(self, asset_id) -> list[dict]:
        return self._fetch_all(
            "SELECT * FROM dns_records WHERE asset_id = %s", (asset_id,)
        )


class PortRepository(BaseRepository):
    def upsert(self, port: Port) -> dict:
        cur = self.conn.execute(
            "INSERT INTO ports (ip_id, port_number, protocol, state, service, version) "
            "VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (ip_id, port_number, protocol) "
            "DO UPDATE SET state = EXCLUDED.state, service = EXCLUDED.service, "
            "version = EXCLUDED.version "
            "RETURNING *",
            (
                port.ip_id,
                port.port_number,
                port.protocol,
                port.state,
                port.service,
                port.version,
            ),
        )
        return cur.fetchone()

    def get_by_ip_port(self, ip_id, port_number: int, protocol: str = "tcp"):
        return self._fetch_one(
            "SELECT * FROM ports WHERE ip_id = %s AND port_number = %s "
            "AND protocol = %s",
            (ip_id, port_number, protocol),
        )


class WebAppRepository(BaseRepository):
    def upsert(self, app: WebApp) -> dict:
        cur = self.conn.execute(
            "INSERT INTO web_apps "
            "(asset_id, port_id, status_code, title, server_header) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (asset_id, port_id) "
            "DO UPDATE SET status_code = EXCLUDED.status_code, "
            "title = EXCLUDED.title, server_header = EXCLUDED.server_header "
            "RETURNING *",
            (
                app.asset_id,
                app.port_id,
                app.status_code,
                app.title,
                app.server_header,
            ),
        )
        return cur.fetchone()


class TaskRepository(BaseRepository):
    def insert(self, task: Task) -> dict:
        return self._insert(
            "tasks",
            {
                "run_id": task.run_id,
                "type": task.type,
                "target": task.target,
                "parent_task_id": task.parent_task_id,
                "priority": task.priority,
                "status": task.status,
                "fingerprint": task.fingerprint,
                "reason": task.reason,
                "created_at": task.created_at,
                "started_at": task.started_at,
                "completed_at": task.completed_at,
            },
        )

    def get_by_fingerprint(self, run_id, fingerprint: str) -> Optional[dict]:
        return self._fetch_one(
            "SELECT * FROM tasks WHERE run_id = %s AND fingerprint = %s",
            (run_id, fingerprint),
        )

    def list_for_run(self, run_id) -> list[dict]:
        return self._fetch_all(
            "SELECT * FROM tasks WHERE run_id = %s ORDER BY created_at", (run_id,)
        )

    def list_by_status(self, run_id, status: str) -> list[dict]:
        return self._fetch_all(
            "SELECT * FROM tasks WHERE run_id = %s AND status = %s ORDER BY created_at",
            (run_id, status),
        )

    def update_status(self, task_id, status: str, completed: bool = False) -> dict:
        completed_sql = ", completed_at = now()" if completed else ""
        cur = self.conn.execute(
            f"UPDATE tasks SET status = %s, "
            f"started_at = COALESCE(started_at, now()) {completed_sql} "
            f"WHERE id = %s RETURNING *",
            (status, task_id),
        )
        return cur.fetchone()


class ToolRunRepository(BaseRepository):
    def insert(self, run: ToolRun) -> dict:
        return self._insert(
            "tool_runs",
            {
                "task_id": run.task_id,
                "tool_name": run.tool_name,
                "command": run.command,
                "exit_code": run.exit_code,
                "raw_output_ref": run.raw_output_ref,
                "started_at": run.started_at,
                "completed_at": run.completed_at,
            },
        )

    def finalize(self, tool_run_id, exit_code: int, raw_output_ref: Optional[str]):
        cur = self.conn.execute(
            "UPDATE tool_runs SET exit_code = %s, raw_output_ref = %s, "
            "completed_at = now() WHERE id = %s RETURNING *",
            (exit_code, raw_output_ref, tool_run_id),
        )
        return cur.fetchone()


class EvidenceRepository(BaseRepository):
    def insert(self, evidence: Evidence) -> dict:
        return self._insert(
            "evidence",
            {
                "tool_run_id": evidence.tool_run_id,
                "entity_type": evidence.entity_type,
                "entity_id": evidence.entity_id,
                "raw_reference": evidence.raw_reference,
            },
        )


class Repositories:
    """Aggregate facade over all repositories sharing one connection."""

    def __init__(self, conn: psycopg.Connection):
        self.conn = conn
        self.organizations = OrganizationRepository(conn)
        self.programs = ProgramRepository(conn)
        self.runs = RunRepository(conn)
        self.scope_rules = ScopeRuleRepository(conn)
        self.assets = AssetRepository(conn)
        self.ips = IpRepository(conn)
        self.asset_ips = AssetIpRepository(conn)
        self.dns_records = DnsRecordRepository(conn)
        self.ports = PortRepository(conn)
        self.web_apps = WebAppRepository(conn)
        self.tasks = TaskRepository(conn)
        self.tool_runs = ToolRunRepository(conn)
        self.evidence = EvidenceRepository(conn)