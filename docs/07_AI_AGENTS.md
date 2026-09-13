# ARGUS AI Agents

Defines ARGUS's AI architecture: the agents, their contracts, and the hybrid local/cloud model
routing that powers them.

## AI Architecture

```text
Evidence
   ↓
Context Builder
   ↓
AI Router
   ↓
Local / Cloud Model
   ↓
Agent
   ↓
Structured Output
   ↓
Validator
   ↓
Task Planner
```

Agents never receive an uncontrolled database dump — the Context Builder assembles only the
structured context each agent needs (target, scope, relevant assets, recent observations,
relevant evidence, existing hypotheses, technology info, related endpoints, previous tasks, tool
outputs, graph relationships), scoped to what that specific agent requires.

## Hybrid Model Routing

**Local model** — used for classification, extraction, deduplication, simple technology
identification, keyword classification, lightweight normalization, basic summarization, and
repetitive analysis.

**Cloud/stronger model** — used for complex correlation, attack-surface reasoning, multi-source
analysis, complicated API relationships, hypothesis generation, prioritization, and complex
reconnaissance planning.

The AI Router (`ai/router.py`) chooses based on task complexity, context size, expected
reasoning requirements, cost, latency, and local-model availability.

## Common Output Contract

All agents return a structured object of this shape (exact schema evolves during
implementation):

```json
{
  "type": "hypothesis",
  "target": "...",
  "observation": "...",
  "reasoning": "...",
  "potential_issue": "...",
  "evidence": [],
  "confidence": 0.0,
  "priority": "medium",
  "validation_step": "..."
}
```

Every agent's output passes through a Validator before reaching the Task Planner: unreferenced
claims, missing evidence, or invalid truth labels are rejected rather than silently accepted.

---

## ReconAgent

**Purpose:** Understand the current attack surface and recommend reconnaissance tasks.
**Inputs:** Attack-surface graph summary, recent observations, existing tasks. **Context:**
Assets, technologies, coverage gaps. **Responsibilities:** Identify missing coverage; recommend
next recon stages. **Forbidden actions:** Cannot propose out-of-scope targets; cannot invent
assets not backed by evidence. **Expected output:** List of proposed tasks with `reason` and
`priority`. **Confidence:** Reflects coverage-gap certainty, not vulnerability certainty.
**Evidence requirements:** Each proposal cites the observation that motivated it. **Failure
behavior:** No proposals if no gaps are evidenced. **Next-task generation:** Feeds the Task
Planner directly.

## APIAgent

**Purpose:** Interpret REST/OpenAPI/GraphQL structures and relationships.
**Inputs:** `apis`, `endpoints`, `parameters`, OpenAPI/Swagger schemas. **Context:** API surface
for the target application. **Responsibilities:** API relationship mapping, object-identifier
detection, auth-observation cross-referencing. **Forbidden actions:** Cannot claim an endpoint
exists without evidence; cannot execute API calls itself. **Expected output:** Structured API
relationship summary + candidate hypotheses for AuthZAgent. **Confidence:** Based on schema
completeness. **Evidence requirements:** Cites the schema/crawl/JS evidence used. **Failure
behavior:** Marks incomplete schemas as `UNKNOWN` rather than filling gaps. **Next-task
generation:** May propose GraphQL/WebSocket-specific recon tasks.

## JSAgent

**Purpose:** JavaScript analysis — endpoint/route extraction, parameters, domains, WebSockets,
source maps, token-like strings. **Inputs:** `javascript_files`, parsed extraction results.
**Context:** The specific JS file(s) and their extraction output. **Responsibilities:** Classify
extracted strings/endpoints; flag items warranting further investigation. **Forbidden actions:**
Cannot assert a token-like string is a confirmed secret; cannot invent endpoints not present in
the parsed output. **Expected output:** Classified findings list (endpoint / secret-candidate /
config-reference / etc.) with confidence per item. **Confidence:** Per-item, reflecting
extraction certainty. **Evidence requirements:** Cites the specific JS file and line/region where
possible. **Failure behavior:** Unparseable/obfuscated code → `UNKNOWN`. **Next-task
generation:** Proposes API discovery / source-map analysis tasks for newly found endpoints.

## AuthZAgent

