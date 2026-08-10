CREATE SCHEMA IF NOT EXISTS bf_sensor;

CREATE TABLE IF NOT EXISTS bf_sensor.diagnosis_snapshots (
    id bigserial PRIMARY KEY,
    diagnosis_ts timestamp without time zone NOT NULL,
    diagnosis_window_start timestamp without time zone NOT NULL,
    diagnosis_window_end timestamp without time zone NOT NULL,
    baseline_window_start timestamp without time zone NOT NULL,
    baseline_window_end timestamp without time zone NOT NULL,
    baseline_days integer NOT NULL,
    window_minutes integer NOT NULL,
    source jsonb NOT NULL DEFAULT '{}'::jsonb,
    data_coverage jsonb NOT NULL DEFAULT '{}'::jsonb,
    missing_variables jsonb NOT NULL DEFAULT '[]'::jsonb,
    source_lag_seconds integer,
    main_label text NOT NULL,
    main_score double precision NOT NULL DEFAULT 0,
    main_confidence double precision NOT NULL DEFAULT 0,
    secondary_label text,
    secondary_score double precision NOT NULL DEFAULT 0,
    secondary_confidence double precision NOT NULL DEFAULT 0,
    evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
    raw_scores jsonb NOT NULL DEFAULT '{}'::jsonb,
    feature_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    diagnosis_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamp without time zone NOT NULL DEFAULT now(),
    updated_at timestamp without time zone NOT NULL DEFAULT now(),
    UNIQUE (diagnosis_ts, baseline_days, window_minutes, source)
);

CREATE INDEX IF NOT EXISTS idx_diagnosis_snapshots_ts
    ON bf_sensor.diagnosis_snapshots (diagnosis_ts DESC);

