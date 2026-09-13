# ARGUS Implementation Plan

Complete phase-by-phase roadmap. Milestone 1 (`15_FIRST_MILESTONE.md`) is the single
authoritative definition of the deterministic-first slice — it reaches into Phases 0–5 and
Phase 9 (core config, scope/rate limiting, database, initial adapters, normalization,
run/task lifecycle, JSON summary) but contains **no AI**. The milestone is the definitive
pre-requisite; each phase below is documented as: **Objectives, Dependencies, Files to
Implement, Features, Tests, Acceptance Criteria, Known Risks, Definition of Done.**

---

## Phase 0 — Repository Bootstrap

**Objectives:** Establish the project skeleton so all later work has a consistent home.
**Dependencies:** None. **Files to implement:** top-level package layout (`core/`, `recon/`,
`intelligence/`, `ai/`, `correlation/`, `evidence/`, `database/`, `reports/`, `api/`,
`dashboard/`, `storage/`, `tests/`), `core/config.py` skeleton, dependency manifest, logging
setup. **Features:** project structure, dependency management, structured logging, testing
foundation. **Tests:** smoke test that the package imports cleanly. **Acceptance criteria:**
repo installs and runs a no-op CLI command. **Known risks:** premature structure decisions that
don't match later phases — keep this phase minimal. **Definition of done:** clean checkout →
install → run → exit 0, with logging configured.

## Phase 1 — Core Infrastructure

**Objectives:** Build the deterministic safety/control primitives everything else depends on.
**Dependencies:** Phase 0. **Files to implement:** `core/scope_guard.py`, `core/rate_limiter.py`,
`core/scheduler.py` (basics). **Features:** scope validation, rate limiting, minimal scheduling.
**Tests:** scope accept/reject unit tests, rate-limit unit tests. **Acceptance criteria:**
out-of-scope targets are deterministically rejected; rate limiter enforces configured limits in
isolation tests. **Known risks:** under-specified scope rules leading to false negatives.
**Definition of done:** Scope Guard and Rate Limiter pass their full unit-test suite
(`13_TESTING_STRATEGY.md` §Scope Tests).

## Phase 2 — Database

**Objectives:** Stand up PostgreSQL as the authoritative store. **Dependencies:** Phase 0.
**Files to implement:** `database/models/`, `database/migrations/`, `database/repositories/`.
**Features:** all entities from `05_DATA_MODEL.md`, run/task/evidence structures.
**Tests:** migration tests, insert/relationship tests, deduplication constraint tests.
**Acceptance criteria:** schema matches `05_DATA_MODEL.md`; migrations apply/rollback cleanly.
**Known risks:** schema drift from the documented data model. **Definition of done:** a fresh
database migrates cleanly and every table in `05_DATA_MODEL.md` exists with its documented keys
and constraints.

## Phase 3 — Recon Adapters

**Objectives:** Implement the initial tool adapters. **Dependencies:** Phases 1–2.
**Files to implement:** `recon/subdomains/*.py`, `recon/dns/resolver.py`,
`recon/network/*.py`, `recon/web/*.py`, `recon/historical/*.py`. **Features:** Subfinder, Amass,
Assetfinder, DNS resolver, Nmap, httpx, Katana, GAU, Wayback, FFUF, Feroxbuster — per
`06_TOOL_CONTRACTS.md`. **Tests:** fixture-based parser tests per adapter. **Acceptance
criteria:** each adapter parses its fixture output into correct normalized objects; missing
binaries degrade gracefully. **Known risks:** tool output format drift between versions.
**Definition of done:** all initial adapters pass fixture tests and integrate with the Tool
Runner from Phase 1.

## Phase 4 — Normalization

**Objectives:** Canonical models for cross-tool normalized data. **Dependencies:** Phases 2–3.
**Files to implement:** normalization logic within `recon/**` parsers and shared normalization
helpers. **Features:** canonical models for assets, URLs, endpoints, parameters, technologies,
IPs, ports, services, with deduplication (e.g. `www.example.com` vs
`WWW.example.com.`). **Tests:** deduplication unit tests, normalization edge-case tests.
**Acceptance criteria:** duplicate variants of the same asset collapse to one row. **Known
risks:** over-aggressive normalization merging genuinely distinct assets. **Definition of done:**
normalization test suite passes for all documented edge cases.

## Phase 5 — Initial Orchestrator

**Objectives:** Run/task lifecycle without AI. **Dependencies:** Phases 1–4.
**Files to implement:** `core/orchestrator.py`, `core/task_planner.py` (deterministic ordering
only at this phase). **Features:** run lifecycle, task lifecycle, scheduling, dependencies,
checkpoints, resumability. **Tests:** state-transition tests, resumability-after-crash tests.
**Acceptance criteria:** a simulated crash mid-run resumes without duplicate or lost tasks.
**Known risks:** race conditions in checkpointing. **Definition of done:** orchestrator passes
the full `08_ORCHESTRATOR.md` state-machine test suite.

## Phase 6 — AI Layer

