"""Subfinder adapter (``06_TOOL_CONTRACTS.md`` §Subfinder).

Passive subdomain enumeration for one in-scope root domain.

- Command: ``subfinder -d <domain> -json [-all]`` (argument array, never a shell string)
- Output: newline-delimited JSON lines
- Parser: JSON-lines -> deduplicated, normalized hostname list
- Normalized objects: ``assets`` (hostnames; ``05_DATA_MODEL.md`` §assets)
- Raw output: preserved by the Tool Runner under ``storage/raw/subfinder/``
- Safety: passive only; scope validated before execution.
"""

from __future__ import annotations

import json
from typing import Any

from core.scope_guard import ScopeGuard
from core.tool_runner import CommandResult
from recon.base import ToolAdapter


class SubfinderAdapter(ToolAdapter):
    name = "subfinder"
    executables = ("subfinder",)

    #: JSON field subfinder emits the discovered host under.
    HOST_FIELD = "host"

    # -- scope --------------------------------------------------------------

    def validate(self, task: Any, scope: ScopeGuard) -> None:
        self._require_in_scope(getattr(task, "target", ""), scope)

    # -- command construction -----------------------------------------------

    def build_command(self, task: Any, config: Any) -> list[str]:
        domain = getattr(task, "target", "").strip().lower().rstrip(".")
        if not domain:
            raise ValueError(f"subfinder: task.target must be a root domain, got {domain!r}")
        command = ["subfinder", "-d", domain, "-json"]
        if getattr(getattr(config, "recon", None), "aggressive_subdomain_discovery", True):
            command.append("-all")
        return command

    # -- parse / normalize --------------------------------------------------

    def parse(self, result: CommandResult) -> list[str]:
        """JSON-lines -> normalized, deduplicated hostnames.

        Malformed/empty/non-JSON lines are skipped (logged via the runner's
        stderr capture path), never fatal — a partially malformed subfinder
        stream must not lose the whole source (``13_TESTING_STRATEGY.md``).
        """
        hosts: list[str] = []
        seen: set[str] = set()
        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            hostname = self._host_from_line(line)
            if not hostname:
                continue
            hostname = hostname.strip().lower().rstrip(".")
            if not hostname or hostname.startswith("*."):
                continue  # wildcard entries are not concrete assets
            if hostname in seen:
                continue
            seen.add(hostname)
            hosts.append(hostname)
        return hosts

    def _host_from_line(self, line: str) -> str:
        """Extract the hostname from one JSON line, tolerating garbage."""
        try:
            record = json.loads(line)
        except ValueError:
            return ""
        if not isinstance(record, dict):
            return ""
        host = record.get(self.HOST_FIELD)
        return host if isinstance(host, str) else ""