"""Read-only per-point history coverage audit without scanning unrelated rows."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


VARIABLES = (
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
    rows = conn.execute(
        """
        SELECT r.variable_name,
               r.tag_long_name,
               history.first_ts,
               history.last_ts,
               history.row_count
        FROM bf_sensor.sensor_registry r
        LEFT JOIN LATERAL (
            SELECT min(v.ts) AS first_ts,
                   max(v.ts) AS last_ts,
                   count(*) AS row_count
            FROM bf_sensor.one_minute_values v
            WHERE v.tag_long_name = r.tag_long_name
        ) history ON true
        WHERE r.variable_name = ANY(%s)
        ORDER BY r.variable_name
        """,
        (list(VARIABLES),),
    ).fetchall()
    print(json.dumps([dict(row) for row in rows], ensure_ascii=False, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
