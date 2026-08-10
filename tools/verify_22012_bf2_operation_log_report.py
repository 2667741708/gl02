"""Read-only verification for the 220.12 IMES report dataset."""
from __future__ import annotations

import json
import os

import psycopg
from psycopg.rows import dict_row


def main() -> int:
    conninfo = {
        "host": os.environ.get("GL02_PGHOST", "127.0.0.1"),
        "port": int(os.environ.get("GL02_PGPORT", "5432")),
        "dbname": os.environ.get("GL02_PGDATABASE", "bf_trend"),
        "user": os.environ.get("GL02_PGUSER", ""),
        "password": os.environ.get("GL02_PGPASSWORD", ""),
        "connect_timeout": 10,
    }
    with psycopg.connect(**conninfo, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute(
                """
                SELECT COUNT(*) AS rows_count,
                       COUNT(DISTINCT workdate) AS days_count,
                       MIN(workdate) AS min_workdate,
                       MAX(workdate) AS max_workdate,
                       COUNT(*) FILTER (WHERE report_fuel_ratio IS NOT NULL) AS fuel_ratio_count,
                       COUNT(*) FILTER (WHERE material_rate IS NOT NULL) AS material_rate_count
                FROM bf_imes.v_bf2_operation_log_report
                """
            )
            summary = dict(cur.fetchone())
            cur.execute(
                """
                SELECT workdate, COUNT(*) AS rows_count
                FROM bf_imes.v_bf2_operation_log_report
                GROUP BY workdate
                ORDER BY workdate DESC
                LIMIT 5
                """
            )
            recent = [dict(row) for row in cur.fetchall()]
            cur.execute(
                """
                SELECT COUNT(*) AS duplicate_keys
                FROM (
                    SELECT workdate, report_row_number, COUNT(*) AS n
                    FROM bf_imes.v_bf2_operation_log_report
                    GROUP BY workdate, report_row_number
                    HAVING COUNT(*) > 1
                ) duplicates
                """
            )
            duplicate_keys = dict(cur.fetchone())
    print(json.dumps({"ok": True, "summary": summary, "recent": recent, **duplicate_keys}, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

