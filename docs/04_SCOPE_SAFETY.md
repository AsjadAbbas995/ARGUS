# ARGUS Scope & Safety

This is the most important document in the ARGUS specification. It defines what ARGUS is
**allowed** to do. If any other document conflicts with this one, this document wins — see
`OPENCODE.md` for the precedence rule.

## Scope Model

The scope system understands:

- Allowed domains and subdomains
- Allowed IPs and CIDR ranges
- Excluded assets
- Allowed ports and protocols
- Rate limits (global, per-host, per-tool)
- Active vs. passive recon rules

Scope is defined per `programs` and stored as `scope_rules` (`05_DATA_MODEL.md`).

## Safety Architecture

```text
AI
 ↓
Proposed Task
 ↓
Task Planner
 ↓
Scope Guard
 ↓
Rate Limiter
 ↓
Tool Adapter
 ↓
Tool Runner
 ↓
Target
```

**Never:** `AI → Shell → Target`. This separation is one of the most important architectural
security controls in ARGUS and must never be bypassed for convenience, performance, or feature
requests.

## Deterministic Enforcement

The Scope Guard is deterministic — it evaluates fixed rules, not AI judgment. The AI cannot:

- Change scope
- Disable rate limiting
- Bypass safety checks
- Execute arbitrary commands
- Approve its own sensitive validation steps

If the AI proposes `https://outside-scope.example`, the Scope Guard rejects it and logs the
rejection. This applies identically whether the proposal came from a human-authored task or an
AI-generated one.

## When Scope Must Be Re-Checked

Scope is not a one-time check at run start. It must be re-evaluated whenever:

- A redirect occurs (`in-scope.example.com → other-domain.example` must not be followed without
  authorization for `other-domain.example`)
- DNS resolves a hostname to a new IP
- A discovered hostname is introduced (via crawling, certificate transparency, JS analysis, etc.)
- A crawler discovers another domain
- JavaScript references an external host
- An API points to another service

```text
in-scope.example.com → redirect → other-domain.example
```

ARGUS must not automatically continue unless the destination is authorized. Similarly,
`hostname → DNS → IP` must be checked against the scope model wherever required.

## Redirect and Discovered-Target Policy (Authoritative)

Every time a scope-checked interaction reveals another destination — a redirect, a DNS
resolution, a hostname surfaced in JavaScript, an API/WebSocket destination, or a link found
during crawling — the destination is **never acted on directly**. It is first extracted and
evaluated by the Scope Guard:

```text
In-scope target
→ redirect/discovery detected
→ destination extracted
→ Scope Guard evaluates destination
```

- **Destination in scope:** follow according to normal task policy; the destination may be
  interacted with exactly like any other in-scope target, always through the normal
  Task Planner → Scope Guard → Rate Limiter → Tool Adapter → Tool Runner chain.
- **Destination out of scope:**
  1. Do **not** perform any active interaction with the destination.
  2. Preserve the redirect/destination relationship as an `evidence` record referencing the
     discovering tool run (`05_DATA_MODEL.md` §evidence) — the fact that `in-scope.example.com`
     redirects to `other-domain.example` is itself useful intelligence and must be persisted
     (as evidence of the redirect, not as a claim about the out-of-scope host's contents).
  3. Mark the destination as **out-of-scope** in the run's intelligence (as a rejected/recorded
     destination, without following it).
  4. Optionally create a skipped/rejected task with the recorded reason, so the attempt is
     auditable.

This policy applies uniformly to every discovery surface **before any active interaction**:

- Redirects encountered while probing (httpx follow-redirects)
- DNS-discovered targets (hostname resolves to a new IP)
- JavaScript-discovered hosts
- API-discovered hosts / API responses pointing to other services
- WebSocket endpoints
- Links discovered during crawling
- Certificate-transparency-discovered hostnames

Scope is always evaluated **before** active interaction, never after it. The Scope Guard is the
only entity that decides in/out-of-scope status; AI agents, parsers, and adapters cannot override
it.

## Rate Limiting

Rate limiting considers:

- Requests per second (global and per-host)
- Concurrent request limits
- Per-tool limits
- Program-specific configured rules

Different targets may require different rates; configuration is per-program, not global-only.

## Stop Conditions / Target Instability

If a target appears unstable — repeated timeouts, connection failures, abnormal error rates,
sudden instability, or configured thresholds being exceeded — ARGUS prefers **stop or slow
down** over blindly continuing.

## Prohibited Automation

ARGUS must never automatically perform:

- Destructive exploitation
- Data destruction
- Credential stuffing or password spraying
- Uncontrolled brute force
- Denial-of-service activity
- Unauthorized scope expansion
- Security-control bypass (e.g. WAF evasion)
- Stealth/evasion designed to defeat monitoring
- Arbitrary persistence
- System modification

These are hard prohibitions, not configuration options. No task score, priority, or AI
confidence level authorizes them.

## Human-in-the-Loop

The AI's role in sensitive situations is to present, not act:

```text
Potential authorization issue identified.

Evidence:
...

Reasoning:
...

Safe validation:
...
```

The human decides whether to proceed with sensitive validation. This is preferable to an AI that
detects a possible IDOR and automatically exploits every ID it can find. Activities requiring
human approval include any validation step that would materially interact with authentication,
authorization boundaries, or anything not already covered by a completed, scope-checked recon
task.

## Relationship to Other Documents

- `06_TOOL_CONTRACTS.md` — the Tool Runner and adapters that sit below the Scope Guard/Rate
  Limiter in the diagram above
- `07_AI_AGENTS.md` §Forbidden Actions — per-agent restatement of these rules
- `08_ORCHESTRATOR.md` — safety checks are hard filters applied *before* task scoring, not part
  of the score itself
- `13_TESTING_STRATEGY.md` §Scope Tests / §Command Safety — how these rules are verified
