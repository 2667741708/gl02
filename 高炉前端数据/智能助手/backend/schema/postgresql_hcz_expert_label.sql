CREATE SCHEMA IF NOT EXISTS __SCHEMA__;

CREATE TABLE IF NOT EXISTS __SCHEMA__.hcz_expert_label_events (
    id BIGSERIAL PRIMARY KEY,
    reference_id TEXT NOT NULL UNIQUE,
    idempotency_key TEXT NOT NULL UNIQUE,
    label_version TEXT NOT NULL,
    reference_type TEXT NOT NULL CHECK (reference_type = 'expert_weak_label'),
    furnace_id TEXT NOT NULL DEFAULT 'GL02',
    observed_at TIMESTAMPTZ NOT NULL,
    available_at TIMESTAMPTZ NOT NULL,
    source_window_start TIMESTAMPTZ NOT NULL,
    source_window_end TIMESTAMPTZ NOT NULL,
    context_mode TEXT NOT NULL CHECK (
        context_mode IN ('contemporaneous_blind', 'retrospective_with_post_observation_evidence')
    ),
    blind_to_model BOOLEAN NOT NULL CHECK (blind_to_model),
    root_level_label TEXT NOT NULL CHECK (
        root_level_label IN ('high', 'normal', 'low', 'uncertain')
    ),
    movement_label TEXT NOT NULL CHECK (
        movement_label IN ('up', 'stable', 'down', 'uncertain')
    ),
    center_height_m DOUBLE PRECISION CHECK (
        center_height_m IS NULL OR center_height_m BETWEEN 10.0 AND 35.0
    ),
    thickness_m DOUBLE PRECISION CHECK (
        thickness_m IS NULL OR thickness_m BETWEEN 0.5 AND 8.0
    ),
    eccentric_sector TEXT CHECK (
        eccentric_sector IS NULL OR eccentric_sector IN ('A','B','C','D','E','F','G','H','none','uncertain')
    ),
    confidence_grade SMALLINT NOT NULL CHECK (confidence_grade BETWEEN 1 AND 5),
    evidence_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
    note TEXT NOT NULL DEFAULT '',
    operator_name TEXT NOT NULL,
    reviewer_username TEXT NOT NULL,
    reviewer_role TEXT NOT NULL,
    identity_mode TEXT NOT NULL,
    source_schema_version TEXT NOT NULL,
    source_data_hash CHAR(64) NOT NULL,
    source_context JSONB NOT NULL,
    source_page TEXT NOT NULL DEFAULT '',
    supersedes_label_id BIGINT REFERENCES __SCHEMA__.hcz_expert_label_events(id),
    client_address TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (source_window_start < source_window_end),
    CHECK (observed_at >= source_window_start AND observed_at <= source_window_end),
    CHECK (length(btrim(operator_name)) BETWEEN 2 AND 64),
    CHECK (length(note) <= 2000)
);

CREATE INDEX IF NOT EXISTS hcz_expert_label_observed_idx
    ON __SCHEMA__.hcz_expert_label_events (furnace_id, observed_at DESC, created_at DESC);

CREATE INDEX IF NOT EXISTS hcz_expert_label_available_idx
    ON __SCHEMA__.hcz_expert_label_events (available_at DESC);

CREATE INDEX IF NOT EXISTS hcz_expert_label_reviewer_idx
    ON __SCHEMA__.hcz_expert_label_events (reviewer_username, created_at DESC);

COMMENT ON TABLE __SCHEMA__.hcz_expert_label_events IS
    'HCZ expert weak labels. Blind to model output; never equivalent to direct measurement truth.';
