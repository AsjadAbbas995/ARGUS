# ARGUS Data Model

PostgreSQL is the **authoritative source of truth** for ARGUS. AI memory and the attack-surface
graph are views/derivations over this data — they are never authoritative themselves. Future
graph functionality (e.g. Neo4j) is optional and additive; PostgreSQL remains the initial and
primary source of truth.

Every table below is documented as: **Purpose, Columns, Primary Key, Foreign Keys, Indexes,
Unique Constraints, Relationships, Lifecycle, Example Record.**

---

## organizations

**Purpose:** The top-level authorized client/target owner.
| Column | Type | Notes |
|---|---|---|
| id | uuid | primary key |
| name | text | organization name |
| created_at | timestamptz | |
**Primary key:** `id`. **Foreign keys:** none. **Indexes:** `name`. **Unique:** `name`.
**Relationships:** has many `programs`. **Lifecycle:** created once at onboarding, rarely
updated. **Example:** `{id: ..., name: "Acme Corp"}`.

## programs

**Purpose:** A specific authorized engagement/bug-bounty program under an organization.
| Column | Type | Notes |
|---|---|---|
| id | uuid | primary key |
| organization_id | uuid | FK → organizations |
| name | text | program name |
| status | text | active / paused / closed |
**Primary key:** `id`. **Foreign keys:** `organization_id → organizations.id`. **Indexes:**
`organization_id`. **Unique:** `(organization_id, name)`. **Relationships:** has many
`runs`, `scope_rules`, `assets`, `tasks`, `tool_runs`. **Lifecycle:** created at engagement
start, closed at engagement end. **Example:** `{id: ..., organization_id: ..., name: "Q4
Pentest", status: "active"}`.

## runs

**Purpose:** The top-level execution record for one reconnaissance engagement under a program.
The orchestrator advances a run through the run state machine (`08_ORCHESTRATOR.md` §Run State
Machine). A run owns all tasks; tasks own tool runs; tool runs produce evidence.
| Column | Type | Notes |
|---|---|---|
| id | uuid | primary key |
| program_id | uuid | FK → programs |
| status | text | CREATED / VALIDATING / INITIALIZING / RECONNING / ANALYZING / PLANNING / EXECUTING / CORRELATING / PRIORITIZING / WAITING_FOR_NEXT_TASK / COMPLETED / FAILED / CANCELLED |
| target | text | canonical target string (e.g. root domain) the run is scoped to |
| configuration_snapshot | jsonb | program/tool config captured at run creation for auditability |
| started_at | timestamptz | null until first execution begins |
| completed_at | timestamptz | null until terminal state |
| created_at | timestamptz | |
| updated_at | timestamptz | |
**Primary key:** `id`. **Foreign keys:** `program_id → programs.id`. **Indexes:** `program_id`,
`(program_id, status)`. **Unique:** none. **Relationships:** belongs to `programs`; has many
`tasks` (`tasks.run_id → runs.id`); has many `tool_runs` indirectly via its tasks. **Lifecycle:**
created by the CLI/API at intake (`03_RECON_PIPELINE.md` §2), advanced through the run state
machine by the Orchestrator, terminal on COMPLETED / FAILED / CANCELLED; never deleted (audit
trail). **Example:** `{program_id: ..., status: "RECONNING", target: "example.com",
configuration_snapshot: {...}}`.

## scope_rules

**Purpose:** Deterministic authorization rules the Scope Guard evaluates against.
| Column | Type | Notes |
|---|---|---|
| id | uuid | primary key |
| program_id | uuid | FK → programs |
| rule_type | text | domain / subdomain / ip / cidr / port / exclusion |
| value | text | the actual pattern/value |
| allowed | boolean | true = allow, false = explicit exclusion |
**Primary key:** `id`. **Foreign keys:** `program_id → programs.id`. **Indexes:**
`(program_id, rule_type)`. **Unique:** `(program_id, rule_type, value)`. **Relationships:**
belongs to `programs`; referenced by every Scope Guard decision. **Lifecycle:** defined at intake,
may be amended by the operator only (never by AI). **Example:** `{rule_type: "domain", value:
"example.com", allowed: true}`.

## assets

