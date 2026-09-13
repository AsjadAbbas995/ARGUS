"""Typed configuration for ARGUS.

Mirrors ``docs/14_CONFIG_EXAMPLE.md``. Loaded from YAML, validated
deterministically, and serializable back to a plain dict so that intake can
persist the ``configuration_snapshot`` on the ``runs`` record
(``05_DATA_MODEL.md``).

Security rule from ``14_CONFIG_EXAMPLE.md`` §Secrets: secrets such as
``database.url`` may be supplied via environment variables instead of the
committed file.
"""

from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Raised when configuration is invalid."""


class AiMode(str, Enum):
    LOCAL = "local"
    CLOUD = "cloud"
    HYBRID = "hybrid"


class RuleType(str, Enum):
    """Scope rule types matching ``scope_rules.rule_type`` in ``05_DATA_MODEL.md``."""

    DOMAIN = "domain"
    SUBDOMAIN = "subdomain"
    IP = "ip"
    CIDR = "cidr"
    EXCLUSION = "exclusion"


def _require_non_empty(value: Any, path: str) -> None:
    if value in (None, ""):
        raise ConfigError(f"config.{path} must be provided")


def _require_positive(value: Any, path: str) -> None:
    if not isinstance(value, (int, float)) or value <= 0:
        raise ConfigError(f"config.{path} must be a number > 0")


def _validate_rule_value(value: Any, rule_type: RuleType, path: str) -> None:
    _require_non_empty(value, path)
    if not isinstance(value, str):
        raise ConfigError(f"config.{path} must be a string")
    lowered = value.lower().rstrip(".")
    if rule_type in (RuleType.IP, RuleType.CIDR):
        try:
            ipaddress.ip_network(value, strict=False)
        except ValueError as exc:  # pragma: no cover - exercised via ConfigError
            raise ConfigError(f"config.{path} is not a valid IP/CIDR: {value!r}") from exc
    return None


@dataclass(frozen=True)
class ProjectConfig:
    name: str = "ARGUS"

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ProjectConfig":
        data = data or {}
        name = data.get("name", "ARGUS")
        _require_non_empty(name, "project.name")
        return cls(name=str(name))


@dataclass(frozen=True)
class DatabaseConfig:
    url: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "DatabaseConfig":
        data = data or {}
        url = str(data.get("url", "") or "")
        env_url = os.environ.get("ARGUS_DATABASE_URL")
        if env_url:
            url = env_url
        if not url:
            raise ConfigError(
                "config.database.url is required (or set ARGUS_DATABASE_URL); "
                "never commit real credentials"
            )
        return cls(url=url)


@dataclass(frozen=True)
class ScopeConfig:
    allowed_domains: tuple[str, ...] = ()
    allowed_ips: tuple[str, ...] = ()
    excluded: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ScopeConfig":
        data = data or {}
        allowed_domains = tuple(data.get("allowed_domains") or ())
        allowed_ips = tuple(data.get("allowed_ips") or ())
        excluded = tuple(data.get("excluded") or ())
        for entry in allowed_domains:
            _validate_rule_value(entry, RuleType.DOMAIN, "scope.allowed_domains")
        for entry in allowed_ips:
            _validate_rule_value(entry, RuleType.CIDR, "scope.allowed_ips")
        for entry in excluded:
            _validate_rule_value(entry, RuleType.EXCLUSION, "scope.excluded")
        return cls(
            allowed_domains=allowed_domains,
            allowed_ips=allowed_ips,
            excluded=excluded,
        )


@dataclass(frozen=True)
class TcpPortRange:
    start: int = 1
    end: int = 1000

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "TcpPortRange":
        data = data or {}
        start = int(data.get("start", 1))
        end = int(data.get("end", 1000))
        if start < 1 or end > 65535 or start > end:
            raise ConfigError(
                f"config.network.tcp_ports must satisfy 1 <= start <= end <= 65535 "
                f"(got {start}..{end})"
            )
        return cls(start=start, end=end)


@dataclass(frozen=True)
class NetworkConfig:
    tcp_ports: TcpPortRange = field(default_factory=TcpPortRange)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "NetworkConfig":
        data = data or {}
        return cls(tcp_ports=TcpPortRange.from_dict(data.get("tcp_ports")))


@dataclass(frozen=True)
class ReconConfig:
    aggressive_subdomain_discovery: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ReconConfig":
        data = data or {}
        return cls(
            aggressive_subdomain_discovery=bool(
                data.get("aggressive_subdomain_discovery", True)
            )
        )


@dataclass(frozen=True)
class WebConfig:
    http_probe: bool = True
    crawling: bool = True
    content_discovery: bool = True
    historical_urls: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "WebConfig":
        data = data or {}
        return cls(
            http_probe=bool(data.get("http_probe", True)),
            crawling=bool(data.get("crawling", True)),
            content_discovery=bool(data.get("content_discovery", True)),
            historical_urls=bool(data.get("historical_urls", True)),
        )


@dataclass(frozen=True)
class JavascriptConfig:
    deep_analysis: bool = True
    source_maps: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "JavascriptConfig":
        data = data or {}
        return cls(
            deep_analysis=bool(data.get("deep_analysis", True)),
            source_maps=bool(data.get("source_maps", True)),
        )


@dataclass(frozen=True)
class ApiConfig:
    rest: bool = True
    openapi: bool = True
    swagger: bool = True
    graphql: bool = True
    websocket: bool = True
    authentication_analysis: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ApiConfig":
        data = data or {}
        return cls(
            rest=bool(data.get("rest", True)),
            openapi=bool(data.get("openapi", True)),
            swagger=bool(data.get("swagger", True)),
            graphql=bool(data.get("graphql", True)),
            websocket=bool(data.get("websocket", True)),
            authentication_analysis=bool(data.get("authentication_analysis", True)),
        )


@dataclass(frozen=True)
class AiConfig:
    mode: AiMode = AiMode.HYBRID
    local_model: str = ""
    cloud_model: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "AiConfig":
        data = data or {}
        mode_raw = str(data.get("mode", "hybrid")).lower()
        try:
            mode = AiMode(mode_raw)
        except ValueError as exc:
            raise ConfigError(
                f"config.ai.mode must be one of "
                f"{', '.join(m.value for m in AiMode)} (got {mode_raw!r})"
            ) from exc
        return cls(
            mode=mode,
            local_model=str(data.get("local_model") or ""),
            cloud_model=str(data.get("cloud_model") or ""),
        )


@dataclass(frozen=True)
class LimitsConfig:
    requests_per_second: float = 10.0
    concurrency: int = 5

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "LimitsConfig":
        data = data or {}
        rps = data.get("requests_per_second", 10.0)
        concurrency = data.get("concurrency", 5)
        _require_positive(rps, "limits.requests_per_second")
        _require_positive(concurrency, "limits.concurrency")
        return cls(requests_per_second=float(rps), concurrency=int(concurrency))


@dataclass(frozen=True)
class OutputsConfig:
    json: bool = True
    markdown: bool = True
    html: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "OutputsConfig":
        data = data or {}
        return cls(
            json=bool(data.get("json", True)),
            markdown=bool(data.get("markdown", True)),
            html=bool(data.get("html", True)),
        )


@dataclass(frozen=True)
class StorageConfig:
    root: Path = Path("storage")
    raw_dir: Path = Path("storage/raw")
    evidence_dir: Path = Path("storage/evidence")
    reports_dir: Path = Path("storage/reports")

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "StorageConfig":
        data = data or {}
        root = Path(str(data.get("root") or "storage"))
        raw = data.get("raw", "raw")
        evidence = data.get("evidence", "evidence")
        reports = data.get("reports", "reports")
        return cls(
            root=root,
            raw_dir=root / str(raw),
            evidence_dir=root / str(evidence),
            reports_dir=root / str(reports),
        )


@dataclass(frozen=True)
class Config:
    project: ProjectConfig = field(default_factory=ProjectConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    scope: ScopeConfig = field(default_factory=ScopeConfig)
    recon: ReconConfig = field(default_factory=ReconConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    web: WebConfig = field(default_factory=WebConfig)
    javascript: JavascriptConfig = field(default_factory=JavascriptConfig)
    api: ApiConfig = field(default_factory=ApiConfig)
    ai: AiConfig = field(default_factory=AiConfig)
    limits: LimitsConfig = field(default_factory=LimitsConfig)
    outputs: OutputsConfig = field(default_factory=OutputsConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        return cls(
            project=ProjectConfig.from_dict(data.get("project")),
            database=DatabaseConfig.from_dict(data.get("database")),
            scope=ScopeConfig.from_dict(data.get("scope")),
            recon=ReconConfig.from_dict(data.get("recon")),
            network=NetworkConfig.from_dict(data.get("network")),
            web=WebConfig.from_dict(data.get("web")),
            javascript=JavascriptConfig.from_dict(data.get("javascript")),
            api=ApiConfig.from_dict(data.get("api")),
            ai=AiConfig.from_dict(data.get("ai")),
            limits=LimitsConfig.from_dict(data.get("limits")),
            outputs=OutputsConfig.from_dict(data.get("outputs")),
            storage=StorageConfig.from_dict(data.get("storage")),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serializable snapshot for persistence (``runs.configuration_snapshot``)."""
        return {
            "project": {"name": self.project.name},
            "database": {"url": self.database.url},
            "scope": {
                "allowed_domains": list(self.scope.allowed_domains),
                "allowed_ips": list(self.scope.allowed_ips),
                "excluded": list(self.scope.excluded),
            },
            "recon": {
                "aggressive_subdomain_discovery": self.recon.aggressive_subdomain_discovery,
            },
            "network": {
                "tcp_ports": {
                    "start": self.network.tcp_ports.start,
                    "end": self.network.tcp_ports.end,
                }
            },
            "web": {
                "http_probe": self.web.http_probe,
                "crawling": self.web.crawling,
                "content_discovery": self.web.content_discovery,
                "historical_urls": self.web.historical_urls,
            },
            "javascript": {
                "deep_analysis": self.javascript.deep_analysis,
                "source_maps": self.javascript.source_maps,
            },
            "api": {
                "rest": self.api.rest,
                "openapi": self.api.openapi,
                "swagger": self.api.swagger,
                "graphql": self.api.graphql,
                "websocket": self.api.websocket,
                "authentication_analysis": self.api.authentication_analysis,
            },
            "ai": {
                "mode": self.ai.mode.value,
                "local_model": self.ai.local_model,
                "cloud_model": self.ai.cloud_model,
            },
            "limits": {
                "requests_per_second": self.limits.requests_per_second,
                "concurrency": self.limits.concurrency,
            },
            "outputs": {
                "json": self.outputs.json,
                "markdown": self.outputs.markdown,
                "html": self.outputs.html,
            },
            "storage": {
                "root": str(self.storage.root),
                "raw": str(self.storage.raw_dir),
                "evidence": str(self.storage.evidence_dir),
                "reports": str(self.storage.reports_dir),
            },
        }

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        """Load and validate a YAML configuration file."""
        config_path = Path(path)
        try:
            with config_path.open("r", encoding="utf-8") as handle:
                data = yaml.safe_load(handle)
        except OSError as exc:
            raise ConfigError(f"cannot read config file {config_path}: {exc}") from exc
        except yaml.YAMLError as exc:
            raise ConfigError(f"invalid YAML in {config_path}: {exc}") from exc
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise ConfigError(f"config root in {config_path} must be a mapping")
        return cls.from_dict(data)


def load_config(path: str | Path) -> Config:
    """Backwards-compatible entry point; forwards to :meth:`Config.load`."""
    return Config.load(path)