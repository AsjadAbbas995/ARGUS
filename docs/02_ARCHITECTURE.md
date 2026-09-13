# ARGUS Architecture

Describes **how** ARGUS is built. For **what** it must do, see `01_PRODUCT_SPEC.md`.

## End-to-End Flow

```text
CLI / API / Dashboard
        ↓
    Run Manager
        ↓
    Orchestrator
        ↓
    Task Planner
        ↓
    Scope Guard
        ↓
    Rate Limiter
        ↓
    Tool Runner
        ↓
    Tool Adapters
        ↓
    Recon Tools
        ↓
    Raw Output
        ↓
  Parser / Normalizer
        ↓
    PostgreSQL
        ↓
  Attack-Surface Graph
        ↓
  AI Intelligence Layer
        ↓
   Task Generation
        ↓
    Orchestrator (loop)
```

## Architecture Layers

| Layer | Responsibility | Key Modules |
|---|---|---|
| Interface | CLI, future FastAPI, future dashboard | `api/server.py`, CLI entrypoint |
| Run Management | Run creation, persistence, intake-level scope validation | `runs` model (`05_DATA_MODEL.md`), intake layer |
| Control/Orchestration | Run and task lifecycle, scheduling | `core/orchestrator.py`, `core/scheduler.py`, `core/task_planner.py` |
| Safety | Scope enforcement, rate control | `core/scope_guard.py`, `core/rate_limiter.py` |
| Execution | Safe process execution | Tool Runner (part of `core/`) |
| Recon Adapters | Tool-specific command/parse logic | `recon/**` |
| Parsing/Normalization | Raw output → canonical objects | adapter `parse()` methods, `intelligence/**` |
| Persistence | Authoritative data store | `database/**` |
| Correlation/Graph | Relationship reasoning over normalized data | `correlation/**` |
| AI | Reasoning, hypothesis generation, prioritization | `ai/**` |
| Evidence | Traceable evidence records | `evidence/**` |
| Reporting | JSON/Markdown/HTML output | `reports/**` |

## Component Responsibilities

- **Run Manager** — creates and persists the top-level `runs` record at intake (per
  `03_RECON_PIPELINE.md` §2), attaches the program and program-scoped scope, stores the
  configuration snapshot, and hands the run to the Orchestrator (`05_DATA_MODEL.md` §runs)
- **Orchestrator** — drives the state machine (`08_ORCHESTRATOR.md`), owns run lifecycle
- **Task Planner** — scores and sequences proposed tasks; safety checks precede scoring
- **Scope Guard** — deterministic accept/reject decision for every task and every redirect/DNS
  resolution/discovered hostname; AI cannot override it (`04_SCOPE_SAFETY.md`)
- **Rate Limiter** — enforces global, per-host, and per-tool request/concurrency limits
- **Tool Runner** — executes approved commands as argument arrays (`shell=False`), captures
  stdout/stderr/exit code, enforces timeouts, preserves raw output (`06_TOOL_CONTRACTS.md`)
- **Tool Adapters** — one per external tool; verify availability, build commands, validate
  against scope, execute, parse, normalize
- **Parser/Normalizer** — converts raw tool output into canonical, deduplicated objects
- **PostgreSQL** — the authoritative source of truth (`05_DATA_MODEL.md`)
- **Attack-Surface Graph** — relationship view over normalized data (built on PostgreSQL now;
  Neo4j is an optional future backend)
- **AI Intelligence Layer** — agents that read structured context and produce structured,
  evidence-referenced output (`07_AI_AGENTS.md`)
- **Evidence system** — links every AI statement back to the tool run/observation that produced
  it (`09_OUTPUTS.md`)
- **Reporting** — JSON, Markdown, HTML outputs that separate facts from hypotheses

## Data Flow

`Target intake → Scope validation → Tool execution → Raw output capture → Parsing →
Normalization → Persistence → Graph correlation → AI analysis → New task proposals → Scope
Guard → Execution (loop)`.

## Control Flow

The Orchestrator advances a run through its state machine (`08_ORCHESTRATOR.md`), pulling tasks
from the scheduler in priority order, respecting dependencies, and re-entering the loop after
each analysis/correlation step.

## Failure Flow

Tool unavailability, timeouts, and AI-provider failures are logged and degrade gracefully (skip
and continue with available sources) rather than crashing the run. Run/task state is persisted
so a crashed process can resume from its last checkpoint (`08_ORCHESTRATOR.md` §Resumability).

## AI Flow

`Evidence → Context Builder → AI Router → Local/Cloud Model → Agent → Structured Output →
Validator → Task Planner`. See `07_AI_AGENTS.md`.

## Security / Trust Boundaries

```text
AI  →  Proposed Task  →  Task Planner  →  Scope Guard  →  Rate Limiter  →  Tool Adapter  →  Tool Runner  →  Target
```

Never `AI → shell → target`. The AI process has no direct network or shell access to any target;
every path to a target passes through the Scope Guard and Rate Limiter, which are deterministic
and outside AI control. Full detail: `04_SCOPE_SAFETY.md`.

## Future Extensibility

- PostgreSQL-first graph model may be supplemented by Neo4j for advanced graph queries
- AI router may add more local/cloud model backends without changing agent contracts
- Dashboard and FastAPI layers are additive on top of the existing orchestrator/task model
- New tool adapters plug into the existing `ToolAdapter` interface (`06_TOOL_CONTRACTS.md`)
  without touching AI or safety logic
- Windows platform support may be added in Phase 12 hardening without changing adapter
  contracts, because command construction and execution are platform-neutral
  (`06_TOOL_CONTRACTS.md` §Platform Support)
