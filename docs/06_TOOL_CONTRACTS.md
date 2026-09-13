# ARGUS Tool Contracts

Defines exactly how external security tools integrate with ARGUS.

## Tool Adapter Interface

```python
class ToolAdapter:
    name: str

    def is_available(self) -> bool:
        ...

    def build_command(self, task, config) -> list[str]:
        ...

    def validate(self, task, scope) -> None:
        ...

    def execute(self, task, runner):
        ...

    def parse(self, result):
        ...
```

Every adapter must, in order: (1) verify availability, (2) validate the task against scope,
(3) construct the command as an argument array, (4) execute through the controlled Tool Runner,
(5) preserve raw output, (6) parse output, (7) normalize observations into canonical objects.

---

## Tool Runner

Must specify and enforce:

- `subprocess.run([...], shell=False)` — **never** `shell=True`
- No concatenation of untrusted target input into shell strings; commands are argument arrays
- Configurable timeout per invocation
- Captured stdout, stderr, and exit code
- Controlled environment variables and working directory
- Raw-output preservation to `storage/raw/`
- Structured error objects on failure
- Secrets are never written to logs

### Platform Support

The Tool Runner contract is **platform-neutral by design**: commands are always argument arrays,
never shell strings, so the same adapter code runs on Linux, macOS, and (later) Windows. See
`15_FIRST_MILESTONE.md` §Supported Environment — Milestone 1 targets Linux/Unix; Windows
compatibility is a Phase 12 hardening concern and must not create Linux-only code paths that
would block it.

---

## Initial Adapters

For each adapter: **Tool, Purpose, Input, Command Construction, Arguments, Scope Requirements,
Output Format, Parser, Normalized Objects, Raw Output, Errors, Timeouts, Dependencies, Safety,
Tests.**

### Subfinder

**Purpose:** Passive subdomain enumeration. **Input:** in-scope root domain.
**Command construction:** `subfinder -d <domain> -json`. **Arguments:** `-d`, `-json`,
optional `-all`. **Scope requirements:** domain must be in `scope_rules` as allowed.
**Output format:** newline-delimited JSON. **Parser:** JSON-lines → hostname list.
**Normalized objects:** `assets`. **Raw output:** stored under `storage/raw/subfinder/`.
**Errors:** non-zero exit logged, run continues without this source. **Timeouts:** configurable,
default conservative. **Dependencies:** none. **Safety:** passive only. **Tests:** fixture-based
parse tests using recorded JSON output (`13_TESTING_STRATEGY.md`).

### Amass

**Purpose:** Broad passive/active subdomain enumeration. **Input:** in-scope root domain.
**Command construction:** `amass enum -d <domain> -json <outfile>`. **Arguments:** `-d`,
`-json`, `-passive` (default) or active mode only if scope permits active recon.
**Scope requirements:** domain allowed; active mode requires explicit active-recon permission.
**Output format:** JSON lines to file. **Parser:** JSON → hostname + source list.
**Normalized objects:** `assets`. **Raw output:** `storage/raw/amass/`. **Errors:** missing
binary logs a warning and discovery continues with other sources (`37` in the source brief).
**Timeouts:** longer default than Subfinder (Amass can be slow). **Dependencies:** none.
**Safety:** default passive; active mode gated by scope config. **Tests:** fixture parse tests.

### Assetfinder

**Purpose:** Lightweight subdomain enumeration. **Input:** in-scope root domain.
**Command construction:** `assetfinder --subs-only <domain>`. **Arguments:** `--subs-only`.
**Scope requirements:** domain allowed. **Output format:** plain text, one hostname per line.
**Parser:** line-split → hostname list. **Normalized objects:** `assets`. **Raw output:**
`storage/raw/assetfinder/`. **Errors:** logged, non-fatal. **Timeouts:** short default.
**Dependencies:** none. **Safety:** passive only. **Tests:** fixture parse tests.

### crt.sh (Certificate Transparency)

**Purpose:** CT-log-based hostname discovery. **Input:** in-scope root domain.
**Command construction:** internal HTTPS query against the CT log API (not a shelled binary;
implemented as an HTTP client call inside `recon/subdomains/crt.py`), still routed through the
same validate/execute/parse lifecycle. **Arguments:** query domain parameter.
**Scope requirements:** domain allowed. **Output format:** JSON. **Parser:** JSON → hostname
list, deduplicated against wildcard entries. **Normalized objects:** `assets`, certificate
metadata. **Raw output:** `storage/raw/crt/`. **Errors:** API failure logged, non-fatal.
**Timeouts:** short HTTP timeout with retry/backoff. **Dependencies:** none. **Safety:** passive,
read-only third-party query. **Tests:** fixture-based response parse tests.

### DNS Resolver

**Purpose:** Resolve assets to DNS records. **Input:** normalized asset hostname.
**Command construction:** internal resolver call (e.g. via a DNS library), not a shelled binary.
**Arguments:** record types to query (A/AAAA/CNAME/MX/NS/TXT). **Scope requirements:** hostname
already validated as in-scope. **Output format:** structured record objects. **Parser:** direct
mapping to `dns_records` rows. **Normalized objects:** `dns_records`, `ips`, `asset_ips`.
**Raw output:** `storage/raw/dns/`. **Errors:** NXDOMAIN/timeout recorded per record type, not
fatal to the run. **Timeouts:** short, per-query. **Dependencies:** Subdomain Discovery sources.
**Safety:** resolution to a new IP triggers a scope re-check before further action
(`04_SCOPE_SAFETY.md`). **Tests:** fixture-based resolution tests, including NXDOMAIN cases.

### Nmap