**Objectives:** Local/cloud model integration and routing. **Dependencies:** Phase 5.
**Files to implement:** `ai/local_model.py`, `ai/cloud_model.py`, `ai/router.py`.
**Features:** hybrid routing per `07_AI_AGENTS.md`, structured output parsing/validation.
**Tests:** router-selection unit tests, structured-output schema validation tests. **Acceptance
criteria:** router correctly selects local vs. cloud based on documented criteria; invalid
agent output is rejected by the validator. **Known risks:** cost/latency mis-estimation leading
to poor routing choices. **Definition of done:** AI layer produces schema-valid structured
output end-to-end against a test harness (no live target required).

## Phase 7 — Intelligence Agents

**Objectives:** Implement the specialized AI agents. **Dependencies:** Phase 6.
**Files to implement:** `ai/recon_agent.py`, `ai/api_agent.py`, `ai/js_agent.py`,
`ai/authz_agent.py`, `ai/logic_agent.py`, `ai/triage_agent.py`, `ai/hypothesis_agent.py`,
`intelligence/*.py`. **Features:** per `07_AI_AGENTS.md` per-agent contracts. **Tests:** AI
contract tests (no fabrication, correct truth labels, evidence references present). **Acceptance
criteria:** each agent's output passes the AI Contract Test suite (`13_TESTING_STRATEGY.md`).
**Known risks:** agents drifting into asserting findings instead of hypotheses. **Definition of
done:** all agents pass contract tests against recorded evidence fixtures.

## Phase 8 — Adaptive Recon Loop

**Objectives:** Close the loop: analysis → new tasks → scope check → execution → correlation →
analysis again. **Dependencies:** Phases 5–7. **Files to implement:**
`correlation/relationship_engine.py`, `correlation/asset_graph.py`,
`correlation/endpoint_graph.py`, `correlation/deduplication.py`, loop wiring in
`core/orchestrator.py`. **Features:** full adaptive loop per `03_RECON_PIPELINE.md` §27.
**Tests:** end-to-end loop tests against a controlled local lab fixture. **Acceptance criteria:**
a lab run demonstrates at least one full "discovery → hypothesis → new task" cycle without
manual intervention (beyond configured stop conditions). **Known risks:** infinite-loop
regressions if task fingerprinting is incomplete. **Definition of done:** loop test suite passes
and task deduplication is verified under repeated re-analysis.

## Phase 9 — Reporting

**Objectives:** Generate JSON, Markdown, and HTML reports. **Dependencies:** Phase 8 (or
earlier data if run without AI). **Files to implement:** `reports/json_report.py`,
`reports/markdown_report.py`, `reports/html_report.py`, `ai/report_agent` wiring if applicable.
**Features:** full report structure per `09_OUTPUTS.md`. **Tests:** report-generation snapshot
tests. **Acceptance criteria:** all three formats render the same underlying data consistently,
with facts/hypotheses clearly separated. **Known risks:** report drift from the documented
structure. **Definition of done:** report tests pass for a fixture run with mixed facts,
hypotheses, and validated findings.

## Phase 10 — FastAPI

**Objectives:** Expose ARGUS functionality through an API. **Dependencies:** Phase 5+ (core
functionality); Phase 9 for report endpoints. **Files to implement:** `api/server.py` and
supporting route modules. **Features:** run creation, run status, task inspection, report
retrieval endpoints. **Tests:** API integration tests against a test database. **Acceptance
criteria:** documented endpoints behave per their contract; authentication/authorization for the
API itself is enforced. **Known risks:** API surface accidentally exposing direct tool
execution — must still route through Orchestrator/Scope Guard. **Definition of done:** API test
suite passes and no endpoint bypasses the safety architecture.

## Phase 11 — Dashboard

**Objectives:** Build the operator-facing UI. **Dependencies:** Phase 10. **Files to
implement:** `dashboard/` (framework TBD at implementation time). **Features:** run/asset/task
visualization, attack-surface graph view, hypothesis review UI. **Tests:** UI component tests,
integration tests against the API. **Acceptance criteria:** operator can view runs, assets,
hypotheses, and approve/reject validation steps. **Known risks:** UI encouraging bypass of
human-in-the-loop review (e.g. one-click "approve all") — must be designed against.
**Definition of done:** dashboard supports the full human-in-the-loop review workflow.

## Phase 12 — Hardening

**Objectives:** Security, reliability, performance, failure handling, and auditability pass
across the whole system. Also the point at which Windows platform compatibility is evaluated as
a supported environment, per `15_FIRST_MILESTONE.md` §Supported Environment and
`06_TOOL_CONTRACTS.md` §Platform Support. **Dependencies:** all prior phases. **Files to
implement:**
cross-cutting fixes identified during review; no new major modules expected. **Features:**
expanded logging/audit coverage, performance tuning, chaos/failure testing. **Tests:** full
regression suite, security review checklist, load testing. **Acceptance criteria:** no known
Scope Guard/Rate Limiter bypass; resumability holds under injected failures; logs never leak
secrets. **Known risks:** hardening surfacing design issues that require revisiting earlier
phases — treat as expected, not exceptional. **Definition of done:** full test suite green, and
the safety architecture in `04_SCOPE_SAFETY.md` has been independently verified end-to-end.
