CREATE SCHEMA IF NOT EXISTS bf_sensor;

CREATE TABLE IF NOT EXISTS bf_sensor.sensor_registry (
    variable_name text PRIMARY KEY,
    chinese_name text NOT NULL,
    branch text NOT NULL,
    short_name text NOT NULL,
    tag_long_name text NOT NULL UNIQUE,
    description text NOT NULL,
    status_usage text NOT NULL,
    is_derived boolean NOT NULL DEFAULT false,
    is_enabled boolean NOT NULL DEFAULT true,
    updated_at timestamp without time zone NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bf_sensor.one_minute_values (
    tag_long_name text NOT NULL,
    ts timestamp without time zone NOT NULL,
    value double precision,
    quality text,
    value_type integer,
    aggregate text NOT NULL DEFAULT 'PS_HIS_AVERAGE',
    interval_seconds integer NOT NULL DEFAULT 60,
    source_server text NOT NULL,
    collected_at timestamp without time zone NOT NULL DEFAULT now(),
    sample_count integer,
    numeric_sample_count integer,
    good_sample_count integer,
    expected_sample_count integer,
    coverage_ratio double precision,
    min_value double precision,
    max_value double precision,
    last_value double precision,
    window_complete boolean,
    semantic_version text,
    PRIMARY KEY (tag_long_name, ts)
) PARTITION BY RANGE (ts);

ALTER TABLE bf_sensor.one_minute_values
    ADD COLUMN IF NOT EXISTS sample_count integer,
    ADD COLUMN IF NOT EXISTS numeric_sample_count integer,
    ADD COLUMN IF NOT EXISTS good_sample_count integer,
    ADD COLUMN IF NOT EXISTS expected_sample_count integer,
    ADD COLUMN IF NOT EXISTS coverage_ratio double precision,
    ADD COLUMN IF NOT EXISTS min_value double precision,
    ADD COLUMN IF NOT EXISTS max_value double precision,
    ADD COLUMN IF NOT EXISTS last_value double precision,
    ADD COLUMN IF NOT EXISTS window_complete boolean,
    ADD COLUMN IF NOT EXISTS semantic_version text;

CREATE TABLE IF NOT EXISTS bf_sensor.raw_5s_values (
    tag_long_name text NOT NULL,
    ts timestamp without time zone NOT NULL,
    value double precision,
    quality text,
    value_type integer,
    raw_interval_seconds integer NOT NULL DEFAULT 5,
    source_server text NOT NULL,
    read_start_ts timestamp without time zone NOT NULL,
    read_end_ts timestamp without time zone NOT NULL,
    collected_at timestamp without time zone NOT NULL DEFAULT now(),
    PRIMARY KEY (tag_long_name, ts)
) PARTITION BY RANGE (ts);

CREATE TABLE IF NOT EXISTS bf_sensor.sync_state (
    tag_long_name text PRIMARY KEY,
    last_success_ts timestamp without time zone,
    last_attempt_ts timestamp without time zone,
    last_error text NOT NULL DEFAULT '',
    updated_at timestamp without time zone NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bf_sensor.sync_runs (
    id bigserial PRIMARY KEY,
    started_at timestamp without time zone NOT NULL DEFAULT now(),
    finished_at timestamp without time zone,
    sync_mode text NOT NULL,
    start_ts timestamp without time zone NOT NULL,
    end_ts timestamp without time zone NOT NULL,
    rows_written bigint NOT NULL DEFAULT 0,
    tags_ok integer NOT NULL DEFAULT 0,
    tags_error integer NOT NULL DEFAULT 0,
    error text NOT NULL DEFAULT ''
);

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

CREATE TABLE IF NOT EXISTS bf_sensor.user_instructions (
    id bigserial PRIMARY KEY,
    created_at timestamp without time zone NOT NULL DEFAULT now(),
    title text NOT NULL,
    content text NOT NULL,
    source_file text NOT NULL DEFAULT '',
    UNIQUE (title, content)
);

CREATE INDEX IF NOT EXISTS idx_sensor_registry_enabled
    ON bf_sensor.sensor_registry (is_enabled, is_derived, variable_name);

CREATE OR REPLACE FUNCTION bf_sensor.ensure_1min_partition(partition_start timestamp without time zone)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    month_start timestamp without time zone;
    month_end timestamp without time zone;
    partition_name text;
BEGIN
    month_start := date_trunc('month', partition_start);
    month_end := month_start + interval '1 month';
    partition_name := 'one_minute_values_' || to_char(month_start, 'YYYYMM');

    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS bf_sensor.%I PARTITION OF bf_sensor.one_minute_values FOR VALUES FROM (%L) TO (%L)',
        partition_name,
        month_start,
        month_end
    );
END;
$$;

CREATE OR REPLACE FUNCTION bf_sensor.ensure_1min_partitions(
    from_ts timestamp without time zone,
    to_ts timestamp without time zone
)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    cursor_ts timestamp without time zone;
BEGIN
    cursor_ts := date_trunc('month', from_ts);
    WHILE cursor_ts <= to_ts LOOP
        PERFORM bf_sensor.ensure_1min_partition(cursor_ts);
        cursor_ts := cursor_ts + interval '1 month';
    END LOOP;
END;
$$;

CREATE OR REPLACE FUNCTION bf_sensor.ensure_raw_5s_partition(partition_start timestamp without time zone)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    day_start timestamp without time zone;
    day_end timestamp without time zone;
    partition_name text;
BEGIN
    day_start := date_trunc('day', partition_start);
    day_end := day_start + interval '1 day';
    partition_name := 'raw_5s_values_' || to_char(day_start, 'YYYYMMDD');

    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS bf_sensor.%I PARTITION OF bf_sensor.raw_5s_values FOR VALUES FROM (%L) TO (%L)',
        partition_name,
        day_start,
        day_end
    );
