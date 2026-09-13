# ARGUS Reconnaissance Pipeline

This is the reconnaissance knowledge base: every stage ARGUS can perform, documented so both
humans and AI coding agents know what each stage consumes, produces, and is bounded by. Each
stage below follows the same template: **Purpose, Inputs, Tools, Execution Conditions, Expected
Outputs, Normalized Data, Database Entities, Evidence Generated, Possible Discoveries, Follow-Up
Tasks, Dependencies, Safety Considerations, Failure Conditions.**

---

## 1. Recon Philosophy

**Purpose:** Establish the operating principle for every stage below: deterministic tools
collect facts; AI interprets facts; nothing is reported as true without evidence.
**Inputs:** N/A (governing principle). **Tools:** N/A.
**Execution conditions:** Applies to every stage in this document.
**Expected outputs:** A shared vocabulary (`FACT`/`OBSERVATION`/`INFERENCE`/`HYPOTHESIS`/
`UNVERIFIED_CLAIM`) used consistently across all stages — see `01_PRODUCT_SPEC.md` §14.
**Normalized data / DB entities / Evidence generated:** N/A at this level; every stage below
produces these concretely. **Possible discoveries / Follow-up tasks:** N/A.
**Dependencies:** None — this is the root principle. **Safety considerations:** Discovery is
never treated as exploitation (`73` in the source brief / `04_SCOPE_SAFETY.md`).
**Failure conditions:** A stage that violates this philosophy (fabricates, over-claims) is a
defect regardless of how useful its output looks.

## 2. Initial Target Intake

**Purpose:** Accept an operator-supplied target and scope definition and prepare a validated run.
**Inputs:** Root domain(s), allowed subdomains/IPs/CIDRs/ports, exclusions, program rules.
**Tools:** CLI/API intake layer. **Execution conditions:** Always runs first for a new run.
**Expected outputs:** A `run` record with a validated, normalized scope attached.
**Normalized data:** Canonical scope rule set. **DB entities:** `organizations`, `programs`,
`runs`, `scope_rules`. **Evidence generated:** Intake/validation log entry.
**Possible discoveries:** Malformed or ambiguous scope definitions. **Follow-up tasks:**
Subdomain discovery, DNS enumeration. **Dependencies:** None.
**Safety considerations:** The Scope Guard must validate scope before any other stage runs
(`04_SCOPE_SAFETY.md`). **Failure conditions:** Invalid/unauthorized scope → run rejected, not
silently narrowed.

## 3. Subdomain Discovery

**Purpose:** Enumerate subdomains belonging to in-scope root domains.
**Inputs:** In-scope root domain(s). **Tools:** Subfinder, Amass, Assetfinder.
**Execution conditions:** Runs after intake, before DNS resolution.
**Expected outputs:** Raw candidate subdomain lists per source.
**Normalized data:** Deduplicated, case/trailing-dot-normalized subdomain assets (e.g.
`www.example.com`, `WWW.example.com`, `www.example.com.` → one asset).
**DB entities:** `assets`. **Evidence generated:** Tool run + raw output per source.
**Possible discoveries:** Unexpected or forgotten subdomains. **Follow-up tasks:** DNS
resolution, HTTP probing for each new asset. **Dependencies:** Target Intake.
**Safety considerations:** Discovery sources must stay within allowed passive/active rules.
**Failure conditions:** A missing tool logs a warning and discovery continues with the sources
that are available (`37` in the source brief).

## 4. Certificate Transparency

**Purpose:** Discover subdomains/hostnames via CT logs.
**Inputs:** In-scope root domain(s). **Tools:** `crt.py` adapter (CT log query).
**Execution conditions:** Runs alongside other subdomain discovery sources.
**Expected outputs:** Hostnames observed in issued certificates.
**Normalized data:** Deduplicated hostname assets; certificate → domain relationship.
**DB entities:** `assets`, plus certificate metadata associated with `ips`/`assets`.
**Evidence generated:** Raw CT query result. **Possible discoveries:** Hostnames not found by
active enumeration. **Follow-up tasks:** DNS resolution for newly discovered hostnames.
**Dependencies:** Target Intake. **Safety considerations:** Passive-only, low-risk source.
**Failure conditions:** CT source unavailable → log and continue.

