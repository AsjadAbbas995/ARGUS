# OPENCODE.md — Highest-Priority Instructions

**You are implementing ARGUS, not inventing a new architecture.**

## Project Identity

**ARGUS** — Adaptive Reconnaissance & Graph-based Unified Security. An AI-assisted
reconnaissance and attack-surface intelligence platform for authorized penetration testing, bug
bounty work, and controlled labs.

## Core Principle

```text
Deterministic tools collect facts.
PostgreSQL preserves facts.
Graph relationships connect facts.
AI interprets facts.
Task Planner proposes work.
Scope Guard determines whether work is allowed.
Tool Runner executes approved work.
```

## Non-Negotiable Rules

- Never bypass the Scope Guard.
- Never allow the AI layer direct/unrestricted shell execution.
- Never fabricate evidence.
- Never treat a hypothesis as a validated finding.
- Never silently change the architecture.
- Never silently change the database schema.
- Never implement future phases prematurely (respect `10_IMPLEMENTATION_PLAN.md` ordering and
  `15_FIRST_MILESTONE.md` exclusions).
- Preserve raw tool output.
- Every AI claim must reference evidence.
- Every active task must pass scope validation.
- Use structured schemas for AI output.
- Maintain tests.
- Maintain documentation.
- Prefer small, composable modules.
- Keep tool adapters independent from AI logic.

## Rule 1 — One Source of Truth

If two documents conflict, resolve in this order:

```text
OPENCODE.md
    ↓
01_PRODUCT_SPEC.md
    ↓
02_ARCHITECTURE.md
    ↓
specialized documents (03–15)
```

Architectural changes must be reflected everywhere they're relevant — code and docs change
together (see `11_OPENCODE_WORKFLOW.md` §Documentation Rule).

## Rule 2 — Don't Duplicate Giant Sections

`04_SCOPE_SAFETY.md` contains the complete scope-and-safety architecture. Other documents should
say *"See `04_SCOPE_SAFETY.md` for the authoritative scope enforcement model"* rather than
copying it. The same applies to any other document's core subject matter — one authoritative
home per topic.

## Rule 3 — Distinguish Facts From Hypotheses

ARGUS must maintain the full truth-label set: `FACT`, `OBSERVATION`, `INFERENCE`, `HYPOTHESIS`,
`UNVERIFIED_CLAIM`, `VALIDATED_FINDING`.

**Never:**

```text
AI suspects IDOR
        ↓
ARGUS reports IDOR
```

**Correct:**

```text
Observation
    ↓
Hypothesis
    ↓
Evidence
    ↓
Human / safe validation
    ↓
Validated Finding
```

## Final ARGUS Source-Code Structure

```text
ARGUS/
│
├── docs/
│   ├── INDEX.md
│   ├── 00_README.md
│   ├── 01_PRODUCT_SPEC.md
│   ├── 02_ARCHITECTURE.md
│   ├── 03_RECON_PIPELINE.md
│   ├── 04_SCOPE_SAFETY.md
│   ├── 05_DATA_MODEL.md
│   ├── 06_TOOL_CONTRACTS.md
│   ├── 07_AI_AGENTS.md
│   ├── 08_ORCHESTRATOR.md
│   ├── 09_OUTPUTS.md
│   ├── 10_IMPLEMENTATION_PLAN.md
│   ├── 11_OPENCODE_WORKFLOW.md
│   ├── 12_AI_PROMPTS.md
│   ├── 13_TESTING_STRATEGY.md
│   ├── 14_CONFIG_EXAMPLE.md
│   ├── 15_FIRST_MILESTONE.md
│   └── OPENCODE.md
│
├── core/
│   ├── orchestrator.py
│   ├── task_planner.py
│   ├── scope_guard.py
│   ├── rate_limiter.py
│   ├── scheduler.py
│   └── config.py
│
├── recon/
│   ├── subdomains/   (subfinder.py, amass.py, assetfinder.py, crt.py)
│   ├── dns/          (resolver.py)
│   ├── network/      (ports.py, services.py)
│   ├── web/          (httpx.py, katana.py, ffuf.py, feroxbuster.py)
│   └── historical/   (gau.py, wayback.py)
│
├── intelligence/
│   (technology.py, javascript.py, api.py, graphql.py, websocket.py,
│    authentication.py, cloud.py, waf.py, parameters.py)
│
├── ai/
│   (local_model.py, cloud_model.py, router.py, recon_agent.py, api_agent.py,
│    js_agent.py, authz_agent.py, logic_agent.py, triage_agent.py, hypothesis_agent.py)
│
├── correlation/
│   (asset_graph.py, endpoint_graph.py, relationship_engine.py, deduplication.py)
│
├── evidence/
│   (collector.py, store.py, integrity.py)
│
├── database/
│   (models/, migrations/, repositories/)
│
├── reports/
│   (json_report.py, markdown_report.py, html_report.py)
│
├── api/
│   (server.py)
│
├── dashboard/
│
├── storage/
│   (raw/, evidence/, screenshots/, reports/)
│
└── tests/
```

Start at `INDEX.md` for the full documentation map and reading order.
