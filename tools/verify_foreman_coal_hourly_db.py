"""Read-only production verification for the foreman points and coal-hour table."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


EXPECTED_PHYSICAL = (
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
    parser.add_argument("--require-live-points", type=int, default=len(EXPECTED_PHYSICAL))
    args = parser.parse_args()
    root = args.root.resolve()
    sys.path.insert(0, str(root / "src"))
    from pg_store import connect

    config = root / "config" / "sync_config.json"
    conn = connect(config)
    registry = conn.execute(
        """
        SELECT variable_name, tag_long_name, is_derived
        FROM bf_sensor.sensor_registry
        WHERE variable_name = ANY(%s)
        ORDER BY variable_name
        """,
        (list(EXPECTED_PHYSICAL) + ["PCI_current_hour"],),
    ).fetchall()
    latest = conn.execute(
        """
        SELECT r.variable_name, max(v.ts) AS latest_ts, max(v.value) FILTER (
                   WHERE v.ts = latest.latest_ts
               ) AS latest_value
        FROM bf_sensor.sensor_registry r
        LEFT JOIN LATERAL (
            SELECT max(ts) AS latest_ts
            FROM bf_sensor.one_minute_values
            WHERE tag_long_name = r.tag_long_name
        ) latest ON true
        LEFT JOIN bf_sensor.one_minute_values v
          ON v.tag_long_name = r.tag_long_name AND v.ts = latest.latest_ts
        WHERE r.variable_name = ANY(%s)
        GROUP BY r.variable_name, latest.latest_ts
        ORDER BY r.variable_name
        """,
        (list(EXPECTED_PHYSICAL),),
    ).fetchall()
    current = conn.execute(
        """
        SELECT hour_start, amount_t, metered_amount_t, integrated_amount_t,
               average_rate_tph, coverage_ratio, data_until_ts, amount_source
        FROM bf_sensor.v_coal_injection_current_hour
        """
    ).fetchone()
    registered = {row["variable_name"] for row in registry}
    live = {row["variable_name"] for row in latest if row["latest_ts"] is not None and row["latest_value"] is not None}
    current_payload = dict(current) if current else None
    passed = bool(
        len(registered) == len(EXPECTED_PHYSICAL) + 1
        and len(live) >= args.require_live_points
        and current
        and current["integrated_amount_t"] is not None
        and current["integrated_amount_t"] >= 0
        and current["average_rate_tph"] is not None
    )
    result = {
        "passed": passed,
        "registered_count": len(registered),
        "registered_missing": sorted(set(EXPECTED_PHYSICAL + ("PCI_current_hour",)) - registered),
        "physical_live_count": len(live),
        "physical_live_missing": sorted(set(EXPECTED_PHYSICAL) - live),
        "latest": {row["variable_name"]: {"ts": row["latest_ts"], "value": row["latest_value"]} for row in latest},
        "current_hour": current_payload,
    }
    print(json.dumps(result, ensure_ascii=False, default=str, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())

