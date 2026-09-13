# ARGUS Product Specification

Defines **what** ARGUS must do. For **how** it is implemented, see `02_ARCHITECTURE.md`.

## 1. Product Overview

ARGUS is an AI-assisted adaptive reconnaissance and attack-surface intelligence platform that
continuously discovers, normalizes, correlates, analyzes, and prioritizes authorized
reconnaissance data. It replaces fixed tool-chain wrappers with a feedback loop in which
deterministic tools supply facts and an AI layer reasons over an evolving attack-surface graph.

## 2. Problem Statement

Security teams and testers run many disconnected recon tools and manually stitch results
together, losing correlation opportunities (e.g. a JavaScript-discovered endpoint that should
immediately trigger authorization analysis). Manual adaptive reasoning doesn't scale across
large scopes, and unstructured AI use over recon data risks fabricated or unverifiable findings.

## 3. Goals

- Deterministic, reproducible fact collection across the full recon surface
- A normalized, queryable, relationship-aware attack-surface model
- AI-driven correlation, hypothesis generation, and task prioritization
- Continuous adaptive reconnaissance rather than a fixed tool sequence
- Hard, deterministic scope and safety enforcement that AI cannot bypass
- Full evidence traceability from tool run to reported hypothesis
- Resumable, auditable, cost/latency-aware operation

## 4. Non-Goals

- ARGUS is **not** an autonomous exploitation engine
- ARGUS does **not** perform credential attacks, destructive testing, or denial-of-service
- ARGUS does **not** treat AI output as ground truth
- ARGUS does **not** replace human judgment on sensitive validation steps
- ARGUS does **not** attempt to bypass WAFs, rate limits, or other security controls

## 5. Target Users

Authorized penetration testers, bug bounty researchers, internal red/security teams assessing
owned infrastructure, and students/educators in controlled lab environments.

## 6. Authorized Use Cases

- Authorized penetration tests with defined scope
- Bug bounty programs where testing is explicitly permitted
- Owned infrastructure assessments
- Controlled labs and educational environments

ARGUS must not be designed around, or facilitate, unauthorized exploitation of systems the
operator is not authorized to test.

## 7. Core Capabilities

1. Aggressive, deduplicated asset discovery
2. DNS resolution and correlation
3. Scoped network/port/service reconnaissance
4. HTTP/HTTPS probing and technology fingerprinting
5. Web crawling and content discovery
6. Historical URL recon
7. Deep JavaScript and source-map analysis
8. REST/OpenAPI/Swagger, GraphQL, and WebSocket reconnaissance
9. Authentication and authorization intelligence
10. Parameter intelligence
11. Cloud/CDN/WAF intelligence
12. Attack-surface graph construction
13. AI-driven correlation, hypothesis generation, and prioritization
14. Adaptive task generation under scope control
15. JSON/Markdown/HTML reporting with full evidence traceability

## 8. Reconnaissance Capabilities

See `03_RECON_PIPELINE.md` for the full 27-stage pipeline (subdomain discovery through
correlation and the adaptive recon loop).

## 9. Intelligence Capabilities

Technology detection, JavaScript intelligence, API/GraphQL/WebSocket intelligence,
authentication and authorization intelligence, parameter intelligence, and cloud/CDN/WAF
intelligence — detailed per-stage in `03_RECON_PIPELINE.md`.

## 10. Adaptive Reconnaissance

ARGUS continuously re-evaluates its own attack-surface model and generates new reconnaissance
tasks as new evidence appears (e.g. a discovered GraphQL endpoint raises the priority of GraphQL
schema analysis; a JavaScript-discovered internal API becomes a new recon target). See
`03_RECON_PIPELINE.md` §27 and `08_ORCHESTRATOR.md`.

## 11. AI Capabilities

AI agents classify, correlate, reason across sources, detect anomalies, generate hypotheses, and
propose next tasks using a hybrid local/cloud model architecture. Full agent contracts:
`07_AI_AGENTS.md`.

## 12. Safety Requirements

- Every task must pass the Scope Guard before execution — no exceptions, no AI override
- The AI never has direct shell/network access to a target
- No destructive testing, credential attacks, brute force, or DoS activity is automated
- Rate limiting and instability detection are always active
- Sensitive validation steps require human approval

Full detail: `04_SCOPE_SAFETY.md`.

## 13. Evidence Model

Every important AI statement must be traceable to the tool run and evidence that produced it:
`Task → Tool Run → Observation → Evidence → AI Analysis → Hypothesis → Next Task`. See
`09_OUTPUTS.md` §Evidence Traceability.

## 14. Truth Model

Every AI-generated statement carries one of the following labels:

| Label | Meaning |
|---|---|
| `FACT` | Directly supported by tool output or stored evidence |
| `OBSERVATION` | A direct interpretation of collected data |
| `INFERENCE` | A reasoned conclusion from multiple observations |
| `HYPOTHESIS` | A potential issue that still requires validation |
| `UNVERIFIED_CLAIM` | Something that cannot be established from current evidence |
| `VALIDATED_FINDING` | A hypothesis confirmed through appropriate evidence/human validation |

When evidence does not exist, ARGUS must prefer `UNKNOWN` over guessing. See `OPENCODE.md`
Rule 3.

## 15. Functional Requirements

Example form: *"ARGUS shall discover subdomains for an in-scope domain using at least one
configured discovery source and persist normalized, deduplicated assets to PostgreSQL."* Each
recon and intelligence capability in §8/§9 should be expressed this way during implementation
planning; see `03_RECON_PIPELINE.md` for the per-stage detail these requirements are derived
from.

## 16. Non-Functional Requirements

Discovery and analysis shall be:

- **Resumable** — a run recovers from crashes, restarts, or tool/network/AI-provider failures
- **Auditable** — every decision (scope, rate-limit, task, AI) is logged
- **Scope-controlled** — enforced deterministically, never by AI judgment alone
- **Deterministic** where tools are concerned — same input, same normalized output
- **Cost/latency-aware** — the AI router selects local vs. cloud models appropriately

## 17. Success Criteria

- A full recon run against an authorized target produces a normalized, evidence-backed
  attack-surface model with no fabricated facts
- Out-of-scope targets, redirects, and discovered hosts are reliably rejected
- Reports clearly separate facts, observations, inferences, hypotheses, and validated findings
- A crashed run can resume from its last checkpoint without data loss or duplicate tasks

## 18. Future Capabilities

Neo4j-backed graph storage, a full interactive dashboard, expanded intelligence agents, and
deeper adaptive attack-path reasoning — all subsequent to the phases in
`10_IMPLEMENTATION_PLAN.md`.
