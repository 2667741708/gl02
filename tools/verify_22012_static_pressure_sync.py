from __future__ import annotations

import json
import os

import psycopg
from psycopg.rows import dict_row


def main() -> int:
    connection = {
        "host": os.getenv("GL02_PGHOST", "127.0.0.1"),
        "port": os.getenv("GL02_PGPORT", "5432"),
        "dbname": os.getenv("GL02_PGDATABASE", "bf_trend"),
        "user": os.environ["GL02_PGUSER"],
        "password": os.environ["GL02_PGPASSWORD"],
        "connect_timeout": 10,
    }
    sql = """
        SELECT
          count(DISTINCT r.variable_name) AS registry_count,
          count(DISTINCT r.variable_name) FILTER (WHERE r.is_enabled) AS enabled_count,
          count(DISTINCT r.variable_name) FILTER (WHERE v.ts >= now() - interval '20 minutes') AS latest_row_count,
          max(v.ts) AS latest_ts
        FROM bf_sensor.sensor_registry r
        LEFT JOIN bf_sensor.one_minute_values v USING(tag_long_name)
        WHERE r.variable_name ~ '^P_static_(lower|middle|upper)_[A-F]$'
    """
    with psycopg.connect(**connection, row_factory=dict_row) as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql)
            result = dict(cursor.fetchone() or {})
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0 if result.get("registry_count") == 18 and result.get("latest_row_count") == 18 else 2


if __name__ == "__main__":
    raise SystemExit(main())
