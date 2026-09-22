"""Phase 12 hardening: logs never leak secrets (``10_IMPLEMENTATION_PLAN.md``).

``04_SCOPE_SAFETY.md`` ("AI cannot leave a trail of secrets") and DoD state that
no credential material may appear verbatim in any log line. ``JsonFormatter``
redacts extra record attributes whose key matches a sensitive token
(``core/logging_setup.py`` ``_SENSITIVE_EXTRA_TOKENS``). These tests pin that
redaction: even if a caller attaches ``token``/``password``/``api_key``/etc. as
an extra attribute, the formatted JSON must never contain the literal value.
"""

from __future__ import annotations

import logging

from core.logging_setup import JsonFormatter, _SENSITIVE_EXTRA_TOKENS


def _record(**extra: object) -> logging.LogRecord:
    """Build a LogRecord carrying arbitrary extra attributes."""
    record = logging.LogRecord(
        name="argus.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="probe",
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_sensitive_extra_keys_are_never_emitted_verbatim() -> None:
    for token in _SENSITIVE_EXTRA_TOKENS:
        secret = f"literal-{token}-{len(token)}"
        line = JsonFormatter().format(_record(**{token: secret}))
        assert secret not in line


def test_masks_sensitive_key_with_redaction_placeholder() -> None:
    line = JsonFormatter().format(_record(api_key="k-12345", password="hunter2"))
    assert '"api_key"' in line
    assert "k-12345" not in line
    assert "hunter2" not in line


def test_mask_keeps_key_present_for_audit() -> None:
    line = JsonFormatter().format(_record(client_secret="s3cr3t"))
    assert "client_secret" in line
    assert "s3cr3t" not in line


def test_non_sensitive_extra_is_unchanged() -> None:
    line = JsonFormatter().format(_record(host="example.com", run_id="r-1"))
    assert "example.com" in line
    assert "r-1" in line
