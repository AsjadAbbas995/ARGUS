# ARGUS Orchestrator

Defines the brain of ARGUS: the run/task state machines, scheduling, deduplication, scoring, and
resumability. The **run state machine below** is stored in `runs.status` (`05_DATA_MODEL.md`);
the **task status set** (`pending`, `running`, `completed`, `failed`, `skipped`, `cancelled`) is
stored in `tasks.status` and is a separate concept.

## Run State Machine

```text
CREATED
   ↓
VALIDATING
   ↓
INITIALIZING
   ↓
RECONNING
   ↓
ANALYZING
   ↓
PLANNING
   ↓
EXECUTING
   ↓
CORRELATING
   ↓
PRIORITIZING
   ↓
WAITING_FOR_NEXT_TASK
   ↓
COMPLETED
```

Also handled at the run level: `FAILED`, `CANCELLED`. (`SKIPPED` is a task-level status, not a
run state.) A run transitions to `WAITING_FOR_NEXT_TASK` and
loops back toward `RECONNING`/`ANALYZING` as long as new tasks keep being generated; it only
reaches `COMPLETED` when the adaptive loop's stop conditions are met (see
`01_PRODUCT_SPEC.md` §10).

## Task Queue, Dependencies, and Priorities

Every task carries: `id, run_id, type, target, parent_task, priority, status, reason,
fingerprint, created_at, started_at, completed_at` (`05_DATA_MODEL.md` §tasks). Dependencies
between tasks are expressed through `parent_task` links (a task may have one parent task that
must complete first); scope is enforced by the Scope Guard at execution time, not stored on the
task. `run_id` links every task to its owning run.

Example:

```text
Task:
  Analyze JavaScript
Target:
  https://example.com/app.js
Reason:
  New JavaScript asset discovered during crawling
Priority:
  High
```

Tasks may depend on other tasks, e.g.:

```text
Discover subdomains → Resolve DNS → Probe HTTP → Crawl application
→ Analyze JavaScript → Analyze APIs
```

The scheduler understands these dependencies; a task must not run before the information it
requires exists.

## Task Deduplication

Every task has a deterministic fingerprint based on:

```text
task_type + target + important configuration + relevant parent/context
```

If the same fingerprint has already completed successfully, ARGUS does not regenerate it. This
is essential to prevent infinite loops in the adaptive reconnaissance cycle.

## Task Prioritization / Scoring

The Task Planner scores tasks using: expected value, confidence, novelty, business relevance,
exposure, potential impact, cost, dependencies, and risk. Conceptual scoring model:

```text
score =
    expected_value
    × confidence
    × novelty
    × relevance
    ÷ (cost + 1)
```

**Safety checks are hard filters applied before scoring can authorize execution.** A dangerous
task never becomes acceptable merely because its computed score is high — see
`04_SCOPE_SAFETY.md`.

## Retries and Failure Isolation

Tool failures, timeouts, and AI-provider failures are isolated to the affected task; the run
continues with other available work rather than halting entirely. Retry behavior is
configurable per task type but always respects the Rate Limiter and Scope Guard.

## Resumability

ARGUS must not lose progress if the process crashes, the machine restarts, a tool fails, the
network fails, or the AI provider fails.

- **Run states** (uppercase, in `runs.status`): `CREATED, VALIDATING, INITIALIZING, RECONNING,
  ANALYZING, PLANNING, EXECUTING, CORRELATING, PRIORITIZING, WAITING_FOR_NEXT_TASK, COMPLETED,
  FAILED, CANCELLED`.
- **Task statuses** (lowercase, in `tasks.status`): `pending, running, completed, failed,
  skipped, cancelled`.

A run is restartable from its last known checkpoint — tasks found `running` on restart are
re-evaluated (retried or marked failed) rather than assumed complete, and the run re-enters the
state machine from the state at which it stopped.

## Cancellation

A user-initiated stop transitions in-flight tasks to `cancelled` and the run to `CANCELLED`
without discarding already-persisted evidence.

## Severity vs. Priority

These are stored independently (see `05_DATA_MODEL.md` `hypotheses` table):

- **Severity** — potential impact of a confirmed security issue
- **Priority** — how urgently ARGUS should investigate something

A low-confidence but potentially high-impact hypothesis may carry **high priority, low
confidence**. A confirmed but low-impact issue may carry **low priority, high confidence**.

## The Adaptive Loop

```text
Analyze → Discover leads → Generate tasks → Scope check → Execute → Correlate → Analyze again
```

This loop is what makes ARGUS an adaptive agent rather than a fixed tool wrapper — see
`03_RECON_PIPELINE.md` §27 and `01_PRODUCT_SPEC.md` §10 for stop conditions.

## Relationship to Other Documents

- `04_SCOPE_SAFETY.md` — safety checks that gate every task before scoring/execution
- `07_AI_AGENTS.md` — the agents whose output becomes proposed tasks
- `06_TOOL_CONTRACTS.md` — the Tool Runner/adapters that execute approved tasks
- `13_TESTING_STRATEGY.md` §Orchestrator Tests — how state transitions, deduplication, and
  resumability are verified
