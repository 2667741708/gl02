"""Read-only inventory for 220.12 Si prediction inputs.

Requirement: REQ-SI-HEAT-AVERAGE-CURVE-20260806
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

import build_hot_metal_si_dataset as legacy_reader


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = (
    ROOT / "PT" / "高炉3D模型" / "docs" / "GL02传感器点位清单.v1.json"
)


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _catalog_short_names(path: Path) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    points = payload.get("points") or []
    return {
        str((point.get("database") or {}).get("short_name") or "").strip()
        for point in points
        if str((point.get("database") or {}).get("short_name") or "").strip()
    }


def audit(connection: psycopg.Connection[Any], catalog_path: Path) -> dict[str, Any]:
    """Return schema, heat-label and sensor-catalog evidence without credentials."""

    identity = dict(
        connection.execute(
            """
            SELECT current_database() AS database,
                   current_user AS current_user,
                   current_setting('transaction_read_only') AS read_only,
                   localtimestamp AS database_now
            """
        ).fetchone()
    )
    heat_bounds = dict(
        connection.execute(
            """
            SELECT count(*) AS heat_rows,
                   min(open_ts) AS min_open_ts,
                   max(open_ts) AS max_open_ts,
                   count(*) FILTER (WHERE si_avg IS NOT NULL) AS si_avg_rows,
                   max(aggregated_at) AS max_aggregated_at
            FROM bf_assistant.heat_performance_quality_summary
            """
        ).fetchone()
    )
    recent = dict(
        connection.execute(
            """
            WITH boundary AS (
                SELECT max(open_ts) AS max_open_ts
                FROM bf_assistant.heat_performance_quality_summary
                WHERE si_avg IS NOT NULL
            )
            SELECT count(*) AS heat_rows,
                   count(*) FILTER (WHERE si_avg IS NOT NULL) AS si_avg_rows,
                   min(open_ts) AS min_open_ts,
                   max(open_ts) AS max_open_ts,
                   min(si_avg) AS min_si_avg,
                   max(si_avg) AS max_si_avg,
                   avg(si_avg) AS mean_si_avg,
                   sum(hot_metal_sample_count) AS sample_rows
            FROM bf_assistant.heat_performance_quality_summary, boundary
            WHERE open_ts >= boundary.max_open_ts - interval '15 days'
              AND open_ts <= boundary.max_open_ts
            """
        ).fetchone()
    )
    registry = legacy_reader.fetch_registry(connection)
    frozen = _catalog_short_names(catalog_path)
    physical = [
        row for row in registry if not bool(row.get("is_derived"))
    ]
    derived = [
        {
            "short_name": row.get("short_name"),
            "variable_name": row.get("variable_name"),
            "chinese_name": row.get("chinese_name"),
            "tag_long_name": row.get("tag_long_name"),
            "branch": row.get("branch"),
        }
        for row in registry
        if bool(row.get("is_derived"))
    ]
    added = [
        {
            "short_name": row.get("short_name"),
            "variable_name": row.get("variable_name"),
            "chinese_name": row.get("chinese_name"),
            "tag_long_name": row.get("tag_long_name"),
            "branch": row.get("branch"),
        }
        for row in physical
        if str(row.get("short_name") or "") not in frozen
    ]
    candidate_columns = [
        dict(row)
        for row in connection.execute(
            """
            SELECT table_schema, table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
              AND (
                   lower(table_name) ~ '(heat|melt|chem|material|batch|coal|pci|quality|imes|sinter|insp|sample|feed|ore)'
                OR lower(column_name) ~ '(heat|melt|si_|chem|material|batch|coal|pci|tfe|feo|sio2|al2o3|cao|mgo)'
              )
            ORDER BY table_schema, table_name, ordinal_position
            """
        ).fetchall()
    ]
    table_counts = [
        dict(row)
        for row in connection.execute(
            """
            SELECT 'bf_assistant.heat_performance_quality_summary' AS object_name,
                   count(*) AS row_count,
                   max(open_ts) AS max_ts
            FROM bf_assistant.heat_performance_quality_summary
            UNION ALL
            SELECT 'bf_sensor.coal_injection_hourly', count(*), max(hour_start)
            FROM bf_sensor.coal_injection_hourly
            """
        ).fetchall()
    ]
    return {
        "schema": "bf.si_prediction_source_audit.v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "identity": identity,
        "heat_summary": heat_bounds,
        "latest_15_days": recent,
        "sensor_registry": {
            "enabled_rows": len(registry),
            "enabled_physical_rows": len(physical),
            "enabled_derived_rows": len(derived),
            "derived_points": derived,
            "frozen_catalog_rows": len(frozen),
            "new_physical_rows": len(added),
            "new_physical_points": added,
        },
        "candidate_schema_columns": candidate_columns,
        "key_table_counts": table_counts,
    }


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(
        description="只读核对220.12平均Si、IMES化学成分与新增预测点位。"
    )
    cli.add_argument("--output", type=Path, required=True)
    cli.add_argument("--sensor-catalog", type=Path, default=DEFAULT_CATALOG)
    cli.add_argument("--ssh-host", default="10.30.220.12")
    cli.add_argument("--ssh-user", default="administrator")
    cli.add_argument("--remote-pg-host", default="127.0.0.1")
    cli.add_argument("--remote-pg-port", type=int, default=5432)
    cli.add_argument("--local-tunnel-port", type=int, default=15449)
    cli.add_argument("--remote-pg-user", default="gl02_sync")
    cli.add_argument("--remote-pg-db", default="bf_trend")
    cli.add_argument("--connect-timeout", type=int, default=20)
    return cli


def main() -> int:
    args = parser().parse_args()
    args.output = args.output.resolve()
    args.sensor_catalog = args.sensor_catalog.resolve()
    with legacy_reader.sensor_ssh_tunnel(args) as (port, ssh_client):
        params = legacy_reader.remote_sensor_params(args, port, ssh_client)
        params["options"] = (
            "-c default_transaction_read_only=on -c statement_timeout=120000"
        )
        with psycopg.connect(**params, row_factory=dict_row) as connection:
            result = audit(connection, args.sensor_catalog)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "ok": True,
                "output": str(args.output),
                "latest_15_days": result["latest_15_days"],
                "sensor_registry": result["sensor_registry"],
            },
            ensure_ascii=False,
            default=_json_default,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
