from __future__ import annotations

import json
import os
import psycopg
from psycopg.rows import dict_row


def main() -> None:
    conninfo = {
        "host": os.environ.get("GL02_PGHOST", "127.0.0.1"),
        "port": int(os.environ.get("GL02_PGPORT", "5432")),
        "dbname": os.environ.get("GL02_PGDATABASE", "bf_trend"),
        "user": os.environ.get("GL02_PGUSER", "gl02_sync"),
        "password": os.environ.get("GL02_PGPASSWORD", ""),
    }
    with psycopg.connect(**conninfo, row_factory=dict_row) as conn:
        rows = conn.execute(
            """
            SELECT variable_name, count(*) AS rows,
                   count(*) FILTER (WHERE p25 IS NOT NULL AND p75 IS NOT NULL) AS complete,
                   count(*) FILTER (WHERE p25 IS NULL OR p75 IS NULL) AS missing,
                   max(baseline_day) AS latest_day
            FROM bf_sensor.daily_baselines
            WHERE baseline_days=30 AND variable_name IN ('P_blast_cold','P_blast')
            GROUP BY variable_name ORDER BY variable_name
            """
        ).fetchall()
        latest = conn.execute(
            """
            SELECT baseline_day, variable_name, p25, p75, sample_count, coverage_ratio, updated_at
            FROM bf_sensor.daily_baselines
            WHERE baseline_days=30 AND variable_name='P_blast_cold'
            ORDER BY baseline_day DESC, updated_at DESC LIMIT 1
            """
        ).fetchone()
        print(json.dumps({"rows": rows, "latest_pressure": latest}, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
