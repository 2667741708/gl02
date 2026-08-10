"""Read-only audit for storing MES operation-log fuel-ratio report data.

Requirement: REQ-SI-FUELRATIO-MES-REPORT-PERSISTENCE-20260808
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


PROPOSED_TABLES = [
    "bf_imes.mes_operation_log_report_raw",
    "bf_assistant.mes_operation_log_hourly_metrics",
    "bf_assistant.mes_operation_log_heat_metrics",
    "bf_assistant.foreman_fuel_ratio_rule_versions",
    "bf_assistant.foreman_fuel_ratio_si_predictions",
]


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _rows(connection: psycopg.Connection[Any], query: str, args: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(query, args).fetchall()]


def audit(connection: psycopg.Connection[Any]) -> dict[str, Any]:
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
    schemas = _rows(
        connection,
        """
        SELECT schema_name
        FROM information_schema.schemata
        WHERE schema_name IN ('bf_assistant','bf_imes','bf_sensor')
        ORDER BY schema_name
        """,
    )
    proposed = _rows(
        connection,
        "SELECT name, to_regclass(name) AS existing_regclass FROM unnest(%s::text[]) AS t(name) ORDER BY name",
        (PROPOSED_TABLES,),
    )
    relevant_tables = _rows(
        connection,
        """
        SELECT table_schema, table_name, table_type
        FROM information_schema.tables
        WHERE table_schema IN ('bf_assistant','bf_imes','bf_sensor')
          AND (
            table_name ILIKE '%%heat%%'
            OR table_name ILIKE '%%quality%%'
            OR table_name ILIKE '%%imes%%'
            OR table_name ILIKE '%%report%%'
            OR table_name ILIKE '%%coal%%'
            OR table_name ILIKE '%%fuel%%'
            OR table_name ILIKE '%%operation%%'
          )
        ORDER BY table_schema, table_name
        """,
    )
    key_columns = _rows(
        connection,
        """
        SELECT table_schema, table_name, column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE (table_schema, table_name) IN (
            ('bf_assistant','heat_performance_quality_summary'),
            ('bf_sensor','coal_injection_hourly'),
            ('bf_imes','raw_rows')
        )
        ORDER BY table_schema, table_name, ordinal_position
        """,
    )
    operation_log_columns = _rows(
        connection,
        """
        SELECT table_schema, table_name, column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE (table_schema, table_name) IN (
            ('bf_imes','imes_bf2_operation_log_report'),
            ('bf_imes','v_bf2_operation_log_report')
        )
        ORDER BY table_schema, table_name, ordinal_position
        """,
    )
    operation_log_probe: dict[str, Any] = {}
    for table_name in [
        "bf_imes.imes_bf2_operation_log_report",
        "bf_imes.v_bf2_operation_log_report",
    ]:
        try:
            count_row = connection.execute(f"SELECT count(*) AS row_count FROM {table_name}").fetchone()
            operation_log_probe[table_name] = {"row_count": int(count_row["row_count"])}
            operation_log_probe[table_name]["sample_rows"] = _rows(connection, f"SELECT * FROM {table_name} LIMIT 3")
        except Exception as exc:  # pragma: no cover - diagnostic output
            operation_log_probe[table_name] = {
                "error_type": type(exc).__name__,
                "message": str(exc),
            }
    row_counts: dict[str, Any] = {}
    for table_name in [
        "bf_assistant.heat_performance_quality_summary",
        "bf_sensor.coal_injection_hourly",
        "bf_imes.raw_rows",
    ]:
        try:
            row = connection.execute(f"SELECT count(*) AS row_count FROM {table_name}").fetchone()
            row_counts[table_name] = int(row["row_count"])
        except Exception as exc:  # pragma: no cover - diagnostic output
            row_counts[table_name] = {
                "error_type": type(exc).__name__,
                "message": str(exc),
            }
    return {
        "schema": "bf.fuelratio_report_surface_audit.v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "identity": identity,
        "schemas": schemas,
        "proposed_table_conflicts": proposed,
        "relevant_existing_tables": relevant_tables,
        "key_existing_columns": key_columns,
        "operation_log_columns": operation_log_columns,
        "operation_log_probe": operation_log_probe,
        "row_counts": row_counts,
        "write_recommendation": {
            "raw_source_schema": "bf_imes",
            "analysis_schema": "bf_assistant",
            "reason": "Keep MES Web raw report snapshots separate from page-facing derived hourly/heat/rule predictions.",
        },
    }


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description="只读核查220.12是否适合承接MES作业日志燃料比/料速/Si报表数据。")
    cli.add_argument("--output", type=Path, required=True)
    cli.add_argument("--ssh-host", default="10.30.220.12")
    cli.add_argument("--ssh-user", default="administrator")
    cli.add_argument("--remote-pg-host", default="127.0.0.1")
    cli.add_argument("--remote-pg-port", type=int, default=5432)
    cli.add_argument("--local-tunnel-port", type=int, default=15459)
    cli.add_argument("--remote-pg-user", default="gl02_sync")
    cli.add_argument("--remote-pg-db", default="bf_trend")
    cli.add_argument("--connect-timeout", type=int, default=20)
    return cli


def main() -> int:
    args = parser().parse_args()
    args.output = args.output.resolve()
    with legacy_reader.sensor_ssh_tunnel(args) as (port, ssh_client):
        params = legacy_reader.remote_sensor_params(args, port, ssh_client)
        params["options"] = "-c default_transaction_read_only=on -c statement_timeout=60000"
        with psycopg.connect(**params, row_factory=dict_row) as connection:
            result = audit(connection)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "output": str(args.output),
                "proposed_table_conflicts": result["proposed_table_conflicts"],
                "row_counts": result["row_counts"],
            },
            ensure_ascii=False,
            default=_json_default,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
