from __future__ import annotations

import json
import os

import psycopg
from psycopg.rows import dict_row


VARIABLES = [
    "P_top", "DP_total", "DP_upper", "DP_lower", "Q_blast", "P_blast", "PI", "GasUtil",
    "TFT", "T_taphole_1", "T_taphole_2", "T_top_A", "T_top_B", "T_top_C", "T_top_D",
    "L_south", "L_north", "Q_soft_water", "P_soft_water", "Q_high_pressure_water",
    "P_high_pressure_water", "P_medium_pressure_water", "ExpansionTankLevel",
]


def main() -> int:
    values = {
        "host": os.getenv("GL02_PGHOST", "127.0.0.1"),
        "port": os.getenv("GL02_PGPORT", "5432"),
        "dbname": os.getenv("GL02_PGDATABASE", "bf_trend"),
        "user": os.getenv("GL02_PGUSER"),
        "password": os.getenv("GL02_PGPASSWORD"),
    }
    if not values["user"] or not values["password"]:
        raise RuntimeError("PostgreSQL runtime credentials are unavailable")
    dsn = " ".join(f"{key}={value}" for key, value in values.items())
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        rows = conn.execute(
            """WITH clock AS (SELECT max(ts) AS evaluation_ts FROM bf_sensor.one_minute_values),
               minute_rows AS (
                 SELECT r.variable_name,date_trunc('minute',v.ts) AS minute_ts,max(v.aggregate) AS aggregate
                 FROM bf_sensor.one_minute_values v JOIN bf_sensor.sensor_registry r USING(tag_long_name),clock c
                 WHERE r.variable_name=ANY(%s) AND v.ts>c.evaluation_ts-interval '90 minutes'
                 GROUP BY r.variable_name,date_trunc('minute',v.ts)
               ), latest_baseline AS (
                 SELECT DISTINCT ON(variable_name) variable_name,baseline_day,coverage_ratio,median_ref,iqr_ref
                 FROM bf_sensor.daily_baselines
                 WHERE variable_name=ANY(%s)
                 ORDER BY variable_name,baseline_day DESC
               )
               SELECT v.variable_name,c.evaluation_ts,max(m.minute_ts) AS latest_minute,
                      count(*) FILTER(WHERE m.minute_ts>c.evaluation_ts-interval '15 minutes') AS minutes_15,
                      count(*) FILTER(WHERE m.minute_ts>c.evaluation_ts-interval '30 minutes') AS minutes_30,
                      count(*) FILTER(WHERE m.minute_ts>c.evaluation_ts-interval '60 minutes') AS minutes_60,
                      count(m.minute_ts) AS minutes_90,
                      count(*) FILTER(WHERE m.aggregate='PS_STATE_HOLD') AS held_90,
                      b.baseline_day,b.coverage_ratio AS baseline_coverage,b.median_ref,b.iqr_ref
               FROM unnest(%s::text[]) v(variable_name) CROSS JOIN clock c
               LEFT JOIN minute_rows m ON m.variable_name=v.variable_name
               LEFT JOIN latest_baseline b ON b.variable_name=v.variable_name
               GROUP BY v.variable_name,c.evaluation_ts,b.baseline_day,b.coverage_ratio,b.median_ref,b.iqr_ref
               ORDER BY v.variable_name""",
            (VARIABLES, VARIABLES, VARIABLES),
        ).fetchall()
    print(json.dumps([dict(row) for row in rows], ensure_ascii=False, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