**Purpose:** Canonical, deduplicated hostnames/domains discovered or provided for a program.
| Column | Type | Notes |
|---|---|---|
| id | uuid | primary key |
| program_id | uuid | FK → programs |
| hostname | text | normalized (lowercase, no trailing dot) |
| source | text | subfinder / amass / crt / manual / etc. |
| discovered_at | timestamptz | |
**Primary key:** `id`. **Foreign keys:** `program_id → programs.id`. **Indexes:** `hostname`.
**Unique:** `(program_id, hostname)`. **Relationships:** has many `asset_ips`,
`asset_technologies`; parent of `web_apps`. **Lifecycle:** created on first discovery, never
duplicated (normalization enforces this). **Example:** `{hostname: "app.example.com", source:
"subfinder"}`.

## dns_records

**Purpose:** Structured DNS resolution results per asset.
| Column | Type | Notes |
|---|---|---|
| id | uuid | primary key |
| asset_id | uuid | FK → assets |
| record_type | text | A / AAAA / CNAME / MX / NS / TXT |
| value | text | record value |
| resolved_at | timestamptz | |
**Primary key:** `id`. **Foreign keys:** `asset_id → assets.id`. **Indexes:**
`(asset_id, record_type)`. **Unique:** none (multiple records per type possible).
**Relationships:** belongs to `assets`; correlates to `ips` for A/AAAA records. **Lifecycle:**
appended each resolution pass; historical records retained, not overwritten. **Example:**
`{record_type: "A", value: "203.0.113.10"}`.

## ips

**Purpose:** Canonical IP addresses observed during recon.
| Column | Type | Notes |
|---|---|---|
| id | uuid | primary key |
| address | inet | IP address |
| first_seen | timestamptz | |
**Primary key:** `id`. **Foreign keys:** none. **Indexes:** `address`. **Unique:** `address`.
**Relationships:** many-to-many with `assets` via `asset_ips`; has many `ports`. **Lifecycle:**
created on first sighting, shared across assets. **Example:** `{address: "203.0.113.10"}`.

## asset_ips

**Purpose:** Many-to-many join between `assets` and `ips`.
| Column | Type | Notes |
|---|---|---|
| asset_id | uuid | FK → assets |
| ip_id | uuid | FK → ips |
| observed_at | timestamptz | |
**Primary key:** `(asset_id, ip_id)`. **Foreign keys:** `asset_id → assets.id`,
`ip_id → ips.id`. **Indexes:** both FK columns. **Unique:** the composite primary key itself.
**Relationships:** join table. **Lifecycle:** appended as new correlations are observed.
**Example:** `{asset_id: ..., ip_id: ...}`.

## ports

**Purpose:** Open/closed/filtered port state per IP.
| Column | Type | Notes |
|---|---|---|
| id | uuid | primary key |
| ip_id | uuid | FK → ips |
| port_number | integer | |
| protocol | text | tcp / udp |
| state | text | open / closed / filtered |
| service | text | service name (e.g. "http", "ssh"), nullable |
| version | text | service version banner, nullable |
**Primary key:** `id`. **Foreign keys:** `ip_id → ips.id`. **Indexes:** `(ip_id, port_number)`.
**Unique:** `(ip_id, port_number, protocol)`. **Relationships:** belongs to `ips`; may have one
`web_apps` row when an HTTP(S) service is probed. Service/version are stored as columns here,
not in a separate `services` table. **Lifecycle:**
updated per scan; state changes over time are historically valuable and may be versioned.
**Example:** `{port_number: 443, protocol: "tcp", state: "open"}`.

## technologies

**Purpose:** Canonical technology catalog (frameworks, CMSs, clouds, CDNs, WAFs, etc.).
| Column | Type | Notes |
|---|---|---|
| id | uuid | primary key |
| name | text | e.g. "React", "GraphQL", "Cloudflare" |
| category | text | framework / cms / api_technology / cdn / waf / cloud / auth / other |
**Primary key:** `id`. **Foreign keys:** none. **Indexes:** `name`. **Unique:** `name`.
**Relationships:** many-to-many with `assets`/`web_apps` via `asset_technologies`. **Lifecycle:**
seeded/extended as new signatures are added. **Example:** `{name: "GraphQL", category:
"api_technology"}`.

## asset_technologies

