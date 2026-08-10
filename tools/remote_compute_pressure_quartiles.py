"""Read-only exact p25/p75 recomputation for existing pressure baselines."""
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
        zero_table = bool(conn.execute("SELECT to_regclass('bf_sensor.zero_value_audits')").fetchone()[0])
        zero_join = ""
        zero_where = ""
        if zero_table:
            zero_join = """
              LEFT JOIN bf_sensor.zero_value_audits z
                ON z.tag_long_name = v.tag_long_name
               AND z.ts = v.ts
               AND z.pspace_aggregate = v.aggregate
            """
            zero_where = "AND (v.value <> 0 OR z.verification_status = 'verified_zero')"
        else:
            zero_where = "AND v.value <> 0"
        rows = conn.execute(
            f"""
            WITH targets AS (
                SELECT id, baseline_day, baseline_window_start, baseline_window_end, variable_name
                FROM bf_sensor.daily_baselines
                WHERE baseline_days=30
                  AND variable_name IN ('P_blast_cold','P_blast')
                  AND (p25 IS NULL OR p75 IS NULL)
            ), minute_values AS (
                SELECT t.id, t.baseline_day, t.variable_name, v.ts,
                       avg(v.value)::double precision AS value
                FROM targets t
                JOIN bf_sensor.sensor_registry r
                  ON r.variable_name=t.variable_name
                 AND r.is_enabled=true AND r.is_derived=false
                JOIN bf_sensor.one_minute_values v
                  ON v.tag_long_name=r.tag_long_name
                 AND v.ts >= t.baseline_window_start
                 AND v.ts <= t.baseline_window_end
                {zero_join}
                WHERE v.value IS NOT NULL {zero_where}
                GROUP BY t.id, t.baseline_day, t.variable_name, v.ts
            )
            SELECT id, baseline_day, variable_name,
                   count(*)::integer AS minute_samples,
                   percentile_cont(0.25) WITHIN GROUP (ORDER BY value) AS p25_calc,
                   percentile_cont(0.75) WITHIN GROUP (ORDER BY value) AS p75_calc
            FROM minute_values
            GROUP BY id, baseline_day, variable_name
            ORDER BY baseline_day DESC, variable_name
            """
        ).fetchall()
        complete = conn.execute(
            """
            SELECT count(*) FILTER (WHERE p25 IS NOT NULL AND p75 IS NOT NULL), count(*)
            FROM bf_sensor.daily_baselines
            WHERE baseline_days=30 AND variable_name IN ('P_blast_cold','P_blast')
            """
        ).fetchone()
        print(json.dumps({
            "zero_value_audits_used": zero_table,
            "existing_complete_rows": int(complete[0]),
            "existing_target_rows": int(complete[1]),
            "recomputed_rows": len(rows),
            "rows": rows,
        }, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