## 5. DNS Enumeration

**Purpose:** Resolve discovered assets to DNS records and correlate to IPs.
**Inputs:** Normalized subdomain assets. **Tools:** DNS resolver adapter.
**Execution conditions:** Runs after subdomain discovery for each new asset.
**Expected outputs:** A/AAAA/CNAME/MX/NS/TXT and other relevant records per asset.
**Normalized data:** `Subdomain → DNS record → IP` structured records (not raw-only).
**DB entities:** `dns_records`, `ips`, `asset_ips`. **Evidence generated:** Resolver tool run
per asset. **Possible discoveries:** CNAME chains to third-party services, unexpected IP ranges.
**Follow-up tasks:** Port scanning of resolved IPs, scope re-check if resolution leaves scope.
**Dependencies:** Subdomain Discovery / Certificate Transparency.
**Safety considerations:** Resolution to an out-of-scope IP must trigger a scope re-check before
any further action (`04_SCOPE_SAFETY.md` §Redirect/DNS Safety). **Failure conditions:** NXDOMAIN
or resolution failure is recorded, not silently dropped.

## 6. IP Correlation

**Purpose:** Correlate resolved IPs across multiple hostnames/assets.
**Inputs:** DNS records. **Tools:** Internal correlation logic (no external tool).
**Execution conditions:** Runs after DNS Enumeration.
**Expected outputs:** IP-to-asset relationship map, shared-hosting detection.
**Normalized data:** `asset_ips` relationships. **DB entities:** `ips`, `asset_ips`.
**Evidence generated:** Derived from DNS evidence (no new tool run). **Possible discoveries:**
Shared infrastructure across otherwise-unrelated domains. **Follow-up tasks:** Port scanning per
unique IP (deduplicated). **Dependencies:** DNS Enumeration.
**Safety considerations:** Shared IPs hosting out-of-scope domains must not extend scope.
**Failure conditions:** Ambiguous many-to-many mappings are stored explicitly, not collapsed.

## 7. Port Scanning

**Purpose:** Identify open ports/services on in-scope, resolved IPs.
**Inputs:** In-scope IPs. **Tools:** Nmap.
**Execution conditions:** Configured port range (default `1–1000`); never scans outside scope.
**Expected outputs:** Open/closed/filtered port states with service/version where available.
**Normalized data:** Port + protocol + service + version + state. **DB entities:** `ports`.
**Evidence generated:** Nmap tool run + raw output. **Possible discoveries:** Unexpected
services, management interfaces. **Follow-up tasks:** Service enumeration, HTTP probing for
web-looking ports. **Dependencies:** DNS Enumeration / IP Correlation.
**Safety considerations:** Strict adherence to configured port range and rate limits; no
scanning beyond the authorized range (`12` in the source brief). **Failure conditions:** Scan
timeout/instability → back off per `04_SCOPE_SAFETY.md` §Target Instability.

## 8. Service Enumeration

**Purpose:** Identify the service and version bound to each open port.
**Inputs:** Open ports. **Tools:** Nmap service/version detection.
**Execution conditions:** Runs immediately after Port Scanning for each open port.
**Expected outputs:** Service name, version banner where available.
**Normalized data:** service/version columns on `ports`. **DB entities:** `ports` (service/version
columns — see `05_DATA_MODEL.md`). **Evidence generated:** Service-detection tool run.
**Possible discoveries:** Outdated or unusual service versions. **Follow-up tasks:** HTTP
probing for web services, deeper protocol-specific analysis for non-HTTP services.
**Dependencies:** Port Scanning. **Safety considerations:** Passive/banner-based only; no
active exploitation of the service. **Failure conditions:** Unidentifiable service → recorded
as `unknown`, not guessed.