**Purpose:** Many-to-many join between assets and detected technologies, with evidence.
| Column | Type | Notes |
|---|---|---|
| asset_id | uuid | FK → assets |
| technology_id | uuid | FK → technologies |
| confidence | numeric | 0.0–1.0 |
| evidence_id | uuid | FK → evidence |
**Primary key:** `(asset_id, technology_id)`. **Foreign keys:** as listed. **Indexes:** both
FK columns. **Unique:** composite primary key. **Relationships:** join table linked to
`evidence`. **Lifecycle:** appended/updated as fingerprinting improves confidence. **Example:**
`{asset_id: ..., technology_id: ..., confidence: 0.9}`.

## web_apps

**Purpose:** A live web application observed on an asset/port.
| Column | Type | Notes |
|---|---|---|
| id | uuid | primary key |
| asset_id | uuid | FK → assets |
| port_id | uuid | FK → ports |
| status_code | integer | |
| title | text | |
| server_header | text | |
**Primary key:** `id`. **Foreign keys:** `asset_id → assets.id`, `port_id → ports.id`.
**Indexes:** `asset_id`. **Unique:** `(asset_id, port_id)`. **Relationships:** parent of `urls`.
**Lifecycle:** created on first successful HTTP probe, refreshed on subsequent probes.
**Example:** `{status_code: 200, title: "Acme App", server_header: "nginx"}`.

## urls

**Purpose:** Individual URLs discovered via crawling, content discovery, or historical recon.
| Column | Type | Notes |
|---|---|---|
| id | uuid | primary key |
| web_app_id | uuid | FK → web_apps |
| path | text | |
| source | text | katana / ffuf / feroxbuster / gau / wayback |
| historical | boolean | true if from a historical source, not yet re-verified live |
**Primary key:** `id`. **Foreign keys:** `web_app_id → web_apps.id`. **Indexes:**
`(web_app_id, path)`. **Unique:** `(web_app_id, path)`. **Relationships:** parent of
`endpoints`. **Lifecycle:** created on discovery; `historical` flips to false only after a fresh
liveness check. **Example:** `{path: "/api/users", source: "katana", historical: false}`.

## endpoints

**Purpose:** A normalized API/application endpoint derived from one or more `urls`.
| Column | Type | Notes |
|---|---|---|
| id | uuid | primary key |
| url_id | uuid | FK → urls |
| method | text | GET / POST / etc. |
| pattern | text | e.g. "/api/users/{id}" |
**Primary key:** `id`. **Foreign keys:** `url_id → urls.id`. **Indexes:** `pattern`. **Unique:**
`(url_id, method, pattern)`. **Relationships:** has many `parameters`; linked to `apis`,
`auth_mechanisms`, `hypotheses`. **Lifecycle:** created/merged as multiple sources confirm the
same pattern. **Example:** `{method: "GET", pattern: "/api/users/{id}"}`.

## parameters

**Purpose:** A parameter observed on an endpoint (query, body, header, path).
| Column | Type | Notes |
|---|---|---|
| id | uuid | primary key |
| endpoint_id | uuid | FK → endpoints |
| name | text | |
| location | text | query / body / header / path |
| significance | text | object_id / pagination / filter / sort / unknown |
**Primary key:** `id`. **Foreign keys:** `endpoint_id → endpoints.id`. **Indexes:**
`(endpoint_id, name)`. **Unique:** `(endpoint_id, name, location)`. **Relationships:** belongs to
`endpoints`; referenced by `hypotheses`. **Lifecycle:** created on discovery; `significance`
refined as intelligence improves. **Example:** `{name: "id", location: "path", significance:
"object_id"}`.

## javascript_files

**Purpose:** JavaScript assets discovered via crawling, with extraction results.
| Column | Type | Notes |
|---|---|---|
| id | uuid | primary key |
| web_app_id | uuid | FK → web_apps |
| url | text | |
| has_source_map | boolean | |
**Primary key:** `id`. **Foreign keys:** `web_app_id → web_apps.id`. **Indexes:** `url`.
**Unique:** `(web_app_id, url)`. **Relationships:** source of extracted `endpoints`, `apis`,
`websocket_endpoints`. **Lifecycle:** created on discovery, re-parsed if content changes.
**Example:** `{url: "https://app.example.com/app.js", has_source_map: true}`.

## apis

