"""Refresh 2# furnace hourly coal amounts from the existing PostgreSQL minute feed."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


REFRESH_SQL = r"""
WITH point_tags AS (
    SELECT
        max(tag_long_name) FILTER (WHERE variable_name = 'PCI_rate') AS rate_tag,
        max(tag_long_name) FILTER (WHERE variable_name = 'PCI_previous_hour') AS meter_tag
    FROM bf_sensor.sensor_registry
    WHERE is_enabled = true
),
hours AS (
    SELECT generate_series(
        date_trunc('hour', %(from_ts)s::timestamp) - interval '1 hour',
        date_trunc('hour', %(to_ts)s::timestamp),
        interval '1 hour'
    ) AS hour_start
),
rate_agg AS (
    SELECT
        date_trunc('hour', v.ts) AS hour_start,
        sum(v.value * least(greatest(coalesce(v.interval_seconds, 60), 1), 60) / 3600.0) AS integrated_amount_t,
        avg(v.value) AS average_rate_tph,
        count(*)::integer AS rate_sample_count,
        least(1.0, sum(least(greatest(coalesce(v.interval_seconds, 60), 1), 60)) / 3600.0) AS coverage_ratio,
        max(v.ts) AS data_until_ts
    FROM bf_sensor.one_minute_values v
    CROSS JOIN point_tags p
    WHERE p.rate_tag IS NOT NULL
      AND v.tag_long_name = p.rate_tag
      AND v.ts >= date_trunc('hour', %(from_ts)s::timestamp) - interval '1 hour'
      AND v.ts < date_trunc('hour', %(to_ts)s::timestamp) + interval '1 hour'
      AND v.value IS NOT NULL
      AND (v.quality IS NULL OR lower(v.quality) LIKE 'good%%')
    GROUP BY date_trunc('hour', v.ts)
),
meter_agg AS (
    SELECT
        date_trunc('hour', v.ts) - interval '1 hour' AS hour_start,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY v.value) AS metered_amount_t,
        count(*)::integer AS meter_sample_count,
        max(v.ts) AS meter_sample_ts
    FROM bf_sensor.one_minute_values v
    CROSS JOIN point_tags p
    WHERE p.meter_tag IS NOT NULL
      AND v.tag_long_name = p.meter_tag
      AND v.ts >= date_trunc('hour', %(from_ts)s::timestamp)
      AND v.ts < date_trunc('hour', %(to_ts)s::timestamp) + interval '1 hour'
      AND v.value IS NOT NULL
      AND (v.quality IS NULL OR lower(v.quality) LIKE 'good%%')
    GROUP BY date_trunc('hour', v.ts) - interval '1 hour'
),
prepared AS (
    SELECT
        h.hour_start,
        m.metered_amount_t,
        r.integrated_amount_t,
        r.average_rate_tph,
        coalesce(r.rate_sample_count, 0) AS rate_sample_count,
        coalesce(r.coverage_ratio, 0) AS coverage_ratio,
        coalesce(m.meter_sample_count, 0) AS meter_sample_count,
        m.meter_sample_ts,
        r.data_until_ts,
        coalesce(r.data_until_ts >= h.hour_start + interval '1 hour' - interval '1 minute', false) AS hour_complete
    FROM hours h
    LEFT JOIN rate_agg r USING (hour_start)
    LEFT JOIN meter_agg m USING (hour_start)
    WHERE r.hour_start IS NOT NULL OR m.hour_start IS NOT NULL
),
upserted AS (
    INSERT INTO bf_sensor.coal_injection_hourly (
        hour_start, metered_amount_t, integrated_amount_t, average_rate_tph,
        rate_sample_count, coverage_ratio, meter_sample_count, meter_sample_ts,
        data_until_ts, hour_complete, semantic_version, calculated_at
    )
    SELECT
        hour_start, metered_amount_t, integrated_amount_t, average_rate_tph,
        rate_sample_count, coverage_ratio, meter_sample_count, meter_sample_ts,
        data_until_ts, hour_complete, 'pci_hourly_meter_and_rate_integral_v1', now()
    FROM prepared
    ON CONFLICT (hour_start) DO UPDATE SET
        metered_amount_t = excluded.metered_amount_t,
        integrated_amount_t = excluded.integrated_amount_t,
        average_rate_tph = excluded.average_rate_tph,
        rate_sample_count = excluded.rate_sample_count,
        coverage_ratio = excluded.coverage_ratio,
        meter_sample_count = excluded.meter_sample_count,
        meter_sample_ts = excluded.meter_sample_ts,
        data_until_ts = excluded.data_until_ts,
        hour_complete = excluded.hour_complete,
        semantic_version = excluded.semantic_version,
        calculated_at = excluded.calculated_at
    RETURNING hour_start
)
SELECT count(*)::integer AS refreshed_rows, min(hour_start) AS first_hour, max(hour_start) AS last_hour
FROM upserted;
"""


def refresh_coal_injection_hourly(conn: Any, start: datetime, end: datetime) -> dict[str, Any]:
    """Refresh affected hour rows; a failure is reported without stopping primary sync."""
    try:
        row = conn.execute(REFRESH_SQL, {"from_ts": start, "to_ts": end}).fetchone()
        conn.commit()
        return {
            "status": "ok",
            "refreshed_rows": int(row["refreshed_rows"] or 0),
            "first_hour": row["first_hour"].isoformat(sep=" ") if row["first_hour"] else None,
            "last_hour": row["last_hour"].isoformat(sep=" ") if row["last_hour"] else None,
        }
    except Exception as exc:  # preserve the primary 1-minute sensor pipeline
        conn.rollback()
        return {"status": "error", "error": str(exc)[:500]}


def current_hour_bounds(now: datetime) -> tuple[datetime, datetime]:
    start = now.replace(minute=0, second=0, microsecond=0)
    return start, now