## 9. HTTP/HTTPS Probing

**Purpose:** Identify live web hosts and capture response metadata.
**Inputs:** Resolved IPs/hostnames with web-plausible ports. **Tools:** httpx.
**Execution conditions:** Runs after DNS/port information is available.
**Expected outputs:** Live-host status, status codes, redirects, titles, server headers,
technologies, content types. **Normalized data:** `web_apps` records.
**DB entities:** `web_apps`. **Evidence generated:** httpx tool run + raw response metadata.
**Possible discoveries:** Redirect chains leaving scope, unexpected virtual hosts.
**Follow-up tasks:** Technology fingerprinting, web crawling, content discovery.
**Dependencies:** DNS Enumeration, Port Scanning. **Safety considerations:** Redirect
destinations must be scope-checked before further interaction (`04_SCOPE_SAFETY.md`).
**Failure conditions:** Connection failure recorded per host; does not halt the run.

## 10. Technology Fingerprinting

**Purpose:** Identify web servers, frameworks, CMSs, JS frameworks, CDNs, WAFs, cloud providers,
auth systems, and API technologies in use.
**Inputs:** HTTP probe results. **Tools:** httpx technology detection, header/body heuristics.
**Execution conditions:** Runs alongside/after HTTP Probing.
**Expected outputs:** A technology tag set per web application (e.g. `React`, `GraphQL`).
**Normalized data:** `technologies`, `asset_technologies`. **DB entities:** `technologies`,
`asset_technologies`. **Evidence generated:** Fingerprint match evidence (header/body signature).
**Possible discoveries:** Technology-specific attack surface (e.g. GraphQL present → GraphQL
recon becomes higher priority). **Follow-up tasks:** Technology-specific recon tasks (e.g. React
→ prioritize JS analysis). **Dependencies:** HTTP/HTTPS Probing.
**Safety considerations:** Fingerprinting is passive/observational only.
**Failure conditions:** Ambiguous fingerprints are stored with lower confidence, not asserted.

## 11. Web Crawling

**Purpose:** Discover URLs, paths, parameters, forms, and linked JavaScript/API paths.
**Inputs:** Live web applications. **Tools:** Katana.
**Execution conditions:** Runs after HTTP Probing confirms a live web app.
**Expected outputs:** Crawled URL set, discovered forms, linked JS files.
**Normalized data:** `urls`, `endpoints`, `parameters`, `javascript_files`.
**DB entities:** `urls`, `endpoints`, `parameters`, `javascript_files`. **Evidence generated:**
Katana tool run + raw crawl output. **Possible discoveries:** New in-scope subdomains reached via
links (must re-enter Scope Guard). **Follow-up tasks:** Content discovery, JavaScript analysis,
API discovery. **Dependencies:** HTTP/HTTPS Probing. **Safety considerations:** Any
newly-discovered domain from a link must pass the Scope Guard before being crawled itself.
**Failure conditions:** Crawl depth/time limits are respected; partial results are still stored.

## 12. Content Discovery

**Purpose:** Discover hidden directories, files, admin paths, and forgotten functionality.
**Inputs:** Live web applications. **Tools:** FFUF, Feroxbuster.
**Execution conditions:** Runs after HTTP Probing / Web Crawling.
**Expected outputs:** Discovered paths with status codes. **Normalized data:** `urls`,
`endpoints`. **DB entities:** `urls`, `endpoints`. **Evidence generated:** Fuzzer tool run + raw
output. **Possible discoveries:** Admin paths, backup-like paths, API routes not linked from the
UI. **Follow-up tasks:** API discovery, authorization intelligence for sensitive-looking paths.
**Dependencies:** HTTP/HTTPS Probing. **Safety considerations:** Wordlist size, concurrency, and
request rate must respect the Rate Limiter; discovery must never be treated as confirmation of a
vulnerability (`16` in the source brief). **Failure conditions:** Target instability during
fuzzing → reduce concurrency or stop per `04_SCOPE_SAFETY.md`.

