# ARGUS OpenCode / AI Coding-Agent Workflow

Tells an AI coding agent (OpenCode, Claude Code, or similar) exactly how to work on this repo.
This document is procedural; `OPENCODE.md` holds the non-negotiable rules.

## Workflow

```text
READ
 ↓
UNDERSTAND
 ↓
INSPECT REPOSITORY
 ↓
PLAN
 ↓
IMPLEMENT
 ↓
TEST
 ↓
REVIEW
 ↓
DOCUMENT
 ↓
COMMIT-READY
```

Before writing any code, read (in this order): `INDEX.md`, `00_README.md`, `01_PRODUCT_SPEC.md`,
`02_ARCHITECTURE.md`, `03_RECON_PIPELINE.md`, `04_SCOPE_SAFETY.md`, `05_DATA_MODEL.md`,
`06_TOOL_CONTRACTS.md`, `07_AI_AGENTS.md`, `08_ORCHESTRATOR.md`, `09_OUTPUTS.md`,
`10_IMPLEMENTATION_PLAN.md`, `11_OPENCODE_WORKFLOW.md` (this file), `12_AI_PROMPTS.md`,
`13_TESTING_STRATEGY.md`, `14_CONFIG_EXAMPLE.md`, `15_FIRST_MILESTONE.md`, `OPENCODE.md`.

Then **inspect the existing repository** — do not assume the docs describe code that already
exists in the intended form; verify against what's actually there before planning a change.

## Rules

The coding agent must:

- Read the relevant docs before coding, every time — not just once per session
- Inspect existing code before proposing changes
- Preserve the documented architecture rather than inventing a new one
- Avoid unnecessary rewrites — prefer small, additive, reversible changes
- Run tests after every change
- Update documentation whenever architecture changes, in the same change
- Never bypass the Scope Guard
- Never give the AI layer unrestricted shell access
- Never silently modify the database schema
- Never implement future phases prematurely (see `10_IMPLEMENTATION_PLAN.md` phase ordering and
  `15_FIRST_MILESTONE.md` exclusions)

## Incremental Coding

Implementation happens in small, logical, reversible commits. Illustrative sequence for the
first milestone:

```text
Commit 1: Project bootstrap
Commit 2: Configuration
Commit 3: Scope Guard
Commit 4: Tool Runner
Commit 5: Database models
Commit 6: Subfinder adapter
Commit 7: DNS adapter
Commit 8: httpx adapter
Commit 9: Orchestrator integration
Commit 10: Tests
```

Exact commit structure can change; the principle does not: **small, testable, reversible
changes.**

## Documentation Rule

If architecture changes, code changes and documentation changes happen together, in the same
change set. The Markdown specification files exist precisely so a coding agent has persistent
context across sessions — letting them drift from the actual code defeats their purpose.

## What OpenCode Must Not Do

- Rewrite the entire project unnecessarily
- Invent architecture not described in `02_ARCHITECTURE.md`
- Invent dependencies not already part of the project
- Bypass the Scope Guard
- Provide the AI layer unrestricted shell access
- Silently change the database schema
- Silently change task behavior
- Remove safety mechanisms
- Implement future phases prematurely
- Skip tests
- Ignore migration requirements

See `OPENCODE.md` for the complete, canonical list of non-negotiable rules — this document's
list restates them in a coding-workflow context but `OPENCODE.md` is authoritative if they ever
appear to diverge.
