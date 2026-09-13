# ARGUS First Milestone

Tells the implementer (human or AI coding agent) exactly what to build first. **Do not start
with AI.** The first milestone is deliberately, entirely deterministic.

## Milestone 1 Flow

```text
CLI
 ↓
Target + Scope
 ↓
Scope Validation
 ↓
Create Run
 ↓
Subdomain Discovery
 ↓
Parse
 ↓
Normalize
 ↓
PostgreSQL
 ↓
DNS
 ↓
PostgreSQL
 ↓
HTTP Probe
 ↓
PostgreSQL
 ↓
JSON Summary
```

## Supported Environment

Milestone 1 targets **Linux/Unix**. Specifically: 64-bit Linux (Debian/Ubuntu-class or
equivalent), Python 3.10+, and PostgreSQL (local or containerized).

**Why Linux first:**

- Every external recon tool in the initial adapter set (Subfinder, Amass, Assetfinder, Nmap,
  httpx, Katana) is Linux/Unix-first software; several have no reliable Windows distribution.
- The reference deployment posture (Linux host + PostgreSQL) matches the documented tool
  contracts (`06_TOOL_CONTRACTS.md`) and the controlled-lab integration environment
  (`13_TESTING_STRATEGY.md` §Integration Tests).
- Contrast: forcing Windows installs of Nmap, Amass, and Python bindings across CI and dev
  machines adds cross-platform surface area for zero Milestone-1 benefit.

**Windows compatibility is a future hardening phase** (`10_IMPLEMENTATION_PLAN.md` Phase 12),
not a Milestone-1 goal. It will not be block-able by Linux-only code paths in Milestone 1.

**Tool execution remains platform-neutral by design.** The Tool Runner
(`06_TOOL_CONTRACTS.md` §Tool Runner) executes every command as an argument array via
`subprocess.run(..., shell=False)`, never as a shell string. Adapters discover executables via
PATH, build argument arrays, and normalize output — a contract that does not depend on the host
OS. Windows support therefore requires running and testing the same adapters on Windows CI, not
rewriting the adapter/runner abstraction.

## Implement First

- Repository bootstrap
- Typed configuration (`core/config.py`)
- Scope Guard (`core/scope_guard.py`)
- Rate Limiter (`core/rate_limiter.py`)
- Tool Runner (safe `subprocess` execution, `shell=False`)
- PostgreSQL setup / migrations
- Run model and Task model (`runs` → `tasks` → `tool_runs`; see `05_DATA_MODEL.md`)
- Subfinder adapter
- DNS resolver adapter
- httpx adapter
- Normalization (asset dedup, e.g. `www.example.com` vs `WWW.example.com.`)
- Structured logging
- Tests
- JSON summary generator

## Explicitly Exclude From Milestone 1

- AI (no agents, no local/cloud model integration)
- Dashboard
- Adaptive reasoning / the adaptive recon loop
- Autonomous exploitation
- Credential attacks
- Destructive testing
- Complex attack-path reasoning

This exclusion list matches `10_IMPLEMENTATION_PLAN.md` Phases 6+; those phases only begin once
Milestone 1's acceptance criteria are met.

## Acceptance Criteria

Milestone 1 is complete only when all of the following hold:

- **Scope** — out-of-scope targets are rejected by the Scope Guard, including out-of-scope
  redirect/discovery destinations (per `04_SCOPE_SAFETY.md` §Redirect and Discovered-Target
  Policy)
- **Command safety** — commands execute through safe argument arrays, never shell strings
- **Raw output** — tool output is preserved under `storage/raw/`
- **Database** — normalized assets persist into PostgreSQL matching `05_DATA_MODEL.md`
- **Run/Task** — a `runs` record is created at intake; tasks are linked to it via
  `tasks.run_id`, and tool runs to tasks via `tool_runs.task_id`
- **DNS** — DNS results persist as structured `dns_records`
- **HTTP** — HTTP probe results persist as `web_apps`
- **Resumability** — a run can recover from interruption without data loss or duplicate work
- **Tests** — core safety and functionality tests pass
- **JSON** — a valid, reproducible JSON summary is generated for the run

## Why This Sequencing

The project must first prove it can **safely and reliably collect reality** — deterministic,
scope-controlled, resumable, evidence-preserving reconnaissance — before attempting to build an
AI layer that reasons about that reality. See `01_PRODUCT_SPEC.md` §Non-Goals and
`OPENCODE.md` for why this order is non-negotiable.