**Purpose:** A logical API surface (REST, GraphQL, or otherwise) grouping related endpoints.
| Column | Type | Notes |
|---|---|---|
| id | uuid | primary key |
| web_app_id | uuid | FK → web_apps |
| api_type | text | rest / graphql / websocket |
| documented | boolean | true if OpenAPI/Swagger source confirmed |
**Primary key:** `id`. **Foreign keys:** `web_app_id → web_apps.id`. **Indexes:** `api_type`.
**Unique:** none beyond primary key. **Relationships:** has many `endpoints`,
`graphql_operations`, `auth_mechanisms`. **Lifecycle:** created when API presence is confirmed.
**Example:** `{api_type: "rest", documented: true}`.

## graphql_operations

**Purpose:** Individual GraphQL queries/mutations/subscriptions discovered for an API.
| Column | Type | Notes |
|---|---|---|
| id | uuid | primary key |
| api_id | uuid | FK → apis |
| operation_type | text | query / mutation / subscription |
| name | text | |
**Primary key:** `id`. **Foreign keys:** `api_id → apis.id`. **Indexes:**
`(api_id, operation_type)`. **Unique:** `(api_id, operation_type, name)`. **Relationships:**
belongs to `apis`; linked to `parameters` via associated `endpoints` where applicable.
**Lifecycle:** created from introspection/JS extraction. **Example:** `{operation_type: "query",
name: "getUserProfile"}`.

## websocket_endpoints

**Purpose:** WebSocket endpoints and their observed relationships.
| Column | Type | Notes |
|---|---|---|
| id | uuid | primary key |
| web_app_id | uuid | FK → web_apps |
| url | text | ws:// or wss:// |
| auth_mechanism_id | uuid | FK → auth_mechanisms, nullable |
**Primary key:** `id`. **Foreign keys:** `web_app_id → web_apps.id`,
`auth_mechanism_id → auth_mechanisms.id`. **Indexes:** `url`. **Unique:** `(web_app_id, url)`.
**Relationships:** belongs to `web_apps`; may link to `auth_mechanisms`. The connection to the
discovering `javascript_files` entry is a derived graph edge (see Graph Relationships below),
not a stored foreign key. **Lifecycle:** created on
discovery. **Example:** `{url: "wss://app.example.com/socket"}`.

## auth_mechanisms

**Purpose:** Observed authentication mechanisms for an application/API.
| Column | Type | Notes |
|---|---|---|
| id | uuid | primary key |
| web_app_id | uuid | FK → web_apps |
| mechanism_type | text | cookie / bearer / oauth / api_key / jwt / other |
| details | jsonb | header names, cookie names, flow info |
**Primary key:** `id`. **Foreign keys:** `web_app_id → web_apps.id`. **Indexes:**
`mechanism_type`. **Unique:** none. **Relationships:** referenced by `endpoints`,
`websocket_endpoints`, `hypotheses`. **Lifecycle:** created/updated as new evidence appears.
**Example:** `{mechanism_type: "bearer", details: {"header": "Authorization"}}`.

## hypotheses

**Purpose:** AI-generated, evidence-linked, unconfirmed potential issues.
| Column | Type | Notes |
|---|---|---|
| id | uuid | primary key |
| endpoint_id | uuid | FK → endpoints, nullable |
| statement | text | the hypothesis text |
| truth_label | text | HYPOTHESIS / UNVERIFIED_CLAIM / VALIDATED_FINDING |
| confidence | numeric | 0.0–1.0 |
| severity | text | low / medium / high; potential impact if eventually confirmed |
| priority | text | low / medium / high; how urgently to investigate |
| status | text | open / validated / rejected |
**Primary key:** `id`. **Foreign keys:** `endpoint_id → endpoints.id`. **Indexes:**
`(truth_label, status)`. **Unique:** none. **Relationships:** linked to `evidence`;
generated by `ai_analysis`. **Lifecycle:** created by AI agents, transitions to
`VALIDATED_FINDING` only via human/safe validation. **Example:** `{statement: "Potential
object-level authorization weakness on /api/users/{id}", truth_label: "HYPOTHESIS", priority:
"high", confidence: 0.4}`.

## evidence

**Purpose:** The traceable link between a tool run/observation and any downstream claim.
| Column | Type | Notes |
|---|---|---|
| id | uuid | primary key |
| tool_run_id | uuid | FK → tool_runs, nullable |
| entity_type | text | which table the evidence supports |
| entity_id | uuid | polymorphic reference |
| raw_reference | text | pointer into storage/raw or storage/evidence |
**Primary key:** `id`. **Foreign keys:** `tool_run_id → tool_runs.id`. **Indexes:**
`(entity_type, entity_id)`. **Unique:** none. **Relationships:** referenced by nearly every
other table (`asset_technologies`, `hypotheses`, `ai_analysis`, etc.). **Lifecycle:** created
whenever a tool run or AI analysis produces something worth citing; never deleted (audit trail).
**Example:** `{entity_type: "hypothesis", entity_id: ..., raw_reference:
"storage/raw/js/app.js"}`.

