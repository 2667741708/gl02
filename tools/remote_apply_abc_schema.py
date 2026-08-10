"""Apply the additive ABC33 schema on the controlled 220.12 PostgreSQL."""
from __future__ import annotations

import hashlib
import os
import sys

import psycopg


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: remote_apply_abc_schema.py SQL_PATH")
    sql_path = sys.argv[1]
    sql = open(sql_path, "r", encoding="utf-8").read()
    conninfo = {
        "host": os.environ.get("GL02_PGHOST", "127.0.0.1"),
        "port": int(os.environ.get("GL02_PGPORT", "5432")),
        "dbname": os.environ.get("GL02_PGDATABASE", "bf_trend"),
        "user": os.environ.get("GL02_PGUSER", "gl02_sync"),
        "password": os.environ.get("GL02_PGPASSWORD", ""),
    }
    digest = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    with psycopg.connect(**conninfo) as conn:
        with conn.transaction():
            conn.execute(sql)
        tables = conn.execute(
            """
            SELECT table_schema, table_name FROM information_schema.tables
            WHERE (table_schema, table_name) IN (
              ('bf_sensor','abc_rule_evaluation_batches'),('bf_sensor','abc_rule_evaluation_items'),
              ('bf_assistant','abc_rule_config_versions'),('bf_assistant','abc_alert_episodes'),
              ('bf_assistant','abc_alert_event_log')) ORDER BY table_schema, table_name
            """
        ).fetchall()
    print({"migration": "REQ-ABC33-FURNACE-RULES-20260807", "sql_sha256": digest, "tables": [f"{r[0]}.{r[1]}" for r in tables]})


if __name__ == "__main__":
    main()
