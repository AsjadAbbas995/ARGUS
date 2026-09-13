"""Deterministic SQL migration runner.

Applies ``database/migrations/*.sql`` in lexical (version) order, recording each
applied version in ``schema_migrations``. Revert files are named
``<version>_<name>.down.sql`` and drop objects in reverse dependency order.

Gate: a migration either fully applies or fully reverts; each file runs inside
its own transaction.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import psycopg
from psycopg.rows import dict_row

from core.config import Config

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class MigrationError(RuntimeError):
    """Raised when a migration cannot be applied cleanly."""


def migration_files(directory: Path = MIGRATIONS_DIR) -> list[Path]:
    up = sorted(
        p for p in directory.glob("*.sql") if not p.name.endswith(".down.sql")
    )
    return up


def version_of(path: Path) -> int:
    return int(path.name.split("_", 1)[0])


def _applied_versions(conn: psycopg.Connection) -> set[int]:
    cur = conn.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    )
    return {row[0] for row in cur.fetchall()}


def apply(conn: psycopg.Connection, directory: Path = MIGRATIONS_DIR) -> list[int]:
    """Apply all pending migrations, returning the versions applied."""
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version integer PRIMARY KEY,"
            " name text NOT NULL,"
            " applied_at timestamptz NOT NULL DEFAULT now())"
        )
    except psycopg.Error as exc:
        raise MigrationError(f"cannot create schema_migrations: {exc}") from exc

    applied = _applied_versions(conn)
    versions = []
    for path in migration_files(directory):
        version = version_of(path)
        if version in applied:
            continue
        try:
            with conn.transaction():
                conn.execute(path.read_text(encoding="utf-8"))
                conn.execute(
                    "INSERT INTO schema_migrations (version, name) VALUES (%s, %s)",
                    (version, path.name),
                )
        except psycopg.Error as exc:
            raise MigrationError(f"migration {path.name} failed: {exc}") from exc
        versions.append(version)
    return versions


def revert(
    conn: psycopg.Connection,
    target_version: int = 0,
    directory: Path = MIGRATIONS_DIR,
) -> list[int]:
    """Revert applied migrations back to ``target_version`` (default: none).

    Returns the list of versions reverted, in reverse version order.
    """
    applied = sorted(_applied_versions(conn))
    to_revert = [v for v in applied if v > target_version]
    reverted: list[int] = []
    for version in reversed(to_revert):
        candidates = [
            p
            for p in directory.glob(f"{version:04d}_*.down.sql")
        ]
        if not candidates:
            raise MigrationError(
                f"no down migration found for version {version}"
            )
        down = candidates[0]
        try:
            with conn.transaction():
                conn.execute(down.read_text(encoding="utf-8"))
        except psycopg.Error as exc:
            raise MigrationError(f"revert {down.name} failed: {exc}") from exc
        reverted.append(version)
    return reverted


def ensure_migrated(conn: psycopg.Connection) -> list[int]:
    """Apply pending migrations; idempotent."""
    return apply(conn)


def connect(url: str) -> psycopg.Connection:
    """Open a psycopg connection (row factory: dict)."""
    return psycopg.connect(url, row_factory=dict_row)


def migrate_from_config(config: Config) -> list[int]:
    """Convenience: connect from parsed config and apply pending migrations."""
    with connect(config.database.url) as conn:
        return apply(conn)