## 13. Historical Recon

**Purpose:** Discover URLs/paths that may no longer be directly linked.
**Inputs:** In-scope domains. **Tools:** GAU, Wayback.
**Execution conditions:** Runs independently of live crawling; passive.
**Expected outputs:** Historical URL list, explicitly flagged as historical.
**Normalized data:** `urls` marked with a historical/inactive flag. **DB entities:** `urls`.
**Evidence generated:** Historical-source tool run. **Possible discoveries:** Old API versions,
deprecated routes, legacy parameters, forgotten applications. **Follow-up tasks:** HTTP probing
to verify current liveness of historical URLs before treating them as active.
**Dependencies:** Target Intake (no live host required). **Safety considerations:** Passive-only.
**Failure conditions:** A historical URL must never be presented as currently active without a
fresh liveness check (`17` in the source brief).

## 14. JavaScript Analysis

**Purpose:** Extract endpoints, routes, parameters, domains, WebSocket URLs, API versions,
object identifiers, and token-like strings from JavaScript.
**Inputs:** JavaScript files discovered via crawling. **Tools:** Internal JS parser
(`intelligence/javascript.py`). **Execution conditions:** Runs after Web Crawling discovers JS
files. **Expected outputs:** Structured extraction results per file.
**Normalized data:** `endpoints`, `parameters`, `apis`, `websocket_endpoints` derived from JS.
**DB entities:** `javascript_files`, `endpoints`, `parameters`, `apis`, `websocket_endpoints`.
**Evidence generated:** Parsed-JS evidence linked to the source file. **Possible discoveries:**
Hidden/internal APIs, auth-related code, feature flags, token-like strings.
**Follow-up tasks:** API discovery/authorization analysis for newly found endpoints; source map
analysis if maps are exposed. **Dependencies:** Web Crawling. **Safety considerations:** A
token-like string is classified and investigated, never automatically reported as a confirmed
secret (`18` in the source brief). **Failure conditions:** Obfuscated/minified JS that cannot be
parsed is recorded as `UNKNOWN`, not guessed at.

## 15. Source Maps

**Purpose:** Recover original source structure where source maps are exposed.
**Inputs:** JavaScript files. **Tools:** Internal source-map parser.
**Execution conditions:** Runs when a `.map` file is discovered/referenced.
**Expected outputs:** Original file structure, comments, endpoint definitions where present.
**Normalized data:** Additional `endpoints`/`parameters` entries with a source-map provenance tag.
**DB entities:** `javascript_files`, `endpoints`. **Evidence generated:** Parsed source-map
evidence. **Possible discoveries:** Internal functionality, development paths, additional
configuration. **Follow-up tasks:** API discovery, authorization analysis on newly revealed
endpoints. **Dependencies:** JavaScript Analysis. **Safety considerations:** Discovery ≠
vulnerability — relevance is determined by AI reasoning with human validation, not asserted
automatically (`19` in the source brief). **Failure conditions:** Corrupt/partial maps are
parsed best-effort and marked incomplete.

## 16. API Discovery

**Purpose:** Identify REST APIs, undocumented endpoints, parameters, object identifiers, and
authentication mechanisms.
**Inputs:** Crawled URLs, JS-extracted endpoints, content-discovery results. **Tools:** Internal
API intelligence (`intelligence/api.py`). **Execution conditions:** Runs continuously as new
endpoint evidence appears. **Expected outputs:** A structured API surface map.
**Normalized data:** `apis`, `endpoints`, `parameters`. **DB entities:** `apis`, `endpoints`,
`parameters`. **Evidence generated:** Correlated evidence from crawling/JS/content-discovery.
**Possible discoveries:** Undocumented endpoints, object-based access patterns.
**Follow-up tasks:** OpenAPI/Swagger discovery, GraphQL/WebSocket recon, authorization analysis.
**Dependencies:** Web Crawling, JavaScript Analysis, Content Discovery.
**Safety considerations:** ARGUS only claims an endpoint exists when evidence confirms it
(`21` in the source brief). **Failure conditions:** Conflicting evidence about an endpoint's
existence is stored with both sources rather than resolved by guessing.

