"""Read-only audit of 220.12 pressure baseline rows and missing quartiles."""
from __future__ import annotations

import json
import os
import psycopg


def main() -> None:
    conninfo = {
        "host": os.environ.get("GL02_PGHOST", "127.0.0.1"),
        "port": int(os.environ.get("GL02_PGPORT", "5432")),
        "dbname": os.environ.get("GL02_PGDATABASE", "bf_trend"),
        "user": os.environ.get("GL02_PGUSER", "gl02_sync"),
        "password": os.environ.get("GL02_PGPASSWORD", ""),
    }
    with psycopg.connect(**conninfo) as conn:
        cols = conn.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema='bf_sensor' AND table_name='daily_baselines'
            ORDER BY ordinal_position
            """
        ).fetchall()
        print(json.dumps({"columns": cols}, ensure_ascii=False, default=str))
        total = conn.execute("SELECT count(*) FROM bf_sensor.daily_baselines").fetchone()[0]
        latest_day = conn.execute("SELECT max(baseline_day) FROM bf_sensor.daily_baselines").fetchone()[0]
        print(json.dumps({"total_rows": total, "latest_day": str(latest_day) if latest_day else None}, ensure_ascii=False))
        names = conn.execute(
            """
            SELECT variable_name, max(baseline_day) AS latest_day,
                   count(*) AS rows,
                   count(*) FILTER (WHERE p25 IS NULL) AS p25_null,
                   count(*) FILTER (WHERE p75 IS NULL) AS p75_null,
                   max(sample_count) AS max_sample_count,
                   max(coverage_ratio) AS max_coverage_ratio
            FROM bf_sensor.daily_baselines
            WHERE lower(variable_name) LIKE '%blast%'
               OR lower(variable_name) LIKE '%pressure%'
               OR lower(variable_name) LIKE '%冷风%'
            GROUP BY variable_name
            ORDER BY variable_name
            """
        ).fetchall()
        print(json.dumps({"pressure_like_variables": names}, ensure_ascii=False, default=str))
        latest = conn.execute(
            """
            SELECT baseline_day, variable_name, p10, p25, p50, p75, p90,
                   sample_count, coverage_ratio, updated_at, source, baseline_days,
                   baseline_window_start, baseline_window_end
            FROM bf_sensor.daily_baselines
            WHERE baseline_day = (SELECT max(baseline_day) FROM bf_sensor.daily_baselines)
              AND (lower(variable_name) LIKE '%blast%'
                   OR lower(variable_name) LIKE '%pressure%'
                   OR lower(variable_name) LIKE '%冷风%')
            ORDER BY variable_name
            """
        ).fetchall()
        print(json.dumps({"latest_pressure_rows": latest}, ensure_ascii=False, default=str))
        target = conn.execute(
            """
            SELECT baseline_day, variable_name, p10, p25, p50, p75, p90,
                   sample_count, coverage_ratio, updated_at, source, baseline_days,
                   baseline_window_start, baseline_window_end
            FROM bf_sensor.daily_baselines
            WHERE variable_name IN ('P_blast_cold','P_blast','p_blast_cold','冷风压力')
            ORDER BY baseline_day DESC, variable_name
            LIMIT 20
            """
        ).fetchall()
        print(json.dumps({"target_rows": target}, ensure_ascii=False, default=str))
        coverage = conn.execute(
            """
            SELECT variable_name,
                   count(*) AS rows,
                   count(*) FILTER (WHERE p25 IS NOT NULL AND p75 IS NOT NULL) AS complete_quartile_rows,
                   min(baseline_day) AS first_day,
                   max(baseline_day) AS last_day,
                   array_agg(baseline_day ORDER BY baseline_day DESC)
                     FILTER (WHERE p25 IS NULL OR p75 IS NULL) AS missing_days
            FROM bf_sensor.daily_baselines
            WHERE variable_name IN ('P_blast_cold','P_blast') AND baseline_days=30
            GROUP BY variable_name
            ORDER BY variable_name
            """
        ).fetchall()
        print(json.dumps({"quartile_coverage": coverage}, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
