# ARGUS Configuration Reference

Canonical configuration example. This is conceptual and will evolve during implementation, but
every option below must be explained wherever it appears in code.

```yaml
project:
  name: ARGUS

database:
  url: ...                     # PostgreSQL connection string; never commit real credentials

scope:
  allowed_domains:
    - example.com
  allowed_ips: []               # CIDR/IP entries allowed for active recon
  excluded:
    - internal-staging.example.com

recon:
  aggressive_subdomain_discovery: true

network:
  tcp_ports:
    start: 1
    end: 1000

web:
  http_probe: true
  crawling: true
  content_discovery: true
  historical_urls: true

javascript:
  deep_analysis: true
  source_maps: true

api:
  rest: true
  openapi: true
  swagger: true
  graphql: true
  websocket: true
  authentication_analysis: true

ai:
  mode: hybrid                 # local | cloud | hybrid
  local_model: ...
  cloud_model: ...

limits:
  requests_per_second: ...
  concurrency: ...

outputs:
  json: true
  markdown: true
  html: true
```

## Option Reference

| Section | Option | Meaning |
|---|---|---|
| `project` | `name` | Project/run label used in reports and logs |
| `database` | `url` | PostgreSQL connection string (via environment variable, never committed) |
| `scope` | `allowed_domains` | Root domains the Scope Guard treats as in-scope |
| `scope` | `allowed_ips` | CIDR/IP ranges authorized for active recon |
| `scope` | `excluded` | Explicit exclusions checked even if a domain matches an allowed pattern |
| `recon` | `aggressive_subdomain_discovery` | Enables broader (slower) subdomain enumeration sources |
| `network.tcp_ports` | `start` / `end` | Authorized TCP port scan range (default `1–1000`) |
| `web` | `http_probe` / `crawling` / `content_discovery` / `historical_urls` | Toggle each web-recon stage independently |
| `javascript` | `deep_analysis` / `source_maps` | Toggle JS extraction and source-map analysis |
| `api` | `rest` / `openapi` / `swagger` / `graphql` / `websocket` / `authentication_analysis` | Toggle each API-recon capability independently |
| `ai` | `mode` | Force `local`, force `cloud`, or let the router choose (`hybrid`) |
| `ai` | `local_model` / `cloud_model` | Model identifiers used by `ai/router.py` |
| `limits` | `requests_per_second` / `concurrency` | Global Rate Limiter defaults (per-program overrides may still apply) |
| `outputs` | `json` / `markdown` / `html` | Toggle which report formats are generated |

## Secrets

Secrets (database credentials, cloud model API keys, etc.) must never be committed to Git. Use
environment variables or a secure secrets mechanism, and reference them by name in this
configuration file rather than by value.
