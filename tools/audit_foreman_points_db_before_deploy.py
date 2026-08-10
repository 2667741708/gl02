"""Audit whether confirmed foreman points and their history already exist on 220.12."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


EXPECTED = (
    "PCI_rate",
    "PCI_previous_hour",
    "BlastEnergy",
    "BlastSpeedStd",
    "BlastSpeedActual",
    "Q_soft_water",
    "P_soft_water",
    "Q_high_pressure_water",
    "P_high_pressure_water",
    "P_medium_pressure_water",
    "ExpansionTankLevel",
    "Hopper_weight",
    "Q_N2",
    "P_N2",
    "P_O2_valve_in",
    "P_O2_valve_out",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    sys.path.insert(0, str(root / "src"))
    from pg_store import connect

    conn = connect(root / "config" / "sync_config.json")
    global_span = conn.execute(
        "SELECT min(ts) AS min_ts, max(ts) AS max_ts, count(*) AS rows FROM bf_sensor.one_minute_values"
    ).fetchone()
    rows = conn.execute(
        """
        SELECT
            wanted.variable_name,
            r.short_name,
            r.tag_long_name,
            r.description,
            min(v.ts) AS min_ts,
            max(v.ts) AS max_ts,
            count(v.ts) AS history_rows
        FROM unnest(%s::text[]) AS wanted(variable_name)
        LEFT JOIN bf_sensor.sensor_registry r USING (variable_name)
        LEFT JOIN bf_sensor.one_minute_values v ON v.tag_long_name = r.tag_long_name
        GROUP BY wanted.variable_name, r.short_name, r.tag_long_name, r.description
        ORDER BY wanted.variable_name
        """,
        (list(EXPECTED),),
    ).fetchall()
    hourly_regclass = conn.execute("SELECT to_regclass('bf_sensor.coal_injection_hourly') AS table_name").fetchone()["table_name"]
    result = {
        "global_history": dict(global_span),
        "hourly_table_exists": hourly_regclass is not None,
        "points": [dict(row) for row in rows],
        "registered_count": sum(1 for row in rows if row["tag_long_name"]),
        "with_history_count": sum(1 for row in rows if row["history_rows"]),
    }
    print(json.dumps(result, ensure_ascii=False, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
