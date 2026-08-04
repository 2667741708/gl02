from __future__ import annotations

import json
import os
import time

import psycopg
from psycopg.rows import dict_row


PARAMETERS = [
    "DP_total",
    "DP_upper",
    "DP_lower",
    "PI",
    "P_blast",
    "T_blast",
    "Q_blast",
    "P_top",
    "T_top_A",
    "T_top_B",
    "T_top_C",
    "T_top_D",
    "PCI_rate",
    "Q_O2",
    "GasUtil",
    "L",
    "L_south",
    "L_north",
]


def elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


conn = psycopg.connect(
    host=os.environ.get("GL02_PGHOST", "10.30.220.12"),
    port=int(os.environ.get("GL02_PGPORT", "5432")),
    dbname=os.environ.get("GL02_PGDATABASE", "bf_trend"),
    user=os.environ["GL02_PGUSER"],
    password=os.environ["GL02_PGPASSWORD"],
    connect_timeout=8,
    row_factory=dict_row,
)
result: dict[str, object] = {}
with conn:
    started = time.perf_counter()
    latest = conn.execute(
        """
        SELECT id, diagnosis_ts, updated_at
        FROM bf_sensor.diagnosis_snapshots
        ORDER BY diagnosis_ts DESC, updated_at DESC, id DESC
        LIMIT 1
        """
    ).fetchone()
    result["diagnosis_latest_ms"] = elapsed_ms(started)
    result["diagnosis_latest"] = latest

    sensor_sql = """
        SELECT DISTINCT ON (r.variable_name) r.variable_name, v.value, v.ts
        FROM bf_sensor.sensor_registry r
        JOIN bf_sensor.one_minute_values v ON v.tag_long_name = r.tag_long_name
        WHERE r.variable_name = ANY(%s)
        ORDER BY r.variable_name, v.ts DESC
    """
    started = time.perf_counter()
    rows = conn.execute(sensor_sql, (PARAMETERS,)).fetchall()
    result["sensor_latest_ms"] = elapsed_ms(started)
    result["sensor_row_count"] = len(rows)

    lateral_sql = """
        SELECT r.variable_name, latest.value, latest.ts
        FROM bf_sensor.sensor_registry r
        CROSS JOIN LATERAL (
            SELECT v.value, v.ts
            FROM bf_sensor.one_minute_values v
            WHERE v.tag_long_name = r.tag_long_name
            ORDER BY v.ts DESC
            LIMIT 1
        ) latest
        WHERE r.variable_name = ANY(%s)
        ORDER BY r.variable_name
    """
    started = time.perf_counter()
    lateral_rows = conn.execute(lateral_sql, (PARAMETERS,)).fetchall()
    result["sensor_lateral_ms"] = elapsed_ms(started)
    result["sensor_lateral_row_count"] = len(lateral_rows)
    lateral_plan = conn.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + lateral_sql, (PARAMETERS,)).fetchone()
    result["sensor_lateral_plan"] = lateral_plan.get("QUERY PLAN") if lateral_plan else None

    plan = conn.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sensor_sql, (PARAMETERS,)).fetchone()
    result["sensor_plan"] = plan.get("QUERY PLAN") if plan else None
    indexes = conn.execute(
        """
        SELECT tablename, indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = 'bf_sensor'
          AND (tablename IN ('sensor_registry', 'one_minute_values') OR tablename LIKE 'one_minute_values_%')
        ORDER BY tablename, indexname
        """
    ).fetchall()
    result["indexes"] = indexes

print(json.dumps(result, ensure_ascii=False, default=str))
