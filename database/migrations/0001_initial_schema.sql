/* ARGUS initial schema.
 *
 * Authoritative source: docs/05_DATA_MODEL.md. Every table/column mirrors that
 * document exactly; do not add or rename columns here without updating the doc.
 * Assumes PostgreSQL 13+ (uuid built-in gen_random_uuid()).
 *
 * Version: 1
 */

CREATE TABLE IF NOT EXISTS organizations (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name       text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS organizations_name_uq ON organizations (name);

CREATE TABLE IF NOT EXISTS programs (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES organizations (id),
    name            text NOT NULL,
    status          text NOT NULL CHECK (status IN ('active', 'paused', 'closed'))
);

CREATE INDEX IF NOT EXISTS programs_organization_id_idx ON programs (organization_id);
CREATE UNIQUE INDEX IF NOT EXISTS programs_name_uq ON programs (organization_id, name);

CREATE TABLE IF NOT EXISTS runs (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    program_id           uuid NOT NULL REFERENCES programs (id),
    status               text NOT NULL CHECK (status IN (
        'CREATED',
        'VALIDATING',
        'INITIALIZING',
        'RECONNING',
        'ANALYZING',
        'PLANNING',
        'EXECUTING',
        'CORRELATING',
        'PRIORITIZING',
        'WAITING_FOR_NEXT_TASK',
        'COMPLETED',
        'FAILED',
        'CANCELLED'
    )),
    target               text NOT NULL,
    configuration_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    started_at           timestamptz,
    completed_at         timestamptz,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS runs_program_id_idx ON runs (program_id);
CREATE INDEX IF NOT EXISTS runs_program_status_idx ON runs (program_id, status);

CREATE TABLE IF NOT EXISTS scope_rules (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    program_id uuid NOT NULL REFERENCES programs (id),
    rule_type  text NOT NULL CHECK (rule_type IN ('domain', 'subdomain', 'ip', 'cidr', 'port', 'exclusion')),
    value      text NOT NULL,
    allowed    boolean NOT NULL
);

CREATE INDEX IF NOT EXISTS scope_rules_program_type_idx ON scope_rules (program_id, rule_type);
CREATE UNIQUE INDEX IF NOT EXISTS scope_rules_uq ON scope_rules (program_id, rule_type, value);

CREATE TABLE IF NOT EXISTS assets (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    program_id    uuid NOT NULL REFERENCES programs (id),
    hostname      text NOT NULL,
    source        text NOT NULL,
    discovered_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS assets_hostname_idx ON assets (hostname);
CREATE UNIQUE INDEX IF NOT EXISTS assets_program_hostname_uq ON assets (program_id, hostname);

CREATE TABLE IF NOT EXISTS dns_records (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id    uuid NOT NULL REFERENCES assets (id),
    record_type text NOT NULL CHECK (record_type IN ('A', 'AAAA', 'CNAME', 'MX', 'NS', 'TXT')),
    value       text NOT NULL,
    resolved_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS dns_records_asset_type_idx ON dns_records (asset_id, record_type);

CREATE TABLE IF NOT EXISTS ips (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    address    inet NOT NULL,
    first_seen timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ips_address_uq ON ips (address);

CREATE TABLE IF NOT EXISTS asset_ips (
    asset_id    uuid NOT NULL REFERENCES assets (id),
    ip_id       uuid NOT NULL REFERENCES ips (id),
    observed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_id, ip_id)
);

CREATE INDEX IF NOT EXISTS asset_ips_ip_id_idx ON asset_ips (ip_id);

CREATE TABLE IF NOT EXISTS ports (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ip_id       uuid NOT NULL REFERENCES ips (id),
    port_number integer NOT NULL,
    protocol    text NOT NULL CHECK (protocol IN ('tcp', 'udp')),
    state       text NOT NULL CHECK (state IN ('open', 'closed', 'filtered')),
    service     text,
    version     text
);

CREATE INDEX IF NOT EXISTS ports_ip_port_idx ON ports (ip_id, port_number);
CREATE UNIQUE INDEX IF NOT EXISTS ports_uq ON ports (ip_id, port_number, protocol);

CREATE TABLE IF NOT EXISTS technologies (
    id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name     text NOT NULL,
    category text NOT NULL CHECK (category IN (
        'framework', 'cms', 'api_technology', 'cdn', 'waf', 'cloud', 'auth', 'other'
    ))
);

CREATE UNIQUE INDEX IF NOT EXISTS technologies_name_uq ON technologies (name);

CREATE TABLE IF NOT EXISTS tasks (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id         uuid NOT NULL REFERENCES runs (id),
    type           text NOT NULL,
    target         text NOT NULL,
    parent_task_id uuid REFERENCES tasks (id),
    priority       numeric,
    status         text NOT NULL CHECK (status IN (
        'pending', 'running', 'completed', 'failed', 'skipped', 'cancelled'
    )),
    fingerprint    text NOT NULL,
    reason         text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    started_at     timestamptz,
    completed_at   timestamptz
);

CREATE INDEX IF NOT EXISTS tasks_fingerprint_idx ON tasks (fingerprint);
CREATE INDEX IF NOT EXISTS tasks_run_status_idx ON tasks (run_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS tasks_run_fingerprint_uq ON tasks (run_id, fingerprint);

CREATE TABLE IF NOT EXISTS tool_runs (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id       uuid NOT NULL REFERENCES tasks (id),
    tool_name     text NOT NULL,
    command       text[] NOT NULL DEFAULT '{}',
    exit_code     integer,
    raw_output_ref text,
    started_at    timestamptz,
    completed_at  timestamptz
);

CREATE INDEX IF NOT EXISTS tool_runs_tool_task_idx ON tool_runs (tool_name, task_id);

CREATE TABLE IF NOT EXISTS evidence (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tool_run_id   uuid REFERENCES tool_runs (id),
    entity_type   text NOT NULL,
    entity_id     uuid,
    raw_reference text
);

CREATE INDEX IF NOT EXISTS evidence_entity_idx ON evidence (entity_type, entity_id);

CREATE TABLE IF NOT EXISTS asset_technologies (
    asset_id      uuid NOT NULL REFERENCES assets (id),
    technology_id uuid NOT NULL REFERENCES technologies (id),
    confidence    numeric NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    evidence_id   uuid REFERENCES evidence (id),
    PRIMARY KEY (asset_id, technology_id)
);

CREATE INDEX IF NOT EXISTS asset_technologies_technology_id_idx ON asset_technologies (technology_id);

CREATE TABLE IF NOT EXISTS web_apps (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id      uuid NOT NULL REFERENCES assets (id),
    port_id       uuid NOT NULL REFERENCES ports (id),
    status_code   integer,
    title         text,
    server_header text
);

CREATE INDEX IF NOT EXISTS web_apps_asset_id_idx ON web_apps (asset_id);
CREATE UNIQUE INDEX IF NOT EXISTS web_apps_uq ON web_apps (asset_id, port_id);

CREATE TABLE IF NOT EXISTS urls (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    web_app_id uuid NOT NULL REFERENCES web_apps (id),
    path       text NOT NULL,
    source     text NOT NULL,
    historical boolean NOT NULL DEFAULT false
);

CREATE INDEX IF NOT EXISTS urls_webapp_path_idx ON urls (web_app_id, path);
CREATE UNIQUE INDEX IF NOT EXISTS urls_uq ON urls (web_app_id, path);

CREATE TABLE IF NOT EXISTS endpoints (
    id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    url_id  uuid NOT NULL REFERENCES urls (id),
    method  text NOT NULL,
    pattern text NOT NULL
);

CREATE INDEX IF NOT EXISTS endpoints_pattern_idx ON endpoints (pattern);
CREATE UNIQUE INDEX IF NOT EXISTS endpoints_uq ON endpoints (url_id, method, pattern);

CREATE TABLE IF NOT EXISTS parameters (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    endpoint_id uuid NOT NULL REFERENCES endpoints (id),
    name        text NOT NULL,
    location    text NOT NULL CHECK (location IN ('query', 'body', 'header', 'path')),
    significance text NOT NULL CHECK (significance IN ('object_id', 'pagination', 'filter', 'sort', 'unknown'))
);

CREATE INDEX IF NOT EXISTS parameters_endpoint_name_idx ON parameters (endpoint_id, name);
CREATE UNIQUE INDEX IF NOT EXISTS parameters_uq ON parameters (endpoint_id, name, location);

CREATE TABLE IF NOT EXISTS javascript_files (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    web_app_id    uuid NOT NULL REFERENCES web_apps (id),
    url           text NOT NULL,
    has_source_map boolean NOT NULL DEFAULT false
);

CREATE INDEX IF NOT EXISTS javascript_files_url_idx ON javascript_files (url);
CREATE UNIQUE INDEX IF NOT EXISTS javascript_files_uq ON javascript_files (web_app_id, url);

CREATE TABLE IF NOT EXISTS apis (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    web_app_id uuid NOT NULL REFERENCES web_apps (id),
    api_type   text NOT NULL CHECK (api_type IN ('rest', 'graphql', 'websocket')),
    documented boolean NOT NULL DEFAULT false
);

CREATE INDEX IF NOT EXISTS apis_api_type_idx ON apis (api_type);

CREATE TABLE IF NOT EXISTS graphql_operations (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    api_id         uuid NOT NULL REFERENCES apis (id),
    operation_type text NOT NULL CHECK (operation_type IN ('query', 'mutation', 'subscription')),
    name           text NOT NULL
);

CREATE INDEX IF NOT EXISTS graphql_operations_api_type_idx ON graphql_operations (api_id, operation_type);
CREATE UNIQUE INDEX IF NOT EXISTS graphql_operations_uq ON graphql_operations (api_id, operation_type, name);

CREATE TABLE IF NOT EXISTS auth_mechanisms (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    web_app_id      uuid NOT NULL REFERENCES web_apps (id),
    mechanism_type  text NOT NULL CHECK (mechanism_type IN ('cookie', 'bearer', 'oauth', 'api_key', 'jwt', 'other')),
    details         jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS auth_mechanisms_type_idx ON auth_mechanisms (mechanism_type);

CREATE TABLE IF NOT EXISTS websocket_endpoints (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    web_app_id         uuid NOT NULL REFERENCES web_apps (id),
    url                text NOT NULL,
    auth_mechanism_id  uuid REFERENCES auth_mechanisms (id)
);

CREATE INDEX IF NOT EXISTS websocket_endpoints_url_idx ON websocket_endpoints (url);
CREATE UNIQUE INDEX IF NOT EXISTS websocket_endpoints_uq ON websocket_endpoints (web_app_id, url);

CREATE TABLE IF NOT EXISTS hypotheses (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    endpoint_id uuid REFERENCES endpoints (id),
    statement   text NOT NULL,
    truth_label text NOT NULL CHECK (truth_label IN ('HYPOTHESIS', 'UNVERIFIED_CLAIM', 'VALIDATED_FINDING')),
    confidence  numeric NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    severity    text NOT NULL CHECK (severity IN ('low', 'medium', 'high')),
    priority    text NOT NULL CHECK (priority IN ('low', 'medium', 'high')),
    status      text NOT NULL CHECK (status IN ('open', 'validated', 'rejected'))
);

CREATE INDEX IF NOT EXISTS hypotheses_label_status_idx ON hypotheses (truth_label, status);

CREATE TABLE IF NOT EXISTS ai_analysis (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_name        text NOT NULL,
    model_used        text NOT NULL,
    input_context_ref text,
    output            jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ai_analysis_agent_name_idx ON ai_analysis (agent_name);

CREATE TABLE IF NOT EXISTS schema_migrations (
    version    integer PRIMARY KEY,
    name       text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
);