**Purpose:** Reason about authorization boundaries, object relationships, and role relationships.
**Inputs:** `endpoints`, `parameters` (object-identifier-flagged), `auth_mechanisms`.
**Context:** Endpoint + parameter + auth evidence for the application. **Responsibilities:**
Generate authorization hypotheses (never confirmed findings). **Forbidden actions:** Must never
autonomously test/exploit an authorization boundary; must never label a hypothesis as a
validated finding itself. **Expected output:** `HYPOTHESIS`-labeled statements with a proposed
safe-validation step. **Confidence:** Reflects strength of the correlated evidence, independent
of the hypothesis's potential severity (see `08_ORCHESTRATOR.md` §Severity vs Priority).
**Evidence requirements:** Every hypothesis cites the endpoint/parameter evidence it's built on.
**Failure behavior:** Insufficient evidence → no hypothesis generated. **Next-task generation:**
Proposes a human-approved validation task, never an automatic exploitation task.

## LogicAgent

**Purpose:** Business logic and workflow interpretation; unusual application behavior detection.
**Inputs:** Sequenced endpoint/flow observations (e.g. multi-step processes). **Context:**
Related endpoints forming a workflow. **Responsibilities:** Flag workflow inconsistencies worth
investigating. **Forbidden actions:** Cannot execute workflow steps itself; cannot assert a
business-logic flaw without supporting observations. **Expected output:** Observations/
inferences about workflow structure, optionally escalated to HypothesisAgent. **Confidence:**
Reflects how well-evidenced the workflow sequence is. **Evidence requirements:** Cites the
endpoint sequence observed. **Failure behavior:** Ambiguous flows are left as observations, not
elevated to hypotheses. **Next-task generation:** May propose further crawling/API-discovery
tasks to clarify a workflow.

## TriageAgent

**Purpose:** Prioritization, confidence normalization, and deciding which hypotheses deserve
human attention. **Inputs:** All open `hypotheses`. **Context:** Full hypothesis backlog for the
run. **Responsibilities:** Rank hypotheses by priority/confidence/severity separately; surface
the highest-value items to the operator. **Forbidden actions:** Cannot change a hypothesis's
underlying evidence or truth label to make it rank higher. **Expected output:** Ranked
hypothesis list with separated severity/priority/confidence. **Confidence:** N/A at the ranking
level — it ranks others' confidence, doesn't assign its own claims. **Evidence requirements:**
Ranking must be explainable by reference to the underlying hypotheses' evidence.
**Failure behavior:** Ties broken conservatively (favor human review over auto-dismissal).
**Next-task generation:** May propose validation tasks for top-ranked hypotheses.

## HypothesisAgent

**Purpose:** Turn observations into structured, evidence-linked hypotheses.
**Inputs:** Observations/inferences from Correlation (`03_RECON_PIPELINE.md` §26). **Context:**
The specific observation cluster being considered. **Responsibilities:** Produce a well-formed
`hypotheses` record. **Forbidden actions:** Cannot skip the observation → hypothesis → evidence
chain; cannot mark its own output as `VALIDATED_FINDING`. **Expected output:** A `hypotheses`
row matching the Data Model schema (`05_DATA_MODEL.md`). **Confidence:** Explicit numeric score.
**Evidence requirements:** At least one linked `evidence` record. **Failure behavior:** No
qualifying evidence → no hypothesis is created. **Next-task generation:** Feeds TriageAgent and,
where relevant, a human-approved validation task.

## ReportAgent

**Purpose:** Produce human-readable reports from verified data. **Inputs:** Final run data:
assets, hypotheses, validated findings, evidence, task history. **Context:** The complete run
summary. **Responsibilities:** Render `09_OUTPUTS.md`-structured reports in JSON/Markdown/HTML.
**Forbidden actions:** Cannot upgrade a hypothesis to a finding in the report; cannot omit the
truth-label distinctions. **Expected output:** Report documents per `09_OUTPUTS.md` §Report
Structure. **Confidence:** Reported per-item as stored, not recalculated. **Evidence
requirements:** Every reported claim links back to its evidence chain. **Failure behavior:**
Missing sections are explicitly marked as such rather than omitted silently. **Next-task
generation:** None — this agent is terminal for a run.

---

## AI Safety Boundary (Summary)

No agent above has direct shell or network access. Every agent's output is a *proposal* that
must pass the Task Planner → Scope Guard → Rate Limiter chain before anything executes against a
target. See `04_SCOPE_SAFETY.md` for the full safety architecture.
