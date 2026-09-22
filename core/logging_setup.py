"""Structured logging for ARGUS.

Standard library only. Emits single-line JSON records so that raw run output,
task lifecycle events, and future AI-agent input can be parsed and persisted
uniformly (see 09_OUTPUTS.md and 12_AI_PROMPTS.md).
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

#: Extra record attributes whose keys look secret must never be written verbatim
#: into structured logs (Phase-12 hardening: "logs never leak secrets"). Keys are
#: matched case-insensitively on the token set below. Note this is belted-and-
#: braced with the explicit standard-key skip-list in ``JsonFormatter.format``.
_SENSITIVE_EXTRA_TOKENS = (
    "password",
    "passwd",
    "secret",
    "token",
    "apikey",
    "api_key",
    "auth",
    "credential",
    "session",
    "cookie",
    "authorization",
    "bearer",
)


class JsonFormatter(logging.Formatter):
    """Formats a log record as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            payload["exc"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key in {
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "taskName",
                "message",
            }:
                continue
            if any(token in key.lower() for token in _SENSITIVE_EXTRA_TOKENS):
                payload.setdefault(key, "***REDACTED***")
                continue
            payload.setdefault(key, value)
        try:
            return json.dumps(payload, ensure_ascii=False, default=str)
        except TypeError:
            return json.dumps(
                {k: str(v) for k, v in payload.items()},
                ensure_ascii=False,
                default=str,
            )


def configure_logging(
    level: str | int = logging.INFO,
    *,
    json_lines: bool = True,
) -> logging.Logger:
    """Configure the root logger to emit structured JSON lines to stderr.

    Returns the root logger so callers can immediately obtain children via
    ``logging.getLogger("argus.*")``.
    """
    root = logging.getLogger()
    root.setLevel(level if isinstance(level, int) else getattr(logging, level.upper()))
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter() if json_lines else logging.Formatter("%(message)s"))
    root.handlers = [handler]
    return root


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the ``argus`` namespace."""
    return logging.getLogger(f"argus.{name}")