## 17. OpenAPI/Swagger

**Purpose:** Identify and parse API documentation/schemas.
**Inputs:** Discovered documentation paths (e.g. from Content Discovery). **Tools:** Internal
OpenAPI/Swagger parser. **Execution conditions:** Runs when a documentation path is confirmed
live. **Expected outputs:** Endpoints, methods, parameters, request/response structures, auth
schemes, object models. **Normalized data:** `apis`, `endpoints`, `parameters`,
`auth_mechanisms`. **DB entities:** same. **Evidence generated:** Parsed schema evidence.
**Possible discoveries:** Full API surface in one document, including undocumented-elsewhere
routes. **Follow-up tasks:** Authorization analysis for object-ID-bearing routes.
**Dependencies:** Content Discovery / API Discovery. **Safety considerations:** A documentation
path is only claimed to exist once evidence confirms it — no guessed common paths presented as
fact. **Failure conditions:** Malformed schema → parsed partially, gaps marked `UNKNOWN`.

## 18. GraphQL

**Purpose:** Identify GraphQL endpoints and collect operations/queries/mutations/subscriptions.
**Inputs:** Endpoints flagged as GraphQL by technology fingerprinting or JS analysis. **Tools:**
Internal GraphQL intelligence (`intelligence/graphql.py`). **Execution conditions:** Prioritized
when `Technology = GraphQL` is detected. **Expected outputs:** Operation list, object types,
parameters, schema info where available (e.g. via introspection if permitted by scope).
**Normalized data:** `graphql_operations`. **DB entities:** `graphql_operations`, `apis`.
**Evidence generated:** GraphQL probe/introspection evidence. **Possible discoveries:** Object
types exposing user/tenant identifiers. **Follow-up tasks:** Authorization analysis on object-ID
operations. **Dependencies:** API Discovery / Technology Fingerprinting. **Safety
considerations:** Introspection queries only, no mutation execution without explicit human
approval. **Failure conditions:** Introspection disabled → recorded as `UNKNOWN`, not inferred.

## 19. WebSockets

**Purpose:** Identify WebSocket endpoints and safely observable connection/message structure.
**Inputs:** WebSocket URLs from JS analysis or crawling. **Tools:** Internal WebSocket
intelligence (`intelligence/websocket.py`). **Execution conditions:** Runs when a `ws://`/`wss://`
reference is found. **Expected outputs:** Endpoint URL, channel names, auth relationship.
**Normalized data:** `websocket_endpoints`. **DB entities:** `websocket_endpoints`. **Evidence
generated:** Connection/handshake observation evidence. **Possible discoveries:** Auth tokens
passed over WebSocket handshakes. **Follow-up tasks:** Authentication intelligence.
**Dependencies:** JavaScript Analysis. **Safety considerations:** Passive observation only — no
message injection or protocol abuse without human approval. **Failure conditions:** Connection
refused/unreachable → recorded, not retried aggressively (rate-limited).

## 20. Authentication Intelligence

**Purpose:** Identify observable authentication mechanisms (cookies, bearer tokens, API keys,
OAuth/OIDC, sessions, JWT-like tokens, login/password-reset endpoints).
**Inputs:** HTTP responses, JS analysis, API/OpenAPI schemas. **Tools:** Internal
`intelligence/authentication.py`. **Execution conditions:** Runs continuously as auth-related
evidence appears. **Expected outputs:** Catalogued auth mechanisms per application.
**Normalized data:** `auth_mechanisms`. **DB entities:** `auth_mechanisms`. **Evidence
generated:** Header/cookie/response evidence. **Possible discoveries:** Multiple concurrent auth
schemes, weak-looking session handling. **Follow-up tasks:** Authorization intelligence.
**Dependencies:** HTTP Probing, API Discovery. **Safety considerations:** Observation only — no
automated login attempts, credential attacks, or session manipulation. **Failure conditions:**
Ambiguous auth scheme → recorded with lower confidence, not asserted.