CREATE TABLE IF NOT EXISTS bf_sensor.data_quality_status (
    id bigserial PRIMARY KEY,
    checked_at timestamp without time zone NOT NULL DEFAULT now(),
    window_start timestamp without time zone NOT NULL,
    window_end timestamp without time zone NOT NULL,
    window_kind text NOT NULL,
    latest_data_ts timestamp without time zone,
    source_lag_seconds integer,
    expected_minutes integer NOT NULL DEFAULT 0,
    observed_minutes integer NOT NULL DEFAULT 0,
    coverage_ratio double precision NOT NULL DEFAULT 0,
    missing_variables jsonb NOT NULL DEFAULT '[]'::jsonb,
    stale_variables jsonb NOT NULL DEFAULT '[]'::jsonb,
    status text NOT NULL,
    details jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_data_quality_status_checked
    ON bf_sensor.data_quality_status (checked_at DESC);

CREATE TABLE IF NOT EXISTS bf_sensor.zero_value_audits (
    id bigserial PRIMARY KEY,
    tag_long_name text NOT NULL,
    variable_name text NOT NULL DEFAULT '',
    ts timestamp without time zone NOT NULL,
    db_value double precision,
    pspace_value double precision,
    pspace_quality text NOT NULL DEFAULT '',
    pspace_aggregate text NOT NULL DEFAULT 'PS_HIS_AVERAGE',
    source_server text NOT NULL DEFAULT '',
    verification_status text NOT NULL,
    error text NOT NULL DEFAULT '',
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    verified_at timestamp without time zone NOT NULL DEFAULT now(),
    UNIQUE (tag_long_name, ts, pspace_aggregate)
);

CREATE INDEX IF NOT EXISTS idx_zero_value_audits_status
    ON bf_sensor.zero_value_audits (verification_status, verified_at DESC);

CREATE INDEX IF NOT EXISTS idx_zero_value_audits_ts
    ON bf_sensor.zero_value_audits (ts DESC, tag_long_name);

CREATE TABLE IF NOT EXISTS bf_sensor.backfill_tasks (
    id bigserial PRIMARY KEY,
    created_at timestamp without time zone NOT NULL DEFAULT now(),
    updated_at timestamp without time zone NOT NULL DEFAULT now(),
    status text NOT NULL DEFAULT 'pending',
    reason text NOT NULL DEFAULT '',
    variable_name text NOT NULL DEFAULT '',
    tag_long_name text NOT NULL DEFAULT '',
    start_ts timestamp without time zone NOT NULL,
    end_ts timestamp without time zone NOT NULL,
    attempts integer NOT NULL DEFAULT 0,
    last_error text NOT NULL DEFAULT '',
    UNIQUE (variable_name, tag_long_name, start_ts, end_ts, reason)
);

CREATE INDEX IF NOT EXISTS idx_backfill_tasks_status
    ON bf_sensor.backfill_tasks (status, created_at);

CREATE TABLE IF NOT EXISTS bf_sensor.automation_runs (
    id bigserial PRIMARY KEY,
    started_at timestamp without time zone NOT NULL DEFAULT now(),
    finished_at timestamp without time zone,
    task_name text NOT NULL,
    status text NOT NULL DEFAULT 'running',
    window_start timestamp without time zone,
    window_end timestamp without time zone,
    rows_read bigint NOT NULL DEFAULT 0,
    rows_written bigint NOT NULL DEFAULT 0,
    message text NOT NULL DEFAULT '',
    details jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_automation_runs_started
    ON bf_sensor.automation_runs (started_at DESC);

CREATE TABLE IF NOT EXISTS bf_sensor.daily_baselines (
    id bigserial PRIMARY KEY,
    baseline_day date NOT NULL,
    baseline_window_start timestamp without time zone NOT NULL,
    baseline_window_end timestamp without time zone NOT NULL,
    baseline_days integer NOT NULL DEFAULT 30,
    variable_name text NOT NULL,
    median_ref double precision NOT NULL DEFAULT 0,
    iqr_ref double precision NOT NULL DEFAULT 0,
    p10 double precision,
    p25 double precision,
    p50 double precision,
    p75 double precision,
    p90 double precision,
    sample_count integer NOT NULL DEFAULT 0,
    expected_minutes integer NOT NULL DEFAULT 0,
    coverage_ratio double precision NOT NULL DEFAULT 0,
    source jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamp without time zone NOT NULL DEFAULT now(),
    updated_at timestamp without time zone NOT NULL DEFAULT now(),
    UNIQUE (baseline_day, baseline_days, variable_name)
);

CREATE INDEX IF NOT EXISTS idx_daily_baselines_day
    ON bf_sensor.daily_baselines (baseline_day DESC, variable_name);

ALTER TABLE bf_sensor.daily_baselines
    ADD COLUMN IF NOT EXISTS p25 double precision;

ALTER TABLE bf_sensor.daily_baselines
    ADD COLUMN IF NOT EXISTS p75 double precision;

CREATE TABLE IF NOT EXISTS bf_sensor.diagnosis_queues (
    queue_id text PRIMARY KEY,
    queue_hash text NOT NULL,
    queue_start_ts timestamp without time zone NOT NULL,
    queue_end_ts timestamp without time zone NOT NULL,
    window_minutes integer NOT NULL DEFAULT 60,
    step_minutes integer NOT NULL DEFAULT 5,
    diagnosis_count integer NOT NULL DEFAULT 0,
    expected_count integer NOT NULL DEFAULT 12,
    status text NOT NULL DEFAULT 'complete',
    diagnosis_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    diagnosis_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamp without time zone NOT NULL DEFAULT now(),
    updated_at timestamp without time zone NOT NULL DEFAULT now(),
    UNIQUE (queue_hash)
);

CREATE INDEX IF NOT EXISTS idx_diagnosis_queues_end
    ON bf_sensor.diagnosis_queues (queue_end_ts DESC);

CREATE TABLE IF NOT EXISTS bf_sensor.short_window_summaries (
    summary_id text PRIMARY KEY,
    queue_id text NOT NULL REFERENCES bf_sensor.diagnosis_queues(queue_id) ON DELETE CASCADE,
    queue_hash text NOT NULL,
    model_name text NOT NULL,
    prompt_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    llm_summary text NOT NULL DEFAULT '',
    diagnosis_queue_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    docx_path text NOT NULL DEFAULT '',
    markdown_path text NOT NULL DEFAULT '',
    status text NOT NULL DEFAULT 'ok',
    created_at timestamp without time zone NOT NULL DEFAULT now(),
    updated_at timestamp without time zone NOT NULL DEFAULT now(),
    UNIQUE (queue_id, model_name)
);

CREATE INDEX IF NOT EXISTS idx_short_window_summaries_created
    ON bf_sensor.short_window_summaries (created_at DESC);

CREATE TABLE IF NOT EXISTS bf_sensor.short_window_conversations (
    conversation_id text PRIMARY KEY,
    queue_id text NOT NULL REFERENCES bf_sensor.diagnosis_queues(queue_id) ON DELETE CASCADE,
    queue_hash text NOT NULL,
    last_queue_diagnosis_ts timestamp without time zone NOT NULL,
    created_at timestamp without time zone NOT NULL DEFAULT now(),
    updated_at timestamp without time zone NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_short_window_conversations_queue
    ON bf_sensor.short_window_conversations (queue_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS bf_sensor.conversation_delta_contexts (
    id bigserial PRIMARY KEY,
    conversation_id text NOT NULL,
    queue_id text NOT NULL,
    message_ts timestamp without time zone NOT NULL,
    previous_queue_end_ts timestamp without time zone NOT NULL,
    delta_start_ts timestamp without time zone,
    delta_end_ts timestamp without time zone,
    delta_diagnosis_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    operator_message text NOT NULL DEFAULT '',
    hidden_context_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamp without time zone NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_conversation_delta_contexts_conv
    ON bf_sensor.conversation_delta_contexts (conversation_id, message_ts DESC);

CREATE TABLE IF NOT EXISTS bf_sensor.short_window_conversation_messages (
    id bigserial PRIMARY KEY,
    conversation_id text NOT NULL REFERENCES bf_sensor.short_window_conversations(conversation_id) ON DELETE CASCADE,
    queue_id text NOT NULL REFERENCES bf_sensor.diagnosis_queues(queue_id) ON DELETE CASCADE,
    role text NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content text NOT NULL DEFAULT '',
    hidden_context_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamp without time zone NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_short_window_conversation_messages_conv
    ON bf_sensor.short_window_conversation_messages (conversation_id, id);
