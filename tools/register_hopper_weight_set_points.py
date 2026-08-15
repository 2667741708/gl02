"""Audit or register the GL02 hopper-weight-set point family on PostgreSQL.

OPS-SENSOR-REGISTRY-HOPPER-WEIGHT-SET-20260814

The command is read-only unless ``--apply`` is supplied.  Registration uses
the authoritative point catalog under ``<root>/config/点位清单.tsv`` and does
not start another pSpace reader.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PHYSICAL_NAMES = tuple(f"Hopper_weight_set_{index:02d}" for index in range(1, 12))
EXPECTED_NAMES = ("L_south", "L_north", *PHYSICAL_NAMES, "Hopper_weight_set")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit or register hopper-weight-set points.")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="Write the selected registry rows.")
    args = parser.parse_args()

    root = args.root.resolve()
    sys.path.insert(0, str(root / "src"))
    from catalog import point_by_variable
    from pg_store import connect, upsert_registry

    config = root / "config" / "sync_config.json"
    catalog = point_by_variable(config)
    missing_catalog = sorted(set(EXPECTED_NAMES) - set(catalog))
    if missing_catalog:
        raise SystemExit(f"Catalog is missing expected variables: {missing_catalog}")

    selected = [catalog[name] for name in EXPECTED_NAMES]
    expected_by_name = {point.variable_name: point for point in selected}
    conn = connect(config)

    tag_conflicts = conn.execute(
        """
        SELECT variable_name, tag_long_name
        FROM bf_sensor.sensor_registry
        WHERE tag_long_name = ANY(%s::text[])
          AND variable_name <> ALL(%s::text[])
        ORDER BY variable_name
        """,
        ([point.tag_long_name for point in selected], list(EXPECTED_NAMES)),
    ).fetchall()
    if tag_conflicts:
        print(json.dumps({"ok": False, "tag_conflicts": [dict(row) for row in tag_conflicts]}, ensure_ascii=False, indent=2))
        return 2

    if args.apply:
        upsert_registry(conn, selected)

    rows = conn.execute(
        """
        SELECT variable_name, short_name, tag_long_name, description,
               status_usage, is_derived, is_enabled, updated_at
        FROM bf_sensor.sensor_registry
        WHERE variable_name = ANY(%s::text[])
        ORDER BY variable_name
        """,
        (list(EXPECTED_NAMES),),
    ).fetchall()
    actual = {row["variable_name"]: row for row in rows}
    mismatches: dict[str, object] = {}
    for name, point in expected_by_name.items():
        row = actual.get(name)
        if row is None:
            mismatches[name] = "missing"
            continue
        if (
            row["short_name"] != point.short_name
            or row["tag_long_name"] != point.tag_long_name
            or bool(row["is_derived"]) != point.is_derived
            or not bool(row["is_enabled"])
        ):
            mismatches[name] = {
                "short_name": row["short_name"],
                "tag_long_name": row["tag_long_name"],
                "is_derived": row["is_derived"],
                "is_enabled": row["is_enabled"],
            }

    history = conn.execute(
        """
        SELECT r.variable_name, max(v.ts) AS latest_ts, count(v.ts)::integer AS history_rows
        FROM bf_sensor.sensor_registry r
        LEFT JOIN bf_sensor.one_minute_values v ON v.tag_long_name = r.tag_long_name
        WHERE r.variable_name = ANY(%s::text[])
        GROUP BY r.variable_name
        ORDER BY r.variable_name
        """,
        (list(PHYSICAL_NAMES),),
    ).fetchall()
    result = {
        "ok": not mismatches and len(rows) == len(EXPECTED_NAMES),
        "mode": "apply" if args.apply else "audit",
        "expected_rows": len(EXPECTED_NAMES),
        "registered_rows": len(rows),
        "physical_components": len(PHYSICAL_NAMES),
        "derived_rows": sum(1 for row in rows if row["is_derived"]),
        "mismatches": mismatches,
        "history": [dict(row) for row in history],
    }
    print(json.dumps(result, ensure_ascii=False, default=str, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
