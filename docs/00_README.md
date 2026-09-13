# ARGUS

**Adaptive Reconnaissance & Graph-based Unified Security**

## What ARGUS Is

ARGUS is an AI-assisted cybersecurity reconnaissance and attack-surface intelligence platform
built for authorized penetration testing, bug bounty programs, security assessments, and
controlled labs. It combines deterministic, reproducible reconnaissance tooling with an AI
reasoning layer that continuously interprets discovered facts and decides what should be
investigated next.

## Why ARGUS Exists

### The Problem

Traditional reconnaissance frameworks run a fixed list of tools once and hand the operator a
static report:

```text
Run Nmap → Run Subfinder → Run FFUF → Generate report.
```

This misses the way a skilled human tester actually works: notice something interesting, pull
the thread, adjust the plan, and go deeper where it matters. Fixed pipelines don't adapt, don't
correlate discoveries across tools, and don't get smarter as evidence accumulates.

### The Core Differentiator

ARGUS treats reconnaissance as a continuous, evidence-driven loop instead of a checklist:

```text
INITIAL RECON → COLLECT FACTS → NORMALIZE DATA → BUILD ATTACK-SURFACE GRAPH
→ AI ANALYSIS → DISCOVER NEW LEADS → GENERATE NEXT TASKS → SCOPE CHECK
→ EXECUTE TASKS → COLLECT EVIDENCE → CORRELATE RESULTS → AI ANALYSIS AGAIN
→ PRIORITIZE NEXT TASKS → REPEAT
```

The loop continues until useful coverage is achieved, no worthwhile tasks remain, the configured
time/budget is exhausted, the user stops the run, or a safety/instability limit is reached.

**Core principle:** deterministic tools collect facts; AI interprets those facts and decides
what should be investigated next. AI never gets to pretend it observed something a tool didn't
actually observe.

## High-Level Workflow

```text
Target + Scope → Scope Validation → Recon → Normalize → Persist
→ AI Analysis → Task Generation → Scope Check → Execute → Correlate → Repeat
→ Reports (JSON / Markdown / HTML)
```

## Supported Reconnaissance Categories

- Subdomain & asset discovery (Subfinder, Amass, Assetfinder, certificate transparency)
- DNS intelligence and IP correlation
- Network/port/service reconnaissance
- HTTP/HTTPS probing and technology fingerprinting
- Web crawling and content discovery
- Historical URL recon (GAU, Wayback)
- Deep JavaScript and source-map analysis
- API reconnaissance: REST/OpenAPI/Swagger, GraphQL, WebSockets
- Authentication and authorization intelligence
- Parameter intelligence
- Cloud / CDN / WAF intelligence

## The AI's Role

AI agents classify, correlate, reason, prioritize, detect relationships, generate hypotheses,
and propose the next reconnaissance tasks. AI never fabricates evidence, never claims a tool ran
when it didn't, and never turns a hypothesis into a confirmed finding on its own. Every
AI-generated statement carries an explicit truth label: `FACT`, `OBSERVATION`, `INFERENCE`,
`HYPOTHESIS`, or `UNVERIFIED_CLAIM`.

## The Safety Model

ARGUS enforces a strict separation between reasoning and execution:

```text
AI → Proposed Task → Task Planner → Scope Guard → Rate Limiter → Tool Adapter → Tool Runner → Target
```

Never `AI → shell → target`. The Scope Guard is deterministic and the AI cannot override it,
disable rate limiting, bypass safety, or execute arbitrary commands. ARGUS never automates
destructive exploitation, credential attacks, uncontrolled brute force, denial-of-service
activity, or security-control evasion. Sensitive validation steps remain human-approved. Full
detail: `04_SCOPE_SAFETY.md`.

## Current Development Status

ARGUS is at the **first-milestone** stage: building the deterministic foundation (config, Scope
Guard, Rate Limiter, Tool Runner, PostgreSQL, Subfinder/DNS/httpx adapters, normalization,
persistence, tests, JSON summary) **before** any AI is introduced. See `15_FIRST_MILESTONE.md`.

## Quick-Start Conceptual Flow

```text
1. Operator defines target + scope
2. ARGUS validates scope
3. ARGUS runs initial discovery (subdomains → DNS → HTTP)
4. Results are normalized and persisted to PostgreSQL
5. (Later phases) AI analyzes the attack-surface graph and proposes next tasks
6. Each task passes the Scope Guard before execution
7. Reports are generated in JSON, Markdown, and HTML
```

## Documentation Links

See `INDEX.md` for the full documentation map and recommended reading order. Start with
`OPENCODE.md` if you are an AI coding agent working on this repository.

## Future Roadmap

Local/cloud hybrid AI router → intelligence agents (JS, API, AuthZ, Logic, Triage, Hypothesis,
Report) → adaptive reconnaissance loop → FastAPI service layer → dashboard with attack-surface
graph visualization → hardening pass. See `10_IMPLEMENTATION_PLAN.md`.
