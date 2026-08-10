#!/usr/bin/env python3
"""Add the pressure quartile columns without fabricating any baseline rows."""

from __future__ import annotations

import argparse
import json
import os


def env_value(name: str, default: str = "") -> str:
    value = os.getenv(name, "")
    if value:
        return value
    if os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
            ) as key:
                value, _ = winreg.QueryValueEx(key, name)
                return str(value or default)
        except OSError:
            pass
    return default


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=env_value("GL02_PGHOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(env_value("GL02_PGPORT", "5432")))
    parser.add_argument("--database", default=env_value("GL02_PGDATABASE", "bf_trend"))
    parser.add_argument("--user", default=env_value("GL02_PGADMIN_USER", "postgres"))
    parser.add_argument("--password-env", default="GL02_PGADMIN_PASSWORD")
    parser.add_argument("--require-variable", default="", help="Require a latest baseline row with p25/p75 for this variable.")
    args = parser.parse_args()
    password = env_value(args.password_env)
    if not password:
        raise SystemExit(f"database password environment variable is missing: {args.password_env}")

    import psycopg
    from psycopg.rows import dict_row

    ddl = """
    ALTER TABLE bf_sensor.daily_baselines
      ADD COLUMN IF NOT EXISTS p25 DOUBLE PRECISION,
      ADD COLUMN IF NOT EXISTS p75 DOUBLE PRECISION;
    COMMENT ON COLUMN bf_sensor.daily_baselines.p25 IS 'Exact 30-day historical 25th percentile (Q1).';
    COMMENT ON COLUMN bf_sensor.daily_baselines.p75 IS 'Exact 30-day historical 75th percentile (Q3).';
    """
    with psycopg.connect(
        host=args.host,
        port=args.port,
        dbname=args.database,
        user=args.user,
        password=password,
        connect_timeout=15,
        row_factory=dict_row,
    ) as conn:
        with conn.transaction():
            conn.execute(ddl)
        row = conn.execute(
            """
            SELECT
                EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema='bf_sensor' AND table_name='daily_baselines' AND column_name='p25'
                ) AS p25_installed,
                EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema='bf_sensor' AND table_name='daily_baselines' AND column_name='p75'
                ) AS p75_installed
            """
        ).fetchone()
        latest = None
        if args.require_variable:
            latest = conn.execute(
                """
                SELECT baseline_day::text AS baseline_day, variable_name,
                       p25, p75, sample_count, coverage_ratio,
                       baseline_window_start::text AS baseline_window_start,
                       baseline_window_end::text AS baseline_window_end
                FROM bf_sensor.daily_baselines
                WHERE variable_name = %s
                ORDER BY baseline_day DESC
                LIMIT 1
                """,
                (args.require_variable,),
            ).fetchone()
    result = {
        "ok": bool(row and row["p25_installed"] and row["p75_installed"]),
        "database": args.database,
        "server": f"{args.host}:{args.port}",
        "p25_installed": bool(row and row["p25_installed"]),
        "p75_installed": bool(row and row["p75_installed"]),
        "rows_fabricated": False,
        "latest_baseline": dict(latest) if latest else None,
    }
    if args.require_variable and (
        not latest or latest["p25"] is None or latest["p75"] is None
    ):
        result["ok"] = False
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
