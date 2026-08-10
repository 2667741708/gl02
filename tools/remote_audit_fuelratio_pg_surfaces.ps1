$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$python = 'C:\Program Files\Python311\python.exe'
$scriptPath = Join-Path $env:TEMP 'audit_fuelratio_pg_surfaces.py'

$script = @'
import json
import psycopg
from psycopg.rows import dict_row

params = {
    "host": "127.0.0.1",
    "port": 5432,
    "dbname": "bf_trend",
    "user": "postgres",
    "connect_timeout": 5,
}

PROPOSED = [
    "bf_imes.mes_operation_log_report_raw",
    "bf_assistant.mes_operation_log_hourly_metrics",
    "bf_assistant.mes_operation_log_heat_metrics",
    "bf_assistant.foreman_fuel_ratio_rule_versions",
    "bf_assistant.foreman_fuel_ratio_si_predictions",
]

def fetchall(conn, sql, args=()):
    return [dict(row) for row in conn.execute(sql, args).fetchall()]

with psycopg.connect(**params, row_factory=dict_row) as conn:
    conn.execute("SET TRANSACTION READ ONLY")
    out = {}
    out["server"] = dict(conn.execute("SELECT current_database() AS database, current_user AS user, version() AS version").fetchone())
    out["schemas"] = fetchall(
        conn,
        """
        SELECT schema_name
        FROM information_schema.schemata
        WHERE schema_name IN ('bf_assistant','bf_imes','bf_sensor')
        ORDER BY schema_name
        """,
    )
    out["proposed_regclass"] = fetchall(
        conn,
        "SELECT name, to_regclass(name) AS regclass FROM unnest(%s::text[]) AS t(name) ORDER BY name",
        (PROPOSED,),
    )
    out["relevant_tables"] = fetchall(
        conn,
        """
        SELECT table_schema, table_name, table_type
        FROM information_schema.tables
        WHERE table_schema IN ('bf_assistant','bf_imes','bf_sensor')
          AND (
            table_name ILIKE '%heat%'
            OR table_name ILIKE '%quality%'
            OR table_name ILIKE '%imes%'
            OR table_name ILIKE '%report%'
            OR table_name ILIKE '%coal%'
            OR table_name ILIKE '%fuel%'
            OR table_name ILIKE '%operation%'
          )
        ORDER BY table_schema, table_name
        """,
    )
    out["heat_quality_columns"] = fetchall(
        conn,
        """
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema='bf_assistant'
          AND table_name='heat_performance_quality_summary'
        ORDER BY ordinal_position
        """,
    )
    out["coal_hourly_columns"] = fetchall(
        conn,
        """
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema='bf_sensor'
          AND table_name IN ('coal_injection_hourly', 'v_coal_injection_hourly')
        ORDER BY table_name, ordinal_position
        """,
    )
    out["row_counts"] = {}
    for table in [
        "bf_assistant.heat_performance_quality_summary",
        "bf_sensor.coal_injection_hourly",
        "bf_imes.raw_rows",
    ]:
        try:
            row = conn.execute(f"SELECT count(*) AS count FROM {table}").fetchone()
            out["row_counts"][table] = int(row["count"])
        except Exception as exc:
            out["row_counts"][table] = {"error": type(exc).__name__, "message": str(exc)}
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
'@

Set-Content -LiteralPath $scriptPath -Value $script -Encoding UTF8
& $python -X utf8 $scriptPath
