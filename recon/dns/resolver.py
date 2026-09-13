"""DNS Resolver adapter (``06_TOOL_CONTRACTS.md`` §DNS Resolver).

**In-process** adapter: resolves an in-scope hostname to canonical DNS records
through a DNS library call (dnspython), **not** a shelled binary. Per
``06_TOOL_CONTRACTS.md`` §DNS Resolver:

- **Command construction:** internal resolver call (a DNS library call),
  never a shelled binary or shell string
- **Record types:** A / AAAA / CNAME / MX / NS / TXT
- **Scope requirements:** hostname already validated as in-scope (scope is
  always confirmed before resolution; ``04_SCOPE_SAFETY.md`` §When Scope Must
  Be Re-Checked)
- **Output format:** structured ``ResolutionResult``, serialized to JSON
- **Parser:** structured records -> normalized records (document order kept,
  duplicate ``(record_type, value)`` pairs collapsed)
- **Normalized objects:** ``dns_records``, ``ips``, ``asset_ips`` (A/AAAA
  values surface as IP observations for the Normalizer, ``05_DATA_MODEL.md``)
- **Raw output:** preserved under ``storage/raw/dns/`` (the serialized
  resolution result), via the controlled Tool Runner
- **Errors:** NXDOMAIN / timeout / server errors are recorded per record type
  and are **not fatal** to the run; partial output is still returned
- **Timeouts:** short per-query lifetime, never blocking the whole run
- **Tests:** fixture parse tests, including an NXDOMAIN case and a
  partial-timeout case (``tests/fixtures/dns/``; ``13_TESTING_STRATEGY.md``)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import dns.exception
import dns.resolver

from core.scope_guard import ScopeGuard
from core.tool_runner import CommandResult, ToolRunner, ToolUnavailableError
from recon.base import ToolAdapter, ToolExecution, extract_host

log = logging.getLogger("argus.recon.dns")

#: Record types the adapter queries, matching the ``dns_records`` ``record_type``
#: CHECK constraint (`05_DATA_MODEL.md` §dns_records).
RECORD_TYPES: tuple[str, ...] = ("A", "AAAA", "CNAME", "MX", "NS", "TXT")

#: Record types whose values are IP addresses (feed ``ips`` + ``asset_ips``).
IP_RECORD_TYPES: frozenset[str] = frozenset({"A", "AAAA"})


# -- canonical observations -------------------------------------------------


@dataclass(frozen=True)
class DnsRecordObservation:
    """One normalized DNS record (``dns_records`` row)."""

    hostname: str
    record_type: str
    value: str


@dataclass(frozen=True)
class IpObservation:
    """An IP address surface from an A/AAAA record (``ips`` + ``asset_ips``)."""

    address: str
    record_type: str


# -- resolution result ------------------------------------------------------


@dataclass(frozen=True)
class ResolutionResult:
    """Structured outcome of resolving one hostname (serializable to JSON)."""

    hostname: str
    resolved_at: str  # ISO-8601 UTC
    records: tuple[tuple[str, str], ...] = ()  # (record_type, value) pairs
    errors: dict[str, str] = field(default_factory=dict)  # record_type -> NXDOMAIN/timeout/...

    def to_json(self) -> str:
        """Serialize to stable, canonical JSON (the preserved raw output)."""
        return json.dumps(
            {
                "hostname": self.hostname,
                "resolved_at": self.resolved_at,
                "records": [
                    {"record_type": rt, "value": value} for rt, value in self.records
                ],
                "errors": self.errors,
            },
            sort_keys=True,
            indent=2,
        )


def hostname_from_fixture(data: dict) -> str:
    """Extract the resolved hostname from a DNS fixture (tolerates variations)."""
    return str(
        data.get("hostname")
        or data.get("host")
        or data.get("resolved_from")
        or ""
    ).strip().lower().rstrip(".")


def parse_resolution(data: dict) -> tuple[DnsRecordObservation, ...]:
    """Parse a structured resolution dict into canonical DNS record objects.

    ``NXDOMAIN``/``timeout`` entries are carried in ``errors`` and yield no
    records; they are never fatal (`13_TESTING_STRATEGY.md` §Adapter Fixture
    Tests). Duplicate ``(record_type, value)`` pairs are collapsed; hostnames
    default to the resolution's hostname field.
    """
    hostname = hostname_from_fixture(data)
    seen: set[tuple[str, str]] = set()
    out: list[DnsRecordObservation] = []
    for record in data.get("records") or ():
        if not isinstance(record, dict):
            continue
        record_type = str(record.get("record_type") or "")
        value = record.get("value")
        if not isinstance(value, str) or not value.strip() or not record_type:
            continue
        key = (record_type.upper(), value.strip())
        if key in seen:
            continue
        seen.add(key)
        out.append(
            DnsRecordObservation(
                hostname=hostname,
                record_type=record_type.upper(),
                value=value.strip(),
            )
        )
    return tuple(out)


def ip_observations(records: tuple[DnsRecordObservation, ...]) -> tuple[IpObservation, ...]:
    """Derive IP observations from A/AAAA records (deduplicated, insertion order)."""
    seen: set[str] = set()
    out: list[IpObservation] = []
    for record in records:
        if record.record_type not in IP_RECORD_TYPES:
            continue
        address = record.value.strip()
        if not address or address in seen:
            continue
        seen.add(address)
        out.append(IpObservation(address=address, record_type=record.record_type))
    return tuple(out)


# -- resolver seam ----------------------------------------------------------

#: ``(hostname, record_type) -> (values, error)``; alive for deterministic tests.
ResolverFn = Callable[[str, str], tuple[tuple[str, ...], Optional[str]]]


def make_resolver(
    *,
    timeout: Optional[float] = 3.0,
    resolver: Optional[Any] = None,
) -> ResolverFn:
    """Build a ``(hostname, record_type) -> (values, error)`` callable.

    Values are strings; ``error`` is ``None`` on success or one of
    ``NXDOMAIN`` / ``NOANSWER`` / ``TIMEOUT`` / ``SERVER`` otherwise. This is
    the seam the adapter shells through so fixture-based tests never touch a
    live resolver.
    """
    res = resolver or dns.resolver.Resolver()
    effective_timeout = float(timeout or 3.0)

    def _resolve(hostname: str, record_type: str) -> tuple[tuple[str, ...], Optional[str]]:
        try:
            answers = res.resolve(
                hostname,
                record_type,
                lifetime=effective_timeout,
                raise_on_no_answer=False,
            )
        except dns.resolver.NXDOMAIN:
            return (), "NXDOMAIN"
        except dns.resolver.NoAnswer:
            return (), "NOANSWER"
        except dns.resolver.NoNameservers as exc:
            return (), f"SERVER:{getattr(exc, 'response', None) or 'no-nameservers'}"
        except dns.exception.FormError:
            return (), "FORMERR"
        except dns.exception.Timeout:
            return (), "TIMEOUT"
        except Exception:
            log.exception("dns: unexpected error resolving %s %s", hostname, record_type)
            return (), "ERROR"
        values = []
        for rdata in answers:
            text = rdata.to_text()
            if record_type == "TXT":
                # Strip surrounding quotes from TXT character-strings for a
                # stable normalized value (`05_DATA_MODEL.md` §dns_records).
                text = text.strip().strip('"')
            values.append(text)
        return tuple(values), None

    return _resolve


# -- adapter -----------------------------------------------------------------


class DnsResolverAdapter(ToolAdapter):
    """In-process DNS resolver adapter (never shells out)."""

    name = "dns"
    #: No external binary: this adapter is an in-process DNS library call.
    executables: tuple[str, ...] = ()

    def __init__(
        self,
        *,
        resolver_fn: Optional[ResolverFn] = None,
        timeout: float = 3.0,
    ) -> None:
        super().__init__()
        self._resolver_fn = resolver_fn or make_resolver(timeout=timeout)
        self.timeout = float(timeout)

    # -- availability -------------------------------------------------------

    def is_available(self) -> bool:
        return True  # in-process; dnspython is a declared dependency

    # -- scope ---------------------------------------------------------------

    def validate(self, task: Any, scope: ScopeGuard) -> None:
        self._require_in_scope(extract_host(getattr(task, "target", "")), scope)

    # -- command ------------------------------------------------------------

    def build_command(self, task: Any, config: Any) -> list[str]:
        """Diagnostic marker for the in-process call (never executed)."""
        host = extract_host(getattr(task, "target", ""))
        return ["dns-resolve", host]

    # -- parse ----------------------------------------------------------------

    def parse(self, result: CommandResult) -> list[Any]:
        """Structured resolution JSON -> canonical record/IP observations.

        ``result.stdout`` holds the serialized :class:`ResolutionResult` (the
        recorded fixture content). Empty/malformed output yields no artifacts
        without raising (`13_TESTING_STRATEGY.md` §Adapter Fixture Tests).
        """
        try:
            data = json.loads(result.stdout or "null")
        except ValueError:
            log.warning("dns: parse: output is not valid JSON; no records recovered")
            return []
        if not isinstance(data, dict):
            return []
        records = parse_resolution(data)
        return [*records, *ip_observations(records)]

    # -- execute ---------------------------------------------------------------

    def execute(
        self,
        task: Any,
        runner: ToolRunner,
        config: Any,
        scope: ScopeGuard,
    ) -> ToolExecution:
        """Resolve ``task.target`` in-process through the DNS library.

        Scope is validated before any resolution; NXDOMAIN/timeout per record
        type are recorded (not fatal); the structured resolution is preserved
        as raw output through the controlled Tool Runner; artifacts are the
        canonical normalized observations.
        """
        if not self.is_available():
            raise ToolUnavailableError(
                f"{self.name}: dnspython unavailable; skipping this discovery source"
            )
        self.validate(task, scope)
        host = extract_host(getattr(task, "target", ""))
        if not host:
            raise ValueError(f"dns: task.target must be a hostname, got {getattr(task, 'target', '')!r}")

        records: list[tuple[str, str]] = []
        errors: dict[str, str] = {}
        for record_type in RECORD_TYPES:
            values, error = self._resolver_fn(host, record_type)
            if error:
                errors[record_type] = error
                continue
            for value in values:
                records.append((record_type, value))

        result = ResolutionResult(
            hostname=host,
            resolved_at=_utcnow(),
            records=tuple(records),
            errors=errors,
        )
        raw_ref = runner.save_raw(
            "dns",
            result.to_json(),
            extension="json",
            tag="resolution",
        )
        artifacts = tuple(self.parse(CommandResult(tool=self.name, command=[], stdout=result.to_json())))
        return ToolExecution(
            tool=self.name,
            command=["dns-resolve", host],
            exit_code=0,
            raw_output_ref=raw_ref,
            artifacts=artifacts,
        )


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
