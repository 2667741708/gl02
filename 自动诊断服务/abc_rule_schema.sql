-- REQ-ABC33-FURNACE-RULES-20260807
-- Additive migration.  Internal calculation columns are never projected by
-- production endpoints; use the safe view for ordinary read-only accounts.
CREATE SCHEMA IF NOT EXISTS bf_sensor;
CREATE SCHEMA IF NOT EXISTS bf_assistant;

CREATE TABLE IF NOT EXISTS bf_sensor.abc_rule_evaluation_batches (
    id bigserial PRIMARY KEY,
    furnace_id text NOT NULL DEFAULT 'GL02',
    evaluation_ts timestamptz NOT NULL,
    catalog_version text NOT NULL,
    config_version text NOT NULL,
    config_hash text NOT NULL,
    source_snapshot_id bigint,
    coverage_ratio numeric,
    data_age_seconds numeric,
    public_bundle jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (furnace_id, evaluation_ts, config_hash)
);

CREATE TABLE IF NOT EXISTS bf_sensor.abc_rule_evaluation_items (
    id bigserial PRIMARY KEY,
    batch_id bigint NOT NULL REFERENCES bf_sensor.abc_rule_evaluation_batches(id) ON DELETE CASCADE,
    rule_id text NOT NULL,
    category text NOT NULL CHECK (category IN ('A','B','C')),
    display_name text NOT NULL,
    score numeric NOT NULL,
    confidence numeric NOT NULL,
    status text NOT NULL CHECK (status IN ('eligible','blocked','needs_data','manual_confirm')),
    formula_terms jsonb NOT NULL,
    weights jsonb NOT NULL,
    thresholds jsonb NOT NULL,
    normalized_values jsonb NOT NULL,
    contributions jsonb NOT NULL,
    missing_features jsonb NOT NULL,
    public_detail jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (batch_id, rule_id)
);

CREATE TABLE IF NOT EXISTS bf_assistant.abc_rule_config_versions (
    id bigserial PRIMARY KEY,
    config_version text NOT NULL,
    config_hash text NOT NULL,
    state text NOT NULL CHECK (state IN ('draft','published','rolled_back')),
    config_json jsonb NOT NULL,
    change_reason text,
    actor text,
    actor_ip inet,
    created_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz
);

CREATE TABLE IF NOT EXISTS bf_assistant.abc_alert_episodes (
    id bigserial PRIMARY KEY,
    rule_id text NOT NULL,
    category text NOT NULL,
    state text NOT NULL CHECK (state IN ('active','acknowledged','field_confirmed','recovered','closed')),
    first_seen_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL,
    acknowledged_by text,
    closed_by text,
    latest_score numeric,
    latest_public_detail jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS bf_assistant.abc_alert_event_log (
    id bigserial PRIMARY KEY,
    episode_id bigint REFERENCES bf_assistant.abc_alert_episodes(id),
    rule_id text NOT NULL,
    event_type text NOT NULL CHECK (event_type IN ('triggered','upgraded','acknowledged','field_confirmed','recovered','closed')),
    actor text,
    event_ts timestamptz NOT NULL DEFAULT now(),
    detail jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE OR REPLACE VIEW bf_sensor.abc_rule_evaluation_public AS
SELECT i.batch_id, i.rule_id, i.category, i.display_name, i.score, i.confidence,
       i.status, i.public_detail, b.evaluation_ts, b.catalog_version, b.config_version
FROM bf_sensor.abc_rule_evaluation_items i
JOIN bf_sensor.abc_rule_evaluation_batches b ON b.id = i.batch_id;