END;
$$;

CREATE OR REPLACE FUNCTION bf_sensor.ensure_raw_5s_partitions(
    from_ts timestamp without time zone,
    to_ts timestamp without time zone
)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    cursor_ts timestamp without time zone;
BEGIN
    cursor_ts := date_trunc('day', from_ts);
    WHILE cursor_ts <= to_ts LOOP
        PERFORM bf_sensor.ensure_raw_5s_partition(cursor_ts);
        cursor_ts := cursor_ts + interval '1 day';
    END LOOP;
END;
$$;

CREATE OR REPLACE FUNCTION bf_sensor.drop_1min_partitions_older_than(retain interval DEFAULT interval '3 years')
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    cutoff_month timestamp without time zone;
    part record;
    dropped integer := 0;
BEGIN
    cutoff_month := date_trunc('month', now()::timestamp without time zone - retain);

    FOR part IN
        SELECT c.relname AS partition_name
        FROM pg_inherits i
        JOIN pg_class c ON c.oid = i.inhrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE i.inhparent = 'bf_sensor.one_minute_values'::regclass
          AND n.nspname = 'bf_sensor'
          AND c.relname ~ '^one_minute_values_[0-9]{6}$'
          AND to_date(substring(c.relname from '([0-9]{6})$'), 'YYYYMM') < cutoff_month::date
    LOOP
        EXECUTE format('DROP TABLE IF EXISTS bf_sensor.%I', part.partition_name);
        dropped := dropped + 1;
    END LOOP;

    RETURN dropped;
END;
$$;

CREATE OR REPLACE FUNCTION bf_sensor.drop_raw_5s_partitions_older_than(retain interval DEFAULT interval '30 days')
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    cutoff_day timestamp without time zone;
    part record;
    dropped integer := 0;
BEGIN
    cutoff_day := date_trunc('day', now()::timestamp without time zone - retain);

    FOR part IN
        SELECT c.relname AS partition_name
        FROM pg_inherits i
        JOIN pg_class c ON c.oid = i.inhrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE i.inhparent = 'bf_sensor.raw_5s_values'::regclass
          AND n.nspname = 'bf_sensor'
          AND c.relname ~ '^raw_5s_values_[0-9]{8}$'
          AND to_date(substring(c.relname from '([0-9]{8})$'), 'YYYYMMDD') < cutoff_day::date
    LOOP
        EXECUTE format('DROP TABLE IF EXISTS bf_sensor.%I', part.partition_name);
        dropped := dropped + 1;
    END LOOP;

    RETURN dropped;
