from __future__ import annotations

import json
import os
from datetime import date, datetime
from decimal import Decimal

import psycopg
from psycopg.rows import dict_row


def json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(type(value).__name__)


def main() -> None:
    password = os.environ.get("GL02_PGPASSWORD")
    if not password:
        raise RuntimeError("GL02_PGPASSWORD is unavailable")
    params = {
        "host": os.environ.get("GL02_PGHOST", "127.0.0.1"),
        "port": int(os.environ.get("GL02_PGPORT", "5432")),
        "dbname": os.environ.get("GL02_PGDATABASE", "bf_trend"),
        "user": os.environ.get("GL02_PGUSER", "gl02_sync"),
        "password": password,
        "connect_timeout": 5,
        "options": "-c default_transaction_read_only=on -c statement_timeout=15000",
    }
    with psycopg.connect(**params, row_factory=dict_row) as connection:
        mirror = connection.execute(
            """
            SELECT dataset_key,
                   count(*) AS row_count,
                   max(COALESCE(fetched_at, updated_at)) AS latest_mirrored_at,
                   max(COALESCE(row_json->>'meltNo', row_json->>'meltno')) AS max_meltno
              FROM bf_imes.raw_rows
             WHERE dataset_key IN (
                       'bf2_output_list_cond_data',
                       'bf2_heat_lab_list_cond_data_avg2',
                       'bf2_heat_lab_all_list_cond_data_avg2_new'
                   )
             GROUP BY dataset_key
             ORDER BY dataset_key
            """
        ).fetchall()
        summary = connection.execute(
            """
            SELECT meltno, work_date, open_ts, si_avg, source_status,
                   source_updated_at, aggregated_at
              FROM bf_assistant.heat_performance_quality_summary
             WHERE future_pending IS NOT TRUE
             ORDER BY open_ts DESC NULLS LAST
             LIMIT 3
            """
        ).fetchall()
        latest_mirror_rows = connection.execute(
            """
            SELECT dataset_key,
                   COALESCE(row_json->>'meltNo', row_json->>'meltno') AS meltno,
                   row_json->>'workDate' AS work_date,
                   row_json->>'openTime' AS open_time,
                   row_json->>'closeTime' AS close_time,
                   row_json->>'value_02' AS si,
                   COALESCE(fetched_at, updated_at) AS mirrored_at
              FROM bf_imes.raw_rows
             WHERE dataset_key IN (
                       'bf2_output_list_cond_data',
                       'bf2_heat_lab_list_cond_data_avg2'
                   )
               AND COALESCE(row_json->>'meltNo', row_json->>'meltno') LIKE '2#%'
             ORDER BY COALESCE(row_json->>'meltNo', row_json->>'meltno') DESC,
                      dataset_key
             LIMIT 8
            """
        ).fetchall()
        db_now = connection.execute("SELECT now() AS db_now").fetchone()["db_now"]
    payload = {
        "db_now": db_now,
        "mirror_datasets": [dict(row) for row in mirror],
        "latest_mirror_rows": [dict(row) for row in latest_mirror_rows],
        "latest_summaries": [dict(row) for row in summary],
    }
    print(json.dumps(payload, ensure_ascii=False, default=json_default))


if __name__ == "__main__":
    main()
