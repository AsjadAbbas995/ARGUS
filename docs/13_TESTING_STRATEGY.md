# ARGUS Testing Strategy

Testing happens throughout development, not as a final pass. No test in CI depends on live
external targets.

## Unit Tests

Cover: configuration parsing, scope matching, task fingerprinting, task scoring, normalization
logic, and individual parsers in isolation.

## Adapter Fixture Tests

Every tool adapter (`06_TOOL_CONTRACTS.md`) is tested against recorded fixture output, never a
live tool invocation, in normal CI:

```text
fixtures/
├── subfinder/
├── nmap/
├── httpx/
├── katana/
└── ffuf/
```

Each adapter's `parse()` method must produce the correct normalized objects from its fixture,
including edge cases (empty results, malformed lines, partial output).

## Database Tests

Verify: inserts, relationships (foreign keys resolve correctly), deduplication constraints
(`05_DATA_MODEL.md` unique constraints), migrations (apply and roll back cleanly), and error
handling on constraint violations.

## Scope Tests

```text
Allowed target                 → allowed
Excluded target                 → rejected
Out-of-scope redirect           → rejected; redirect recorded as observation; destination
                                  marked out-of-scope; no active interaction
Out-of-scope discovered host    → rejected
Disallowed port                 → rejected
```

Every rejection must be logged (`04_SCOPE_SAFETY.md`). Test coverage must include the
redirect/discovered-target policy (`04_SCOPE_SAFETY.md` §Redirect and Discovered-Target
Policy) across all discovery surfaces: redirects, DNS-discovered IPs, JavaScript-discovered
hosts, API destinations, WebSocket endpoints, and crawl-discovered links.

## Command Safety Tests

Verify: `shell=False` is used everywhere a subprocess is invoked, commands are constructed as
argument arrays (never string-concatenated), there is no command-injection path from untrusted
target input, timeouts are enforced, and stdout/stderr are captured without leaking secrets into
logs.

## Orchestrator Tests

Cover: state transitions (`08_ORCHESTRATOR.md` state machine), task dependency ordering, task
deduplication (same fingerprint does not re-run), resumability after a simulated crash,
failure-isolation (one task's failure doesn't halt the run), and retry behavior.

## AI Contract Tests

Verify every agent (`07_AI_AGENTS.md`):

- Returns schema-valid structured output (`12_AI_PROMPTS.md` §Output Schemas)
- Does not invent evidence not present in the supplied context
- Respects truth labels — never asserts `FACT` where only `HYPOTHESIS` is warranted
- Does not produce arbitrary commands or targets outside the supplied scope
- Never attempts to change scope

## Integration Tests

Run against controlled local labs only — never against external, uncontrolled targets. A
representative lab fixture should exercise the full pipeline: discovery → normalization →
persistence → (once implemented) AI analysis → task generation → scope check → execution →
correlation, to validate the adaptive loop end-to-end (`03_RECON_PIPELINE.md` §27,
`10_IMPLEMENTATION_PLAN.md` Phase 8).

## Relationship to Other Documents

- `04_SCOPE_SAFETY.md` — the rules Scope/Command Safety tests verify
- `08_ORCHESTRATOR.md` — the state machine Orchestrator tests verify
- `07_AI_AGENTS.md` / `12_AI_PROMPTS.md` — the contracts AI Contract tests verify
- `15_FIRST_MILESTONE.md` §Acceptance Criteria — the specific tests Milestone 1 must pass