## 21. Authorization Intelligence

**Purpose:** Identify endpoints involving user/account/organization/tenant/object/document/
resource/role identifiers and formulate access-control hypotheses.
**Inputs:** Endpoints/parameters from API Discovery, GraphQL, JS Analysis. **Tools:** Internal
authorization reasoning (AI `AuthZAgent`, see `07_AI_AGENTS.md`). **Execution conditions:** Runs
once object-identifier-bearing endpoints exist. **Expected outputs:** `HYPOTHESIS`-labeled
statements such as "potential object-level authorization weakness," never a confirmed finding.
**Normalized data:** `hypotheses` linked to `endpoints`/`parameters`. **DB entities:**
`hypotheses`, `evidence`. **Evidence generated:** Correlated endpoint/parameter evidence.
**Possible discoveries:** IDOR-shaped patterns, missing per-tenant checks (as hypotheses only).
**Follow-up tasks:** Human-approved safe validation. **Dependencies:** Parameter Intelligence,
API Discovery. **Safety considerations:** Never auto-exploits; always routes through
human-in-the-loop validation (`25` in the source brief, `04_SCOPE_SAFETY.md`). **Failure
conditions:** Insufficient evidence → hypothesis is not generated, or is generated with low
confidence and clearly marked `UNVERIFIED_CLAIM` where appropriate.

## 22. Parameter Intelligence

**Purpose:** Catalog URL/query/body/header/path parameters and their likely significance.
**Inputs:** Endpoints from crawling, content discovery, JS analysis, API/OpenAPI/GraphQL.
**Tools:** Internal `intelligence/parameters.py`. **Execution conditions:** Runs continuously
alongside endpoint discovery. **Expected outputs:** Parameter list with type/likely role (e.g.
object identifier, pagination, filter, sort). **Normalized data:** `parameters` linked to
`endpoints`. **DB entities:** `parameters`. **Evidence generated:** Parameter-extraction evidence.
**Possible discoveries:** Object-identifier parameters that should feed Authorization
Intelligence. **Follow-up tasks:** Authorization Intelligence prioritization.
**Dependencies:** Web Crawling, Content Discovery, JavaScript Analysis, API Discovery.
**Safety considerations:** Classification only, no automated parameter fuzzing for exploitation.
**Failure conditions:** Ambiguous parameter role stored as `unknown` significance.

## 23. Cloud Intelligence

**Purpose:** Identify cloud provider relationships and third-party service dependencies.
**Inputs:** DNS records, IP ranges, HTTP headers. **Tools:** Internal `intelligence/cloud.py`.
**Execution conditions:** Runs alongside DNS/HTTP analysis. **Expected outputs:** Cloud
provider tags per asset. **Normalized data:** `technologies`/`asset_technologies` entries tagged
as cloud infrastructure. **DB entities:** `technologies`, `asset_technologies`. **Evidence
generated:** IP-range/header-based match evidence. **Possible discoveries:** Shared cloud
tenancy, third-party service dependencies. **Follow-up tasks:** Scope re-verification if
infrastructure is shared with out-of-scope tenants. **Dependencies:** DNS Enumeration, HTTP
Probing. **Safety considerations:** Identification only — no attempt to access cloud management
planes. **Failure conditions:** Unrecognized provider → recorded as `unknown`.

## 24. CDN/WAF Intelligence

**Purpose:** Identify CDN, WAF, and load-balancer presence and origin indicators.
**Inputs:** HTTP headers, DNS records. **Tools:** Internal `intelligence/waf.py`, technology
fingerprinting. **Execution conditions:** Runs alongside HTTP Probing/Technology Fingerprinting.
**Expected outputs:** CDN/WAF/load-balancer tags, possible origin IP indicators.
**Normalized data:** `technologies`/`asset_technologies` entries. **DB entities:** same.
**Evidence generated:** Header/behavior-based match evidence. **Possible discoveries:** Origin
servers behind a CDN. **Follow-up tasks:** Scope-checked verification of origin IPs before any
direct interaction. **Dependencies:** HTTP Probing. **Safety considerations:** ARGUS must never
attempt to bypass a WAF or circumvent security controls (`27` in the source brief). **Failure
conditions:** Ambiguous CDN/WAF signature → recorded with lower confidence.

