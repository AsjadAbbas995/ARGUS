"""Shared test fixtures."""

from __future__ import annotations

import os

import psycopg
import pytest


def _postgres_available() -> bool:
    url = os.environ.get("ARGUS_TEST_DATABASE_URL")
    if not url:
        return False
    try:
        conn = psycopg.connect(url, connect_timeout=2)
        conn.close()
        return True
    except psycopg.Error:
        return False


@pytest.fixture
def database_url() -> str:
    if not _postgres_available():
        pytest.skip("ARGUS_TEST_DATABASE_URL not set or unreachable")
    return os.environ["ARGUS_TEST_DATABASE_URL"]