**Purpose:** Port/service scanning. **Input:** in-scope, resolved IP(s).
**Command construction:** `nmap -sV -p <port-range> -oJSON <outfile> <ip>` (or equivalent
structured output flag). **Arguments:** port range from config (default `1-1000`), service
detection flag. **Scope requirements:** IP must be in-scope; port range must be within configured
bounds. **Output format:** structured (JSON/XML). **Parser:** → `ports` rows with service/version.
**Normalized objects:** `ports`. **Raw output:** `storage/raw/nmap/`. **Errors:** scan failure
logged; partial results still parsed. **Timeouts:** longer default, target-instability aware.
**Dependencies:** DNS Resolver. **Safety:** strict port-range enforcement, rate-limited, backs
off on target instability. **Tests:** fixture parse tests using recorded Nmap JSON/XML output.

### httpx

**Purpose:** HTTP/HTTPS probing and technology fingerprinting. **Input:** resolved
host:port combinations. **Command construction:** `httpx -json -tech-detect -title
-status-code`. **Arguments:** `-json`, `-tech-detect`, `-title`, `-status-code`, `-follow-redirects`
(scope-checked). **Scope requirements:** host in-scope; redirect destinations re-checked before
follow. **Output format:** JSON lines. **Parser:** → `web_apps` + `asset_technologies` rows.
**Normalized objects:** `web_apps`, `technologies`, `asset_technologies`. **Raw output:**
`storage/raw/httpx/`. **Errors:** connection failure recorded per host, non-fatal. **Timeouts:**
per-request, short. **Dependencies:** Nmap / DNS Resolver. **Safety:** redirects scope-checked
before being followed. **Tests:** fixture parse tests, including redirect-chain fixtures.

### Katana

**Purpose:** Web crawling. **Input:** live web application URL. **Command construction:**
`katana -u <url> -jsonl -js-crawl`. **Arguments:** `-jsonl`, `-js-crawl`, `-depth` (configured).
**Scope requirements:** discovered links to new hosts re-enter the Scope Guard before being
crawled. **Output format:** JSON lines. **Parser:** → `urls`, `endpoints`, `parameters`,
`javascript_files`. **Normalized objects:** as listed. **Raw output:** `storage/raw/katana/`.
**Errors:** crawl errors per-URL logged, crawl continues. **Timeouts:** overall crawl timeout
plus per-request timeout. **Dependencies:** httpx. **Safety:** depth/time bounded, rate-limited,
scope-checked per discovered host. **Tests:** fixture parse tests using recorded crawl output.

### FFUF

**Purpose:** Content discovery via fuzzing. **Input:** live web application base URL + wordlist.
**Command construction:** `ffuf -u <url>/FUZZ -w <wordlist> -json -o <outfile>`. **Arguments:**
`-w`, `-json`, rate/concurrency flags from Rate Limiter config. **Scope requirements:** base URL
in-scope; wordlist source approved. **Output format:** JSON. **Parser:** → `urls`, `endpoints`
with status codes. **Normalized objects:** `urls`, `endpoints`. **Raw output:**
`storage/raw/ffuf/`. **Errors:** logged per request, non-fatal. **Timeouts:** per-request short
timeout, overall job timeout. **Dependencies:** httpx. **Safety:** concurrency/rate capped by
Rate Limiter; discovery is never auto-treated as a vulnerability. **Tests:** fixture parse tests.

### Feroxbuster

**Purpose:** Recursive content discovery. **Input:** live web application base URL + wordlist.
**Command construction:** `feroxbuster -u <url> -w <wordlist> --json -o <outfile>`.
**Arguments:** `-w`, `--json`, recursion depth, rate/concurrency flags. **Scope requirements:**
same as FFUF. **Output format:** JSON. **Parser:** → `urls`, `endpoints`. **Normalized objects:**
`urls`, `endpoints`. **Raw output:** `storage/raw/feroxbuster/`. **Errors:** logged per request,
non-fatal. **Timeouts:** per-request + overall job timeout. **Dependencies:** httpx. **Safety:**
recursion depth and rate capped; discovery ≠ vulnerability. **Tests:** fixture parse tests.

### GAU

**Purpose:** Historical URL discovery. **Input:** in-scope root domain. **Command
construction:** `gau <domain> --json`. **Arguments:** `--json`, optional provider flags.
**Scope requirements:** domain in-scope. **Output format:** JSON lines. **Parser:** → `urls`
marked `historical: true`. **Normalized objects:** `urls`. **Raw output:** `storage/raw/gau/`.
**Errors:** provider failure logged, others continue. **Timeouts:** per-provider timeout.
**Dependencies:** none (passive). **Safety:** passive-only; historical URLs never presented as
active without a fresh liveness check. **Tests:** fixture parse tests.

### Wayback (waybackurls)

**Purpose:** Historical URL discovery via the Wayback Machine. **Input:** in-scope root domain.
**Command construction:** `waybackurls <domain>`. **Arguments:** none beyond target.
**Scope requirements:** domain in-scope. **Output format:** plain text, one URL per line.
**Parser:** line-split → `urls` marked `historical: true`. **Normalized objects:** `urls`.
**Raw output:** `storage/raw/wayback/`. **Errors:** API failure logged, non-fatal. **Timeouts:**
short HTTP timeout with backoff. **Dependencies:** none (passive). **Safety:** passive-only,
historical flag enforced. **Tests:** fixture parse tests.

---

## Missing-Tool Handling

A missing or unavailable tool must never crash the run:

```text
Amass unavailable
  ↓
log warning
  ↓
continue with available discovery sources
```

## Testing

Every adapter is covered by fixture-based parser tests (`fixtures/<tool>/`) so CI never depends
on live external targets — see `13_TESTING_STRATEGY.md` §Adapter Fixture Tests.
