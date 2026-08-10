"""Read-only audit for north burden-line and sparse ABC state telemetry."""
from __future__ import annotations

import json
import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import psycopg
from psycopg.rows import dict_row


def dsn() -> str:
    values = {
        "host": os.getenv("GL02_PGHOST", os.getenv("PGHOST", "127.0.0.1")),
        "port": os.getenv("GL02_PGPORT", os.getenv("PGPORT", "5432")),
        "dbname": os.getenv("GL02_PGDATABASE", os.getenv("PGDATABASE", "bf_trend")),
        "user": os.getenv("GL02_PGUSER", os.getenv("PGUSER")),
        "password": os.getenv("GL02_PGPASSWORD", os.getenv("PGPASSWORD")),
    }
    if not values["user"] or not values["password"]:
        raise RuntimeError("PostgreSQL runtime credentials are unavailable")
    return " ".join(f"{key}={value}" for key, value in values.items())


def serial(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def main() -> int:
    with psycopg.connect(dsn(), row_factory=dict_row) as conn:
        database_now = conn.execute("SELECT now() AS now").fetchone()["now"]
        line = conn.execute(
            """WITH source AS (
                   SELECT r.variable_name,date_trunc('minute',v.ts) AS minute_ts,avg(v.value) AS value
                   FROM bf_sensor.one_minute_values v
                   JOIN bf_sensor.sensor_registry r USING(tag_long_name)
                   WHERE r.variable_name=ANY(ARRAY['L_north','L_south'])
                     AND v.ts>=current_date-interval '30 days' AND v.ts<current_date
                   GROUP BY r.variable_name,date_trunc('minute',v.ts)
               ), bucketed AS (
                   SELECT variable_name,date_bin(interval '5 minutes',minute_ts,timestamp '2000-01-01') AS bucket,
                          min(value) FILTER(WHERE value>=0) AS effective_minimum,
                          max(value) FILTER(WHERE value>=0) AS effective_maximum,
                          avg(value) FILTER(WHERE value>=0) AS effective_mean
                   FROM source GROUP BY 1,2
               ), paired AS (
                   SELECT n.bucket,n.effective_maximum AS north_max,s.effective_maximum AS south_max,
                          s.effective_maximum-n.effective_maximum AS south_north_bias,
                          n.effective_maximum-lag(n.effective_maximum) OVER(ORDER BY n.bucket) AS north_drop_rate,
                          s.effective_maximum-lag(s.effective_maximum) OVER(ORDER BY s.bucket) AS south_drop_rate
                   FROM bucketed n JOIN bucketed s USING(bucket)
                   WHERE n.variable_name='L_north' AND s.variable_name='L_south'
                     AND n.effective_maximum IS NOT NULL AND s.effective_maximum IS NOT NULL
               )
               SELECT jsonb_object_agg(variable_name,stats) AS probes,
                      (SELECT count(*) FROM paired) AS paired_buckets,
                      (SELECT avg(south_north_bias) FROM paired) AS south_north_bias_mean,
                      (SELECT percentile_cont(array[.1,.25,.5,.75,.9]) WITHIN GROUP(ORDER BY south_north_bias) FROM paired) AS south_north_bias_percentiles,
                      (SELECT percentile_cont(array[.1,.25,.5,.75,.9]) WITHIN GROUP(ORDER BY north_drop_rate) FROM paired WHERE north_drop_rate IS NOT NULL) AS north_drop_rate_percentiles,
                      (SELECT percentile_cont(array[.1,.25,.5,.75,.9]) WITHIN GROUP(ORDER BY south_drop_rate) FROM paired WHERE south_drop_rate IS NOT NULL) AS south_drop_rate_percentiles,
                      (SELECT percentile_cont(array[.1,.25,.5,.75,.9]) WITHIN GROUP(ORDER BY south_drop_rate-north_drop_rate) FROM paired WHERE north_drop_rate IS NOT NULL AND south_drop_rate IS NOT NULL) AS drop_rate_difference_percentiles
               FROM (
                   SELECT variable_name,jsonb_build_object(
                       'raw_minutes',count(*),
                       'nonnegative_minutes',count(*) FILTER(WHERE value>=0),
                       'negative_minutes',count(*) FILTER(WHERE value<0),
                       'raw_percentiles',percentile_cont(array[.1,.25,.5,.75,.9,.95,.99]) WITHIN GROUP(ORDER BY value),
                       'five_minute_buckets',(SELECT count(*) FROM bucketed b WHERE b.variable_name=s.variable_name AND b.effective_maximum IS NOT NULL),
                       'effective_min_percentiles',(SELECT percentile_cont(array[.1,.25,.5,.75,.9,.95,.99]) WITHIN GROUP(ORDER BY effective_minimum) FROM bucketed b WHERE b.variable_name=s.variable_name AND effective_minimum IS NOT NULL),
                       'effective_max_percentiles',(SELECT percentile_cont(array[.1,.25,.5,.75,.9,.95,.99]) WITHIN GROUP(ORDER BY effective_maximum) FROM bucketed b WHERE b.variable_name=s.variable_name AND effective_maximum IS NOT NULL),
                       'effective_mean_percentiles',(SELECT percentile_cont(array[.1,.25,.5,.75,.9,.95,.99]) WITHIN GROUP(ORDER BY effective_mean) FROM bucketed b WHERE b.variable_name=s.variable_name AND effective_mean IS NOT NULL)
                   ) AS stats
                   FROM source s GROUP BY variable_name
               ) probe_stats"""
        ).fetchone()
        sampling = conn.execute(
            """WITH minute_rows AS (
                   SELECT r.variable_name,date_trunc('minute',v.ts) AS minute_ts,
                          avg(v.value) AS value,max(v.aggregate) AS aggregate,
                          max(v.semantic_version) AS semantic_version
                   FROM bf_sensor.one_minute_values v
                   JOIN bf_sensor.sensor_registry r USING(tag_long_name)
                   WHERE v.ts>=now()-interval '24 hours'
                     AND (r.variable_name ~ '^T_body_L([7-9]|1[0-6])_[A-H]$'
                          OR r.variable_name=ANY(%s))
                   GROUP BY r.variable_name,date_trunc('minute',v.ts)
               ), ordered AS (
                   SELECT *,lag(value) OVER(PARTITION BY variable_name ORDER BY minute_ts) AS previous_value,
                          lag(minute_ts) OVER(PARTITION BY variable_name ORDER BY minute_ts) AS previous_ts
                   FROM minute_rows
               )
               SELECT variable_name,count(*) AS observed_minutes,
                      count(*) FILTER(WHERE value=previous_value) AS repeated_value_minutes,
                      max(extract(epoch FROM(minute_ts-previous_ts))/60.0) AS maximum_gap_minutes,
                      max(minute_ts) AS latest_minute,
                      array_agg(DISTINCT aggregate) AS aggregates,
                      array_agg(DISTINCT semantic_version) AS semantic_versions
               FROM ordered GROUP BY variable_name ORDER BY variable_name""",
            (["Q_soft_water", "P_soft_water", "Q_high_pressure_water", "P_high_pressure_water",
              "P_medium_pressure_water", "ExpansionTankLevel", "L_north"],),
        ).fetchall()
        held = conn.execute(
            """SELECT r.variable_name,count(*) AS held_minutes,min(v.ts) AS first_held,
                      max(v.ts) AS latest_held,max(v.quality) AS example_quality
               FROM bf_sensor.one_minute_values v
               JOIN bf_sensor.sensor_registry r USING(tag_long_name)
               WHERE v.ts>=now()-interval '20 minutes'
                 AND v.aggregate='PS_STATE_HOLD'
                 AND v.semantic_version='bounded_state_hold_v1'
               GROUP BY r.variable_name ORDER BY r.variable_name"""
        ).fetchall()
    body = [dict(row) for row in sampling if str(row["variable_name"]).startswith("T_body_")]
    other = [dict(row) for row in sampling if not str(row["variable_name"]).startswith("T_body_")]
    result = {
        "schema_version": "abc33.state-sampling-audit.v1",
        "database_now": database_now,
        "burden_line_30d": dict(line),
        "last_24h": {
            "expected_minutes": 1440,
            "body_point_count": len(body),
            "body_observed_minimum": min((int(row["observed_minutes"]) for row in body), default=0),
            "body_observed_median": sorted((int(row["observed_minutes"]) for row in body))[len(body)//2] if body else 0,
            "body_observed_maximum": max((int(row["observed_minutes"]) for row in body), default=0),
            "body_points": body,
            "other_points": other,
        },
        "state_hold_last_20m": [dict(row) for row in held],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=serial))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
