"""Configuration tests: parsing, validation, defaults, env-var secrets override."""

import os
from pathlib import Path

import pytest

from core.config import AiMode, Config, ConfigError, LimitsConfig, TcpPortRange

MINIMAL_YAML = """
database:
  url: postgresql://user:pass@localhost:5432/argus
scope:
  allowed_domains:
    - example.com
  allowed_ips:
    - 203.0.113.0/24
  excluded:
    - internal-staging.example.com
"""


def write_config(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_minimal_config(tmp_path: Path) -> None:
    cfg = Config.load(write_config(tmp_path, MINIMAL_YAML))
    assert cfg.project.name == "ARGUS"
    assert cfg.database.url.startswith("postgresql://")
    assert cfg.scope.allowed_domains == ("example.com",)
    assert cfg.scope.allowed_ips == ("203.0.113.0/24",)
    assert cfg.scope.excluded == ("internal-staging.example.com",)
    assert cfg.limits == LimitsConfig()
    assert cfg.network.tcp_ports == TcpPortRange()
    assert cfg.ai.mode is AiMode.HYBRID


def test_full_config_matches_example(tmp_path: Path) -> None:
    text = """
project:
  name: ARGUS
database:
  url: postgresql://u:p@localhost:5432/argus
scope:
  allowed_domains: [example.com, test.net]
  allowed_ips: []
  excluded: []
recon:
  aggressive_subdomain_discovery: false
network:
  tcp_ports: {start: 1, end: 1000}
web:
  http_probe: true
  crawling: false
  content_discovery: true
  historical_urls: false
javascript:
  deep_analysis: true
  source_maps: false
api:
  rest: true
  openapi: false
  swagger: false
  graphql: true
  websocket: false
  authentication_analysis: false
ai:
  mode: local
  local_model: llama3
  cloud_model: gpt-4o
limits:
  requests_per_second: 20
  concurrency: 8
outputs:
  json: true
  markdown: false
  html: false
"""
    cfg = Config.load(write_config(tmp_path, text))
    assert cfg.recon.aggressive_subdomain_discovery is False
    assert cfg.web.crawling is False
    assert cfg.web.http_probe is True
    assert cfg.javascript.source_maps is False
    assert cfg.api.authentication_analysis is False
    assert cfg.ai.mode is AiMode.LOCAL
    assert cfg.ai.local_model == "llama3"
    assert cfg.limits.requests_per_second == pytest.approx(20.0)
    assert cfg.limits.concurrency == 8
    assert cfg.outputs.markdown is False
    assert cfg.outputs.json is True


def test_database_url_required(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="database.url"):
        Config.load(write_config(tmp_path, "scope:\n  allowed_domains: [example.com]\n"))


def test_env_var_overrides_database_url(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ARGUS_DATABASE_URL", "postgresql://env:secret@db:5432/argus")
    cfg = Config.load(write_config(tmp_path, "database:\n  url: postgresql://bad\n"))
    assert cfg.database.url == "postgresql://env:secret@db:5432/argus"


def test_invalid_cidr_rejected(tmp_path: Path) -> None:
    text = """
database:
  url: postgresql://u:p@localhost:5432/argus
scope:
  allowed_ips: [not-an-ip]
"""
    with pytest.raises(ConfigError, match="allowed_ips"):
        Config.load(write_config(tmp_path, text))


def test_invalid_ai_mode_rejected(tmp_path: Path) -> None:
    text = """
database:
  url: postgresql://u:p@localhost:5432/argus
ai:
  mode: turbo
"""
    with pytest.raises(ConfigError, match="ai.mode"):
        Config.load(write_config(tmp_path, text))


def test_invalid_port_range_rejected(tmp_path: Path) -> None:
    text = """
database:
  url: postgresql://u:p@localhost:5432/argus
network:
  tcp_ports: {start: 70000, end: 5}
"""
    with pytest.raises(ConfigError, match="tcp_ports"):
        Config.load(write_config(tmp_path, text))


def test_invalid_limits_rejected(tmp_path: Path) -> None:
    text = """
database:
  url: postgresql://u:p@localhost:5432/argus
limits:
  concurrency: 0
"""
    with pytest.raises(ConfigError, match="concurrency"):
        Config.load(write_config(tmp_path, text))


def test_to_dict_roundtrip_is_json_safe(tmp_path: Path) -> None:
    cfg = Config.load(write_config(tmp_path, MINIMAL_YAML))
    import json

    payload = json.dumps(cfg.to_dict())
    assert "example.com" in payload
    assert '"url"' in payload


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="cannot read"):
        Config.load(tmp_path / "nope.yaml")


def test_invalid_yaml_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="invalid YAML"):
        Config.load(write_config(tmp_path, "database: [unclosed\n"))