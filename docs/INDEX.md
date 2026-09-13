# ARGUS Documentation Index

## Name

**ARGUS** — *Adaptive Reconnaissance & Graph-based Unified Security*

## One-Paragraph Description

ARGUS is an AI-assisted reconnaissance and attack-surface intelligence platform for
**authorized** penetration testing, bug bounty work, and controlled security labs. Deterministic
tools collect facts about a target; ARGUS normalizes those facts into a PostgreSQL-backed
attack-surface model; and an AI reasoning layer interprets that model to generate hypotheses and
propose the next reconnaissance tasks — all gated by a deterministic Scope Guard and Rate Limiter
that the AI cannot override. ARGUS is a continuous **see → understand → think → plan → verify
scope → act → observe → learn → repeat** loop, not a fixed sequence of tool invocations.

## Documentation Map

```text
INDEX.md (you are here)
 │
 ├── OPENCODE.md ─────────────── highest-priority instructions for AI coding agents
 │
 ├── 00_README.md ────────────── human-facing introduction
 │
 ├── 01_PRODUCT_SPEC.md ───────── what ARGUS must do (not how)
 │
 ├── 02_ARCHITECTURE.md ───────── how ARGUS is built, layer by layer
 │    ├── 05_DATA_MODEL.md ────── PostgreSQL schema (source of truth)
 │    ├── 06_TOOL_CONTRACTS.md ── external tool adapter interface
 │    ├── 07_AI_AGENTS.md ─────── AI agent responsibilities & I/O contracts
 │    └── 08_ORCHESTRATOR.md ──── state machine, scheduling, task scoring
 │
 ├── 03_RECON_PIPELINE.md ─────── the 27-stage reconnaissance knowledge base
 ├── 04_SCOPE_SAFETY.md ───────── authorization, scope enforcement, safety rails
 ├── 09_OUTPUTS.md ─────────────── reports, evidence, storage layout
 ├── 10_IMPLEMENTATION_PLAN.md ── phase-by-phase build roadmap
 ├── 13_TESTING_STRATEGY.md ────── test strategy across all layers
 ├── 14_CONFIG_EXAMPLE.md ──────── canonical configuration reference
 ├── 15_FIRST_MILESTONE.md ─────── what to build *first* (no AI yet)
 ├── 11_OPENCODE_WORKFLOW.md ───── how an AI coding agent should work on this repo
 └── 12_AI_PROMPTS.md ──────────── system/agent prompt library
```

## Recommended Reading Order

1. `OPENCODE.md` — non-negotiable rules, read this first, always
2. `00_README.md` — orientation
3. `01_PRODUCT_SPEC.md` — what we're building
4. `02_ARCHITECTURE.md` — how the pieces fit together
5. `04_SCOPE_SAFETY.md` — the safety model (critical, read before touching code)
6. `05_DATA_MODEL.md`, `06_TOOL_CONTRACTS.md`, `07_AI_AGENTS.md`, `08_ORCHESTRATOR.md`
7. `03_RECON_PIPELINE.md` — reconnaissance stage reference
8. `15_FIRST_MILESTONE.md` — what to implement right now
9. `10_IMPLEMENTATION_PLAN.md` — everything after the first milestone
10. `13_TESTING_STRATEGY.md`, `14_CONFIG_EXAMPLE.md`, `12_AI_PROMPTS.md`, `11_OPENCODE_WORKFLOW.md` as needed

## Document Dependency Relationships

```text
INDEX
 ├── PRODUCT SPEC
 ├── ARCHITECTURE
 │    ├── DATA MODEL
 │    ├── TOOL CONTRACTS
 │    ├── AI AGENTS
 │    └── ORCHESTRATOR
 ├── RECON PIPELINE
 ├── SCOPE & SAFETY
 ├── OUTPUTS
 ├── IMPLEMENTATION PLAN
 ├── TESTING
 ├── CONFIG
 ├── FIRST MILESTONE
 └── OPENCODE WORKFLOW
```

`04_SCOPE_SAFETY.md` sits conceptually *above* every implementation document — nothing in
`06_TOOL_CONTRACTS.md`, `08_ORCHESTRATOR.md`, or `07_AI_AGENTS.md` may contradict it.

## Authoritative-Document Rules

- If two documents conflict, resolve in this order: `OPENCODE.md` → `01_PRODUCT_SPEC.md` →
  `02_ARCHITECTURE.md` → the relevant specialized document. See `OPENCODE.md` Rule 1 for the
  full precedence chain, and `04_SCOPE_SAFETY.md` for why safety rules sit outside this chain
  entirely (they are never overridden).
- Each subject has exactly one authoritative document (e.g. scope lives only in
  `04_SCOPE_SAFETY.md`). Other documents must reference it rather than duplicate it.
- Architectural changes require updating both code and documentation in the same change —
  see `OPENCODE.md` / documentation rule.

## Terminology (Quick Reference)

| Term | Meaning |
|---|---|
| **Fact** | Directly supported by tool output or stored evidence |
| **Observation** | A direct interpretation of collected data |
| **Inference** | A reasoned conclusion from multiple observations |
| **Hypothesis** | A potential issue that still requires validation |
| **Unverified claim** | Something the AI cannot establish from current evidence |
| **Validated finding** | A hypothesis confirmed by appropriate evidence/human validation |
| **Scope Guard** | The deterministic component that authorizes or rejects every task |
| **Task** | A structured unit of work the orchestrator schedules and executes |

Full definitions live in `01_PRODUCT_SPEC.md` §14 (Truth Model) and `04_SCOPE_SAFETY.md`.

## Architecture at a Glance

```text
Deterministic Layer                    Intelligence Layer
 (Recon Tools → Raw Evidence)          (AI Agents → Reasoning/Planning)
              \                              /
               \                            /
                 PostgreSQL (source of truth)
                            │
                  Attack-Surface Graph
                            │
                      Task Planner
                            │
                      Scope Guard
                            │
                      Rate Limiter
                            │
                      Tool Runner
                            │
                        Targets ──→ New Evidence ──→ AI Again
```

## Implementation Order

`15_FIRST_MILESTONE.md` (deterministic foundation, no AI) → `10_IMPLEMENTATION_PLAN.md` Phases
1–5 (infra/DB/adapters/normalization/orchestrator) → Phase 6+ (AI layer, adaptive loop,
reporting, API, dashboard, hardening). See `10_IMPLEMENTATION_PLAN.md` for full phase detail.
