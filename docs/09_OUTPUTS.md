# ARGUS Outputs

Defines everything ARGUS produces: raw artifacts, evidence, screenshots, and reports.

## Storage Layout

```text
storage/
├── raw/           # unmodified tool output, per tool
├── evidence/       # evidence artifacts referenced by evidence.raw_reference
├── screenshots/    # visual captures (future web-app screenshots)
└── reports/        # generated JSON / Markdown / HTML reports
```

PostgreSQL holds the structured, canonical data (`05_DATA_MODEL.md`); `storage/` holds the raw
artifacts that back it up.

## Report Formats

- **JSON** — machine-readable; source for integrations, automation, the future dashboard, and
  further AI processing.
- **Markdown** — human-readable security report.
- **HTML** — interactive, report-friendly presentation.

## Report Structure

```text
Executive Summary
Scope
Run Metadata
Attack Surface Summary
Discovered Assets
DNS
IPs
Ports
Services
Web Applications
Technologies
URLs
Endpoints
Parameters
JavaScript Intelligence
API Intelligence
GraphQL
WebSockets
Authentication
Cloud/CDN/WAF
Hypotheses
Validated Findings
Evidence
Recon Timeline
Task History
Coverage
Errors
Limitations
```

**The report must clearly and consistently distinguish facts from hypotheses** — every
hypothesis and validated finding section carries its `truth_label`
(`01_PRODUCT_SPEC.md` §14) and never blends the two.

## Evidence Traceability

Every reported claim must be traceable back through this chain:

```text
Task
 ↓
Tool Run
 ↓
Observation
 ↓
Evidence
 ↓
AI Analysis
 ↓
Hypothesis
 ↓
Next Task
```

A report reader should always be able to answer: *why did ARGUS investigate this?*, *what
evidence caused this hypothesis?*, *which tool produced the original observation?*, and *which
AI analysis created the next task?* See `05_DATA_MODEL.md` `evidence` table and
`ai_analysis` table.

## Relationship to Other Documents

- `05_DATA_MODEL.md` — the tables (`evidence`, `hypotheses`, `ai_analysis`, `tasks`,
  `tool_runs`) that this traceability chain is built from
- `07_AI_AGENTS.md` — `ReportAgent` is responsible for rendering these reports
- `04_SCOPE_SAFETY.md` — reports must never present a hypothesis as a validated finding without
  the human/safe-validation step having occurred