## 25. Attack-Surface Graph

**Purpose:** Represent all normalized reconnaissance data as a connected graph so AI can reason
across information no single tool understands independently.
**Inputs:** All normalized entities from stages above. **Tools:** `correlation/asset_graph.py`,
`correlation/endpoint_graph.py`. **Execution conditions:** Continuously updated as new data is
persisted. **Expected outputs:** A queryable graph spanning
`Organization → Domain → Subdomain → IP → Port → Service → Web Application → URL → Endpoint →
Parameter → API/Object/Authentication/Technology`, plus cross-links such as
`JavaScript → Endpoint`, `Certificate → Domain`, `API → Authentication`.
**Normalized data:** Graph edges over existing PostgreSQL entities (PostgreSQL is authoritative;
Neo4j is an optional future backend — see `05_DATA_MODEL.md`).
**DB entities:** Derived from all entities in `05_DATA_MODEL.md`. **Evidence generated:** N/A
directly — graph edges reference existing evidence. **Possible discoveries:** Cross-tool
correlations invisible to any single adapter. **Follow-up tasks:** Feeds AI Analysis directly.
**Dependencies:** All prior recon stages. **Safety considerations:** The graph is descriptive
only; it does not grant execution capability. **Failure conditions:** Orphaned/unlinkable
records are still stored, just without an edge, rather than dropped.

## 26. Correlation

**Purpose:** Cross-reference observations from multiple sources to produce inferences (e.g.
"the application appears to use object-based API access patterns").
**Inputs:** Attack-Surface Graph. **Tools:** `correlation/relationship_engine.py`,
`correlation/deduplication.py`. **Execution conditions:** Runs after each significant batch of
new evidence. **Expected outputs:** `INFERENCE`-labeled statements grounded in cited evidence.
**Normalized data:** Derived relationships, deduplicated entities. **DB entities:**
`ai_analysis` records referencing source evidence. **Evidence generated:** Correlation results
tied to source evidence IDs. **Possible discoveries:** Patterns spanning JS + API + Auth data.
**Follow-up tasks:** Hypothesis generation (AuthZAgent, HypothesisAgent). **Dependencies:**
Attack-Surface Graph. **Safety considerations:** Correlation produces inferences, not findings.
**Failure conditions:** Insufficient supporting evidence → no inference is asserted.

## 27. Adaptive Recon Loop

**Purpose:** Continuously convert AI analysis into new, scope-checked reconnaissance tasks.
**Inputs:** Hypotheses/inferences from Correlation and AI Analysis. **Tools:**
`core/task_planner.py`, `core/orchestrator.py`. **Execution conditions:** Runs after every
Analysis/Correlation pass, for the lifetime of the run.
**Expected outputs:** New `tasks` prioritized by expected value, confidence, novelty, relevance,
and cost (see `08_ORCHESTRATOR.md` §Task Scoring). **Normalized data:** `tasks` table entries.
**DB entities:** `tasks`. **Evidence generated:** Task-creation log entry citing the triggering
analysis. **Possible discoveries:** N/A directly — this stage generates work, not findings.
**Follow-up tasks:** Whatever the Task Planner proposes, always subject to the Scope Guard.
**Dependencies:** Correlation, AI Analysis. **Safety considerations:** Every generated task
passes the Scope Guard before execution; deduplication (`08_ORCHESTRATOR.md` §Task
Deduplication) prevents infinite loops. **Failure conditions:** No further worthwhile tasks,
budget/time exhaustion, user cancellation, or an instability/safety limit ends the loop
gracefully (`01_PRODUCT_SPEC.md` §10).
