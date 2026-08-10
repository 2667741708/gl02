"""Read-only 220.12 probe for the ABC33 migration gate."""
from __future__ import annotations

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
        rows = conn.execute(
            """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE (table_schema, table_name) IN (
              ('bf_sensor','abc_rule_evaluation_batches'),
              ('bf_sensor','abc_rule_evaluation_items'),
              ('bf_assistant','abc_rule_config_versions'),
              ('bf_assistant','abc_alert_episodes'),
              ('bf_assistant','abc_alert_event_log')
            ) ORDER BY table_schema, table_name
            """
        ).fetchall()
        print({"tables": [f"{row[0]}.{row[1]}" for row in rows]})
        for table in ("bf_sensor.abc_rule_evaluation_batches", "bf_sensor.abc_rule_evaluation_items"):
            exists = conn.execute("SELECT to_regclass(%s)", (table,)).fetchone()[0]
            if exists:
                print({"table": table, "count": conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]})


if __name__ == "__main__":
    main()
