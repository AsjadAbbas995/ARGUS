"""httpx probe adapter (``06_TOOL_CONTRACTS.md`` §httpx).

HTTP(S) probing + technology fingerprinting against one resolved ``host[:port]``.

- Command construction: ``httpx -json -tech-detect -title -status-code
  [ -follow-redirects]`` (argument array, never a shell string).
- Output format: JSON lines (newline-delimited objects, one per probed URL).
- Parser: JSON-lines -> ``web_apps`` + ``asset_technologies`` observations.
- Normalized objects: ``web_apps``, ``technologies``, ``asset_technologies``
  (``05_DATA_MODEL.md``).
- Raw output: preserved by the Tool Runner under ``storage/raw/httpx/``.
- Errors: per-host connection failure recorded, non-fatal. **Timeouts:**
  per-request, short. **Safety:** host must be in-scope before probing;
  redirect destinations are re-checked against scope before being followed
  (``04_SCOPE_SAFETY.md`` §HTTP Redirect Handling). **Tests:** fixture parse
  tests, including redirect-chain fixtures (``13_TESTING_STRATEGY.md``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from core.scope_guard import ScopeGuard
from core.tool_runner import CommandResult, ToolUnavailableError
from recon.base import ToolAdapter


@dataclass(frozen=True)
class WebAppObservation:
    """One probed web application (``05_DATA_MODEL.md`` §web_apps)."""

    host: str
    url: str
    scheme: str
    port: int
    status_code: int
    title: str = ""
    webserver: str = ""
    content_type: str = ""


@dataclass(frozen=True)
class TechnologyObservation:
    """A single detected technology (``05_DATA_MODEL.md`` §technologies)."""

    name: str


@dataclass(frozen=True)
class AssetTechnologyObservation:
    """Link between one probed host and one observed technology."""

    host: str
    technology: str


#: Field names httpx emits under ``-json`` mode.
URL_FIELD = "url"
SCHEME_FIELD = "scheme"
HOST_FIELD = "host"
PORT_FIELD = "port"
STATUS_FIELD = "status_code"
TITLE_FIELD = "title"
SERVER_FIELD = "webserver"
CONTENT_TYPE_FIELD = "content_type"
TECH_FIELD = "tech"
REDIRECT_FIELD = "location"
TECH_FIELD = "tech"

TECH_FIELD = "tech"
REDIRECT_DEST_FIELD = "location"
REDIRECT_STATUS = 302

#: Track whether ``-follow-redirects`` is present on the constructed command.
FOLLOW_REDIRECTS_FLAG = "-follow-redirects"


def extract_host_from_value(value: str) -> str:
    """Best-effort hostname from a URL/redirect value (scope-ready, lowercased)."""
    if "://" not in value:
        value = "http://" + value
    from urllib.parse import urlparse

    return (urlparse(value).hostname or "").lower()


class HttpxProbeAdapter(ToolAdapter):
    """Probe resolved host:port pairs with ``httpx`` and fingerprint tech."""

    name = "httpx"
    executables = ("httpx",)

    # -- scope ---------------------------------------------------------------

    def validate(self, task: Any, scope: ScopeGuard) -> None:
        host = extract_host_from_value(getattr(task, "target", ""))
        self._require_in_scope(host, scope)

    # -- command construction ------------------------------------------------

    def build_command(self, task: Any, config: Any) -> list[str]:
        target = getattr(task, "target", "")
        host = extract_host_from_value(target)
        if not host:
            raise ValueError(f"httpx: task.target must be a host[:port], got {target!r}")
        command = ["httpx", "-json", "-tech-detect", "-title", "-status-code"]
        if _follow_redirects(config):
            command.append(FOLLOW_REDIRECTS_FLAG)
        command.append(target)
        return command

    # -- parse ---------------------------------------------------------------

    def parse(self, result: CommandResult) -> list[Any]:
        """JSON lines -> web_app + technology observations (non-fatal parsing)."""
        apps: list[WebAppObservation] = []
        seen_pairs: set[tuple[str, str, str, str]] = set()
        tech_map: dict[str, set[str]] = {}

        for line in result.stdout.splitlines():
            text = line.strip()
            if not text:
                continue
            try:
                record = json.loads(text)
            except ValueError:
                continue  # malformed line skipped, not fatal
            if not isinstance(record, dict):
                continue

            url = record.get(URL_FIELD, "")
            if not isinstance(url, str) or not url:
                continue
            host = record.get(HOST_FIELD) or extract_host_from_value(url)
            if not host:
                continue

            scheme = record.get(SCHEME_FIELD) or "http"
            port = record.get(PORT_FIELD) or (443 if scheme == "https" else 80)
            pair = (
                host,
                url,
                str(scheme),
                str(port),
            )
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                apps.append(
                    WebAppObservation(
                        host=host,
                        url=url,
                        scheme=str(scheme),
                        port=int(port),
                        status_code=int(record.get(STATUS_FIELD) or 0),
                        title=str(record.get(TITLE_FIELD) or ""),
                        webserver=str(record.get(SERVER_FIELD) or ""),
                        content_type=str(record.get(CONTENT_TYPE_FIELD) or ""),
                    )
                )

            tech_list = record.get(TECH_FIELD) or ()
            if isinstance(tech_list, (list, tuple)):
                seen_names = tech_map.setdefault(host, set())
                for name in tech_list:
                    if isinstance(name, str) and name.strip() and name.strip() not in seen_names:
                        seen_names.add(name.strip())

        out: list[Any] = list(apps)
        for host, names in sorted(tech_map.items()):
            for name in sorted(names):
                out.append(AssetTechnologyObservation(host=host, technology=name))
        return out

    # -- execution -----------------------------------------------------------

    def execute(
        self,
        task: Any,
        runner: Any,
        config: Any,
        scope: ScopeGuard,
    ) -> Any:
        """Probe via the controlled Tool Runner (scope-checked redirects)."""
        from core.tool_runner import ToolUnavailableError
        from recon.base import ToolExecution

        if not self.is_available():
            raise ToolUnavailableError(
                f"httpx: none of {self.executables} found on PATH; skipping "
                "HTTP probing"
            )
        self.validate(task, scope)
        command = self.build_command(task, config)
        result = runner.run_command(command, tool=self.name)
        raw_ref = runner.save_raw(
            self.name, result.stdout, extension="ndjson", tag="probe"
        )
        artifacts = self.parse(result)
        return ToolExecution(
            tool=self.name,
            command=command,
            exit_code=result.exit_code,
            raw_output_ref=raw_ref,
            artifacts=artifacts,
            timed_out=result.timed_out,
        )


def _follow_redirects(config: Any) -> bool:
    """Whether redirect following is enabled in the current configuration."""
    web = getattr(getattr(config, "recon", None), "web", None)
    return bool(getattr(web, "follow_redirects", False))
