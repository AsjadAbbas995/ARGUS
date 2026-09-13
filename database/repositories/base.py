"""Base repository helpers and a shared connection context."""

from __future__ import annotations

from typing import Optional, Sequence

import psycopg

from core.config import Config


class DatabaseConnection:
    """Thin wrapper around a psycopg connection (dict row factory)."""

    def __init__(self, url: str):
        self.url = url
        self._conn: Optional[psycopg.Connection] = None

    def connect(self) -> psycopg.Connection:
        if self._conn is None or self._conn.closed:
            self._conn = psycopg.connect(self.url, row_factory=dict_row)
        return self._conn

    def close(self) -> None:
        if self._conn is not None and not self._conn.closed:
            self._conn.close()
        self._conn = None

    def __enter__(self) -> "DatabaseConnection":
        self.connect()
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    @classmethod
    def from_config(cls, config: Config) -> "DatabaseConnection":
        return cls(config.database.url)


class BaseRepository:
    """Common query helpers."""

    def __init__(self, conn: psycopg.Connection):
        self.conn = conn

    def _insert(
        self,
        table: str,
        values: dict,
        returning: Sequence[str] = ("*",),
    ) -> dict:
        columns = list(values)
        placeholders = ", ".join("%s" for _ in columns)
        col_sql = ", ".join(f'"{c}"' for c in columns)
        return_sql = ", ".join(returning)
        cur = self.conn.execute(
            f'INSERT INTO "{table}" ({col_sql}) VALUES ({placeholders}) '
            f"RETURNING {return_sql}",
            [values[c] for c in columns],
        )
        return cur.fetchone()

    def _update(
        self,
        table: str,
        row_id,
        values: dict,
        returning: Sequence[str] = ("*",),
    ) -> dict:
        assignments = ", ".join(f'"{c}" = %s' for c in values)
        return_sql = ", ".join(returning)
        cur = self.conn.execute(
            f'UPDATE "{table}" SET {assignments} WHERE id = %s RETURNING {return_sql}',
            [*values.values(), row_id],
        )
        return cur.fetchone()

    def _fetch_one(
        self, sql: str, params: Sequence = ()
    ) -> Optional[dict]:
        cur = self.conn.execute(sql, params)
        return cur.fetchone()

    def _fetch_all(self, sql: str, params: Sequence = ()) -> list[dict]:
        cur = self.conn.execute(sql, params)
        return cur.fetchall()