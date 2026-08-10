from __future__ import annotations

import json
import os

import psycopg
from psycopg.rows import dict_row


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
            """WITH latest AS (
                   SELECT id,evaluation_ts,config_version FROM bf_sensor.abc_rule_evaluation_batches
                   ORDER BY evaluation_ts DESC,id DESC LIMIT 1
               )
               SELECT l.id AS batch_id,l.evaluation_ts,l.config_version,i.rule_id,i.status,
                      i.confidence,i.missing_features
               FROM latest l JOIN bf_sensor.abc_rule_evaluation_items i ON i.batch_id=l.id
               ORDER BY i.rule_id"""
        ).fetchall()
    print(json.dumps([dict(row) for row in rows], ensure_ascii=False, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
