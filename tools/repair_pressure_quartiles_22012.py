"""Repair only missing pressure p25/p75 values from 220.12 one-minute data."""
from __future__ import annotations

import argparse
import json
import math
import os
from datetime import date, datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row


def linear_percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("empty percentile input")
    index = (len(ordered) - 1) * fraction
    lower = int(math.floor(index))
    upper = int(math.ceil(index))
    if lower == upper:
        return float(ordered[lower])
    weight = index - lower
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * weight)


def iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Commit only p25/p75 repairs.")
    args = parser.parse_args()
    conninfo = {
        "host": os.environ.get("GL02_PGHOST", "127.0.0.1"),
        "port": int(os.environ.get("GL02_PGPORT", "5432")),
        "dbname": os.environ.get("GL02_PGDATABASE", "bf_trend"),
        "user": os.environ.get("GL02_PGUSER", "gl02_sync"),
        "password": os.environ.get("GL02_PGPASSWORD", ""),
    }
    variables = ("P_blast_cold", "P_blast")
    with psycopg.connect(**conninfo) as conn:
        conn.row_factory = dict_row
        targets = conn.execute(
            """
            SELECT id, baseline_day, baseline_window_start, baseline_window_end,
                   variable_name, p25, p75, sample_count, coverage_ratio
            FROM bf_sensor.daily_baselines
            WHERE baseline_days=30
              AND variable_name = ANY(%s)
              AND (p25 IS NULL OR p75 IS NULL)
            ORDER BY baseline_day, variable_name
            """,
            (list(variables),),
        ).fetchall()
        if not targets:
            print(json.dumps({"ok": True, "apply": args.apply, "target_rows": 0, "updated_rows": 0}, ensure_ascii=False))
            return 0
        min_start = min(row["baseline_window_start"] for row in targets)
        max_end = max(row["baseline_window_end"] for row in targets)
        zero_table = bool(conn.execute("SELECT to_regclass('bf_sensor.zero_value_audits') AS table_name").fetchone()["table_name"])
        zero_join = ""
        zero_where = ""
        if zero_table:
            zero_join = """
              LEFT JOIN bf_sensor.zero_value_audits z
                ON z.tag_long_name = v.tag_long_name
               AND z.ts = v.ts
               AND z.pspace_aggregate = v.aggregate
            """
            zero_where = "AND (v.value <> 0 OR z.verification_status = 'verified_zero')"
        else:
            zero_where = "AND v.value <> 0"
        raw = conn.execute(
            f"""
            SELECT r.variable_name, v.ts,
                   avg(v.value)::double precision AS value
            FROM bf_sensor.one_minute_values v
            JOIN bf_sensor.sensor_registry r
              ON r.tag_long_name=v.tag_long_name
             AND r.is_enabled=true AND r.is_derived=false
            {zero_join}
            WHERE r.variable_name = ANY(%s)
              AND v.ts >= %s AND v.ts <= %s
              AND v.value IS NOT NULL {zero_where}
            GROUP BY r.variable_name, v.ts
            ORDER BY r.variable_name, v.ts
            """,
            (list(variables), min_start, max_end),
        ).fetchall()
        by_variable: dict[str, list[tuple[datetime, float]]] = {name: [] for name in variables}
        for row in raw:
            by_variable[str(row["variable_name"])].append((row["ts"], float(row["value"])))
        repairs: list[dict[str, Any]] = []
        for target in targets:
            points = [
                value for ts, value in by_variable[str(target["variable_name"])]
                if target["baseline_window_start"] <= ts <= target["baseline_window_end"]
            ]
            if not points:
                raise RuntimeError(f"no source samples for baseline id {target['id']}")
            p25 = linear_percentile(points, 0.25)
            p75 = linear_percentile(points, 0.75)
            if not math.isfinite(p25) or not math.isfinite(p75) or p25 >= p75:
                raise RuntimeError(f"invalid quartiles for baseline id {target['id']}: {p25}, {p75}")
            repairs.append(
                {
                    "id": int(target["id"]),
                    "baseline_day": iso(target["baseline_day"]),
                    "variable_name": target["variable_name"],
                    "sample_count_existing": target["sample_count"],
                    "sample_count_recomputed": len(points),
                    "coverage_ratio_existing": target["coverage_ratio"],
                    "p25": round(p25, 6),
                    "p75": round(p75, 6),
                }
            )
        updated = 0
        if args.apply:
            with conn.transaction():
                for repair in repairs:
                    result = conn.execute(
                        """
                        UPDATE bf_sensor.daily_baselines
                        SET p25=COALESCE(p25, %s),
                            p75=COALESCE(p75, %s),
                            updated_at=now()
                        WHERE id=%s AND (p25 IS NULL OR p75 IS NULL)
                        """,
                        (repair["p25"], repair["p75"], repair["id"]),
                    )
                    updated += result.rowcount
        print(json.dumps({
            "ok": True,
            "apply": args.apply,
            "source_table": "bf_sensor.one_minute_values",
            "zero_value_audits_used": zero_table,
            "target_rows": len(targets),
            "raw_minute_rows": len(raw),
            "updated_rows": updated,
            "repairs": repairs,
        }, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
