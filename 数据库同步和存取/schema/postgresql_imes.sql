CREATE SCHEMA IF NOT EXISTS bf_imes;

CREATE TABLE IF NOT EXISTS bf_imes.dataset_catalog (
    dataset_key text PRIMARY KEY,
    dataset_label text NOT NULL,
    endpoint text NOT NULL,
    table_name text NOT NULL,
    columns_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    notes text NOT NULL DEFAULT '',
    updated_at timestamp without time zone NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bf_imes.fetch_runs (
    id bigserial PRIMARY KEY,
    started_at timestamp without time zone NOT NULL DEFAULT now(),
    finished_at timestamp without time zone,
    sync_mode text NOT NULL,
    dataset_key text NOT NULL,
    dataset_label text NOT NULL,
    workdate date,
    endpoint text NOT NULL,
    params_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    rows_read integer NOT NULL DEFAULT 0,
    rows_written integer NOT NULL DEFAULT 0,
    total integer,
    error text NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS bf_imes.raw_rows (
    dataset_key text NOT NULL,
    row_key text NOT NULL,
    dataset_label text NOT NULL,
    endpoint text NOT NULL,
    workdate date,
    workdate2 text,
    lot text,
    charge text,
    prodcentercode text,
    row_json jsonb NOT NULL,
    fetched_at timestamp without time zone,
    updated_at timestamp without time zone NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset_key, row_key)
);

CREATE INDEX IF NOT EXISTS idx_bf_imes_raw_rows_workdate
    ON bf_imes.raw_rows (workdate, dataset_key);

CREATE INDEX IF NOT EXISTS idx_bf_imes_raw_rows_charge
    ON bf_imes.raw_rows (charge, workdate);

CREATE OR REPLACE VIEW bf_imes.v_bf2_batch_input_detail AS
SELECT
    dataset_key,
    dataset_label,
    workdate,
    workdate2,
    charge,
    lot,
    prodcentercode,
    row_json ->> 'value_01' AS value_01,
    row_json ->> 'value_02' AS value_02,
    row_json ->> 'value_03' AS value_03,
    row_json ->> 'value_04' AS value_04,
    row_json ->> 'value_05' AS value_05,
    row_json ->> 'value_06' AS value_06,
    row_json ->> 'value_07' AS value_07,
    row_json ->> 'value_08' AS value_08,
    row_json ->> 'value_09' AS value_09,
    row_json ->> 'value_10' AS value_10,
    row_json ->> 'value_11' AS value_11,
    row_json ->> 'value_12' AS value_12,
    row_json ->> 'value_13' AS value_13,
    row_json ->> 'value_14' AS value_14,
    row_json ->> 'value_15' AS value_15,
    row_json ->> 'value_16' AS value_16,
    row_json ->> 'value_17' AS value_17,
    row_json ->> 'value_18' AS value_18,
    row_json ->> 'value_19' AS value_19,
    row_json ->> 'value_20' AS value_20,
    row_json ->> 'value_21' AS value_21,
    row_json ->> 'value_22' AS value_22,
    row_json ->> 'value_23' AS value_23,
    row_json ->> 'value_24' AS value_24,
    row_json ->> 'value_sum' AS value_sum,
    row_json ->> 'mining_batch_sum' AS mining_batch_sum,
    row_json ->> 'coke_charge_sum' AS coke_charge_sum,
    fetched_at,
    updated_at
FROM bf_imes.raw_rows
WHERE dataset_key IN ('bf2_batch_all_rows', 'bf2_batch_mining', 'bf2_batch_coke');

CREATE OR REPLACE VIEW bf_imes.v_bf2_operation_log_report AS
SELECT
    dataset_key,
    dataset_label,
    workdate,
    NULLIF(row_json ->> 'report_row_number', '')::integer AS report_row_number,
    row_json ->> 'report_id' AS report_id,
    row_json ->> 'report_time_raw' AS report_time_raw,
    row_json ->> 'report_time_display' AS report_time_display,
    NULLIF(row_json ->> 'report_batch_count', '')::numeric AS report_batch_count,
    NULLIF(row_json ->> 'report_ore_batch', '')::numeric AS report_ore_batch,
    NULLIF(row_json ->> 'report_coke_batch', '')::numeric AS report_coke_batch,
    NULLIF(row_json ->> 'report_coke_breeze', '')::numeric AS report_coke_breeze,
    NULLIF(row_json ->> 'report_moisture', '')::numeric AS report_moisture,
    NULLIF(row_json ->> 'report_pulverized_coal', '')::numeric AS report_pulverized_coal,
    NULLIF(row_json ->> 'report_coal_ratio', '')::numeric AS report_coal_ratio,
    NULLIF(row_json ->> 'report_fuel_ratio', '')::numeric AS report_fuel_ratio,
    NULLIF(row_json ->> 'material_rate', '')::numeric AS material_rate,
    row_json ->> 'material_rate_status' AS material_rate_status,
    row_json ->> 'material_rate_note' AS material_rate_note,
    row_json -> 'headers' AS report_headers,
    row_json -> 'cells' AS report_cells,
    fetched_at,
    updated_at
FROM bf_imes.raw_rows
WHERE dataset_key = 'bf2_operation_log_report';
