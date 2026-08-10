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

