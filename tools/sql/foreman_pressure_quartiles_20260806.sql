-- REQ-FOREMAN-COLD-BLAST-PRESSURE-20260806
-- Compatible extension: persist exact 30-day Q1/Q3 for audited pressure advice.
BEGIN;

ALTER TABLE bf_sensor.daily_baselines
    ADD COLUMN IF NOT EXISTS p25 double precision;

ALTER TABLE bf_sensor.daily_baselines
    ADD COLUMN IF NOT EXISTS p75 double precision;

COMMENT ON COLUMN bf_sensor.daily_baselines.p25 IS
    'Exact 25th percentile calculated from the baseline window; never approximated from median/IQR.';

COMMENT ON COLUMN bf_sensor.daily_baselines.p75 IS
    'Exact 75th percentile calculated from the baseline window; upper cap for cold-blast pressure increases.';

COMMIT;

SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'bf_sensor'
  AND table_name = 'daily_baselines'
  AND column_name IN ('p25', 'p75')
ORDER BY column_name;

SELECT baseline_day, baseline_window_start, baseline_window_end,
       p25, p75, sample_count, coverage_ratio, updated_at
FROM bf_sensor.daily_baselines
WHERE baseline_days = 30
  AND variable_name = 'P_blast_cold'
ORDER BY baseline_day DESC, updated_at DESC
LIMIT 1;
