"""Verify that the latest ABC33 30-day baseline set is complete and usable."""
from __future__ import annotations

import argparse
import json
import os
from datetime import date
from typing import Any

import psycopg
from psycopg.rows import dict_row


FIXED = (
    "P_top", "DP_total", "DP_upper", "DP_lower", "Q_blast", "P_blast", "P_blast_cold", "PI", "GasUtil",
    "T_top_A", "T_top_B", "T_top_C", "T_top_D", "P_top_gas_A", "P_top_gas_B", "P_top_gas_C", "P_top_gas_D",
    "L", "L_south", "L_north", "Hopper_weight", "T_taphole_1", "T_taphole_2", "T_taphole_mean", "T_top",
    "PCI_rate", "O2_rate", "Q_O2", "T_blast", "TFT", "BlastEnergy", "Q_soft_water", "P_soft_water",
    "Q_high_pressure_water", "P_high_pressure_water", "P_medium_pressure_water", "ExpansionTankLevel", "Q_N2", "P_N2",
)


def dsn() -> str:
    values = {
        "host": os.getenv("GL02_PGHOST", os.getenv("PGHOST", "127.0.0.1")),
        "port": os.getenv("GL02_PGPORT", os.getenv("PGPORT", "5432")),
        "dbname": os.getenv("GL02_PGDATABASE", os.getenv("PGDATABASE", "bf_trend")),
        "user": os.getenv("GL02_PGUSER", os.getenv("PGUSER")),
        "password": os.getenv("GL02_PGPASSWORD", os.getenv("PGPASSWORD")),
    }
    if not values["user"] or not values["password"]:
        raise RuntimeError("PostgreSQL runtime credentials are unavailable")
    return " ".join(f"{key}={value}" for key, value in values.items())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", default=date.today().isoformat())
    parser.add_argument("--minimum-coverage", type=float, default=.75)
    parser.add_argument("--output", default="")
    options = parser.parse_args()
    with psycopg.connect(dsn(), row_factory=dict_row) as conn:
        family = conn.execute(
            """SELECT DISTINCT variable_name FROM bf_sensor.sensor_registry
               WHERE is_enabled AND (variable_name ~ '^P_static_(lower|middle|upper)_[A-F]$'
                  OR variable_name ~ '^T_body_L([7-9]|1[0-6])_[A-H]$') ORDER BY variable_name"""
        ).fetchall()
        required = sorted(set(FIXED) | {str(row["variable_name"]) for row in family})
        rows = conn.execute(
            """SELECT DISTINCT ON(variable_name) variable_name,baseline_day,coverage_ratio,sample_count,
                      expected_minutes,median_ref,iqr_ref,p25,p75,source,updated_at
               FROM bf_sensor.daily_baselines
               WHERE baseline_days=30 AND baseline_day<=%s AND variable_name=ANY(%s)
               ORDER BY variable_name,baseline_day DESC,updated_at DESC""",
            (options.day, required),
        ).fetchall()
    by_name = {str(row["variable_name"]): dict(row) for row in rows}
    missing = [name for name in required if name not in by_name]
    low = []
    invalid = []
    for name, row in by_name.items():
        coverage = float(row.get("coverage_ratio") or 0)
        if coverage < options.minimum_coverage:
            low.append({"variable_name": name, "coverage_ratio": coverage, "sample_count": row.get("sample_count"), "source": row.get("source")})
        # Static-pressure A-F points are consumed as a same-time physical
        # range, not individually z-standardized. A constant point may have a
        # legitimate zero IQR and must not invalidate the whole ABC33 set.
        range_only = name.startswith("P_static_")
        if row.get("median_ref") is None or row.get("iqr_ref") is None or (float(row.get("iqr_ref") or 0) <= 0 and not range_only):
            invalid.append(name)
    result: dict[str, Any] = {
        "schema_version": "abc33.baseline-coverage-audit.v1",
        "baseline_day_at_or_before": options.day,
        "minimum_coverage": options.minimum_coverage,
        "required_count": len(required),
        "available_count": len(by_name),
        "missing": missing,
        "below_coverage": sorted(low, key=lambda row: row["variable_name"]),
        "invalid_statistics": sorted(invalid),
        "ok": not missing and not low and not invalid,
    }
    encoded = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    if options.output:
        from pathlib import Path
        target = Path(options.output); target.parent.mkdir(parents=True, exist_ok=True); target.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
