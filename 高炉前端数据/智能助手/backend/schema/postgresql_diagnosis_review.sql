-- REQ-8093-DIAGNOSIS-REVIEW-LOCAL-PROTOTYPE-20260803
-- Run only against explicitly configured loopback PostgreSQL.
CREATE SCHEMA IF NOT EXISTS bf_assistant;
CREATE TABLE IF NOT EXISTS bf_assistant.diagnosis_review_events (
    id BIGSERIAL PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    furnace_id TEXT NOT NULL,
    episode_key TEXT NOT NULL,
    episode_start_ts TIMESTAMPTZ NOT NULL,
    diagnosis_snapshot_id TEXT NOT NULL,
    diagnosis_ts TIMESTAMPTZ NOT NULL,
    main_label TEXT NOT NULL,
    main_score DOUBLE PRECISION NOT NULL,
    main_confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    secondary JSONB NOT NULL DEFAULT '[]'::jsonb,
    raw_scores JSONB NOT NULL,
    evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    data_coverage JSONB NOT NULL DEFAULT '{}'::jsonb,
    verdict TEXT NOT NULL CHECK (verdict IN ('correct', 'incorrect', 'uncertain')),
    corrected_main_label TEXT,
    corrected_secondary_label TEXT,
    note TEXT NOT NULL DEFAULT '',
    human_match_score SMALLINT CHECK (human_match_score BETWEEN 0 AND 100),
    suggestion TEXT NOT NULL DEFAULT '',
    reviewer_username TEXT NOT NULL,
    reviewer_role TEXT NOT NULL,
    identity_mode TEXT NOT NULL DEFAULT 'signed_session',
    snapshot_source TEXT NOT NULL CHECK (snapshot_source IN ('live_readonly', 'local_fixture')),
    source_page TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS diagnosis_review_events_episode_idx
    ON bf_assistant.diagnosis_review_events (episode_key, created_at DESC);
CREATE INDEX IF NOT EXISTS diagnosis_review_events_reviewer_idx
    ON bf_assistant.diagnosis_review_events (reviewer_username, created_at DESC);

ALTER TABLE bf_assistant.diagnosis_review_events
    ADD COLUMN IF NOT EXISTS human_match_score SMALLINT CHECK (human_match_score BETWEEN 0 AND 100);
ALTER TABLE bf_assistant.diagnosis_review_events
    ADD COLUMN IF NOT EXISTS suggestion TEXT NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS bf_assistant.diagnosis_manual_score_events (
    id BIGSERIAL PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    furnace_id TEXT NOT NULL,
    diagnosis_snapshot_id TEXT NOT NULL,
    diagnosis_ts TIMESTAMPTZ NOT NULL,
    target_label TEXT NOT NULL,
    system_main_label TEXT NOT NULL,
    system_main_score DOUBLE PRECISION NOT NULL,
    system_raw_scores JSONB NOT NULL,
    human_match_score SMALLINT CHECK (human_match_score BETWEEN 0 AND 100),
    suggestion TEXT NOT NULL DEFAULT '',
    reviewer_username TEXT NOT NULL,
    reviewer_role TEXT NOT NULL,
    identity_mode TEXT NOT NULL DEFAULT 'signed_session',
    snapshot_source TEXT NOT NULL CHECK (snapshot_source IN ('live_readonly', 'local_fixture')),
    source_page TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (human_match_score IS NOT NULL OR length(btrim(suggestion)) > 0)
);
CREATE INDEX IF NOT EXISTS diagnosis_manual_score_snapshot_idx
    ON bf_assistant.diagnosis_manual_score_events (diagnosis_ts DESC, target_label, created_at DESC);
CREATE INDEX IF NOT EXISTS diagnosis_manual_score_reviewer_idx
    ON bf_assistant.diagnosis_manual_score_events (reviewer_username, created_at DESC);