END;
$$;

CREATE OR REPLACE VIEW bf_sensor.v_one_minute_with_registry AS
SELECT
    r.variable_name,
    r.chinese_name,
    r.branch,
    r.short_name,
    r.tag_long_name,
    r.description,
    r.status_usage,
    v.ts,
    v.value,
    v.quality,
    v.value_type,
    v.aggregate,
    v.interval_seconds,
    v.source_server,
    v.collected_at
FROM bf_sensor.one_minute_values v
JOIN bf_sensor.sensor_registry r ON r.tag_long_name = v.tag_long_name
WHERE r.is_enabled = true
  AND r.is_derived = false;

CREATE OR REPLACE VIEW bf_sensor.v_raw_5s_with_registry AS
SELECT
    r.variable_name,
    r.chinese_name,
    r.branch,
    r.short_name,
    r.tag_long_name,
    r.description,
    r.status_usage,
    v.ts,
    v.value,
    v.quality,
    v.value_type,
    v.raw_interval_seconds,
    v.source_server,
    v.read_start_ts,
    v.read_end_ts,
    v.collected_at
FROM bf_sensor.raw_5s_values v
JOIN bf_sensor.sensor_registry r ON r.tag_long_name = v.tag_long_name
WHERE r.is_enabled = true
  AND r.is_derived = false;

-- FOREMAN-COAL-HOURLY-20260806-BEGIN
-- REQ-FOREMAN-COAL-HOURLY-20260806
-- Store one row per production hour without adding another pSpace reader.
-- The existing minute synchronizer supplies both PCI_rate and the confirmed
-- 2# furnace previous-hour meter point.

CREATE TABLE IF NOT EXISTS bf_sensor.coal_injection_hourly (
    hour_start timestamp without time zone PRIMARY KEY,
    metered_amount_t double precision,
    integrated_amount_t double precision,
    average_rate_tph double precision,
    rate_sample_count integer NOT NULL DEFAULT 0,
    coverage_ratio double precision NOT NULL DEFAULT 0,
    meter_sample_count integer NOT NULL DEFAULT 0,
    meter_sample_ts timestamp without time zone,
    data_until_ts timestamp without time zone,
    hour_complete boolean NOT NULL DEFAULT false,
    semantic_version text NOT NULL DEFAULT 'pci_hourly_meter_and_rate_integral_v1',
    calculated_at timestamp without time zone NOT NULL DEFAULT now(),
    CHECK (coverage_ratio >= 0 AND coverage_ratio <= 1)
);

CREATE INDEX IF NOT EXISTS idx_coal_injection_hourly_calculated
    ON bf_sensor.coal_injection_hourly (calculated_at DESC);

COMMENT ON TABLE bf_sensor.coal_injection_hourly IS
    '2号高炉整点喷煤记录；实测量优先来自 SIO_GL02_PC_T0004，速率积分来自 PCI_rate(t/h)。';

CREATE OR REPLACE VIEW bf_sensor.v_coal_injection_hourly AS
SELECT
    hour_start,
    hour_start + interval '1 hour' AS hour_end,
    metered_amount_t,
    integrated_amount_t,
    CASE
        WHEN hour_complete THEN COALESCE(metered_amount_t, integrated_amount_t)
        ELSE integrated_amount_t
    END AS amount_t,
    CASE
        WHEN hour_complete AND metered_amount_t IS NOT NULL THEN 'SIO_GL02_PC_T0004'
        ELSE 'PCI_rate_time_integral'
    END AS amount_source,
    average_rate_tph,
    rate_sample_count,
    coverage_ratio,
    meter_sample_count,
    meter_sample_ts,
    data_until_ts,
    hour_complete,
    semantic_version,
    calculated_at
FROM bf_sensor.coal_injection_hourly;

CREATE OR REPLACE VIEW bf_sensor.v_coal_injection_current_hour AS
SELECT *
FROM bf_sensor.v_coal_injection_hourly
WHERE hour_start = (SELECT max(hour_start) FROM bf_sensor.coal_injection_hourly);
-- FOREMAN-COAL-HOURLY-20260806-END