## tasks

**Purpose:** A structured unit of reconnaissance work, human- or AI-proposed.
| Column | Type | Notes |
|---|---|---|
| id | uuid | primary key |
| run_id | uuid | FK → runs |
| type | text | task type (e.g. "subdomain_discovery", "js_analysis") |
| target | text | |
| parent_task_id | uuid | FK → tasks, nullable |
| priority | numeric | computed score |
| status | text | pending / running / completed / failed / skipped / cancelled |
| fingerprint | text | deterministic dedup key |
| reason | text | why the task was created (triggering observation/task); nullable |
| created_at | timestamptz | |
| started_at | timestamptz | |
| completed_at | timestamptz | |
**Primary key:** `id`. **Foreign keys:** `run_id → runs.id`, `parent_task_id → tasks.id`.
**Indexes:** `fingerprint`, `(run_id, status)`. **Unique:** `fingerprint` (per run).
**Relationships:** belongs to `runs` (via `run_id`); has many `tool_runs`; may have child tasks
via `parent_task_id`. **Lifecycle:** full task state machine per `08_ORCHESTRATOR.md` §Task
Queue; a task never references `tool_runs` directly as a parent. **Example:** `{run_id: ...,
type: "js_analysis", target: "https://example.com/app.js", status: "pending", priority: 0.82}`.

## tool_runs

**Purpose:** A single execution of a tool adapter for a task.
| Column | Type | Notes |
|---|---|---|
| id | uuid | primary key |
| task_id | uuid | FK → tasks |
| tool_name | text | |
| command | text[] | argument array actually executed |
| exit_code | integer | |
| started_at / completed_at | timestamptz | |
| raw_output_ref | text | pointer into storage/raw |
**Primary key:** `id`. **Foreign keys:** `task_id → tasks.id`. **Indexes:**
`(tool_name, task_id)`. **Unique:** none. **Relationships:** parent of `evidence` records.
**Lifecycle:** created at execution start, finalized at completion/failure. **Example:**
`{tool_name: "subfinder", exit_code: 0}`.

## ai_analysis

**Purpose:** A single AI agent invocation and its structured output.
| Column | Type | Notes |
|---|---|---|
| id | uuid | primary key |
| agent_name | text | ReconAgent / APIAgent / JSAgent / etc. |
| model_used | text | local / cloud model identifier |
| input_context_ref | text | pointer to the context supplied |
| output | jsonb | structured agent output |
| created_at | timestamptz | |
**Primary key:** `id`. **Foreign keys:** none direct (referenced *by* `hypotheses`/`tasks` via
`evidence`). **Indexes:** `agent_name`. **Unique:** none. **Relationships:** may generate
`hypotheses` and new `tasks`. **Lifecycle:** immutable once written (audit trail). **Example:**
`{agent_name: "AuthZAgent", model_used: "cloud", output: {...}}`.

---

## Authoritative Lifecycle Hierarchy

```text
organizations → programs → runs → tasks → tool_runs → evidence
```

`runs` is the top-level execution record for one engagement. `tasks` are units of work within a
run; `tool_runs` are executions of a tool adapter for a task; `evidence` and observation records
attach to tool runs. Tasks belong to runs via `tasks.run_id → runs.id`; tool runs belong to
tasks via `tool_runs.task_id → tasks.id`. This is the single, authoritative parent chain.

## Graph Relationships (Cross-Entity)

```text
Domain → Subdomain → IP → Port → Service → Web Application → URL → Endpoint → Parameter
Endpoint → Object
Endpoint → Authentication
JavaScript → Endpoint
JavaScript → API
API → Authentication
Certificate → Domain
```

These edges are computed views over the tables above (`correlation/asset_graph.py`,
`correlation/endpoint_graph.py`) — see `03_RECON_PIPELINE.md` §25.

## Important Decision

PostgreSQL is the initial and authoritative graph/data store. Neo4j or another dedicated graph
database is optional future functionality layered on top, never a replacement for PostgreSQL as
source of truth.
