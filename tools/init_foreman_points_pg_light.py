"""Apply the foreman schema and registry without scanning the 21M-row history table."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    sys.path.insert(0, str(root / "src"))
    from catalog import load_points, physical_points
    from pg_store import connect, upsert_registry

    config = root / "config" / "sync_config.json"
    conn = connect(config)
    schema_text = (root / "schema" / "postgresql_required_points.sql").read_text(encoding="utf-8")
    begin = "-- FOREMAN-COAL-HOURLY-20260806-BEGIN"
    end = "-- FOREMAN-COAL-HOURLY-20260806-END"
    if begin not in schema_text or end not in schema_text:
        raise RuntimeError("Foreman hourly migration block is missing")
    migration = schema_text.split(begin, 1)[1].split(end, 1)[0]
    conn.execute(migration)
    conn.commit()
    points = load_points(config, include_derived=True)
    upsert_registry(conn, points)
    confirmed = conn.execute(
        """
        SELECT count(*)::integer AS n
        FROM bf_sensor.sensor_registry
        WHERE variable_name = ANY(%s::text[])
        """,
        ([
            "CO_top", "CO2_top", "H2_top", "PCI_previous_hour", "BlastEnergy", "BlastSpeedStd", "BlastSpeedActual",
            "Q_soft_water", "P_soft_water", "Q_high_pressure_water", "P_high_pressure_water",
            "P_medium_pressure_water", "ExpansionTankLevel", "Hopper_weight", "Q_N2", "P_N2",
            "P_O2_valve_in", "P_O2_valve_out", "PCI_current_hour",
        ],),
    ).fetchone()["n"]
    print(json.dumps({
        "ok": confirmed == 19,
        "logical_points": len(points),
        "physical_points": len(physical_points(config)),
        "confirmed_foreman_points": confirmed,
    }, ensure_ascii=False, indent=2))
    return 0 if confirmed == 19 else 2


if __name__ == "__main__":
    raise SystemExit(main())
