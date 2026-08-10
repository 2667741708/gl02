"""Export a small, read-only ABC33 input snapshot from 220.12 PostgreSQL.

The export contains latest 30-day baselines, today's minute observations,
registry mappings and metadata. Credentials are read from the remote process
environment and are never serialized.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row


FIXED_VARIABLES = (
    "P_top", "DP_total", "DP_upper", "DP_lower", "Q_blast", "P_blast",
    "P_blast_cold", "PI", "GasUtil", "T_top_A", "T_top_B", "T_top_C",
    "T_top_D", "P_top_gas_A", "P_top_gas_B", "P_top_gas_C", "P_top_gas_D",
    "L", "L_south", "L_north", "Hopper_weight", "Hopper_weight_set",
    "T_taphole_1", "T_taphole_2", "T_taphole_mean", "T_top", "PCI_rate",
    "PCI_set", "O2_rate", "Q_O2", "T_blast", "TFT", "BlastEnergy",
    "Q_soft_water", "P_soft_water", "Q_high_pressure_water",
    "P_high_pressure_water", "P_medium_pressure_water", "ExpansionTankLevel",
    "Q_N2", "P_N2", "LineDropRate_15", "BodyColdDurationMinutes",
)


def args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--day", help="YYYY-MM-DD; defaults to database current_date")
    return parser.parse_args()


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


def serial(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def dump_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=serial), encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    options = args()
    output = Path(options.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    with psycopg.connect(dsn(), row_factory=dict_row) as conn:
        database_now = conn.execute("SELECT now() AS now, current_date AS day").fetchone()
        snapshot_day = date.fromisoformat(options.day) if options.day else database_now["day"]
        day_start = datetime.combine(snapshot_day, time.min)
        day_end = datetime.combine(snapshot_day, time.max)
        registry = conn.execute(
            """SELECT variable_name,tag_long_name,is_enabled,is_derived
               FROM bf_sensor.sensor_registry
               WHERE variable_name=ANY(%s)
                  OR variable_name ~ '^P_static_(lower|middle|upper)_[A-F]$'
                  OR variable_name ~ '^T_body_L([7-9]|1[0-6])_[A-H]$'
               ORDER BY variable_name,tag_long_name""",
            (list(FIXED_VARIABLES),),
        ).fetchall()
        tag_names = sorted({str(row["tag_long_name"]) for row in registry if row["is_enabled"]})
        baselines = conn.execute(
            """SELECT DISTINCT ON(variable_name) variable_name,baseline_day,baseline_days,
                      baseline_window_start,baseline_window_end,median_ref,iqr_ref,p10,p25,p50,p75,p90,
                      sample_count,expected_minutes,coverage_ratio,source,updated_at
               FROM bf_sensor.daily_baselines
               WHERE baseline_days=30 AND baseline_day<=%s
                 AND (variable_name=ANY(%s)
                      OR variable_name ~ '^P_static_(lower|middle|upper)_[A-F]$'
                      OR variable_name ~ '^T_body_L([7-9]|1[0-6])_[A-H]$')
               ORDER BY variable_name,baseline_day DESC,updated_at DESC""",
            (snapshot_day, list(FIXED_VARIABLES)),
        ).fetchall()
        observations = conn.execute(
            """SELECT r.variable_name,v.tag_long_name,v.ts,v.value
               FROM bf_sensor.one_minute_values v
               JOIN bf_sensor.sensor_registry r USING(tag_long_name)
               WHERE v.ts>=%s AND v.ts<=%s AND v.tag_long_name=ANY(%s)
               ORDER BY v.ts,r.variable_name""",
            (day_start, day_end, tag_names),
        )
        realtime_path = output / "realtime_day.jsonl.gz"
        counts: dict[str, int] = {}
        latest: dict[str, dict[str, Any]] = {}
        row_count = 0
        with gzip.open(realtime_path, "wt", encoding="utf-8", newline="\n") as stream:
            for row in observations:
                item = {key: serial(value) for key, value in dict(row).items()}
                stream.write(json.dumps(item, ensure_ascii=False) + "\n")
                name = str(row["variable_name"])
                counts[name] = counts.get(name, 0) + 1
                latest[name] = item
                row_count += 1
        dump_json(output / "registry.json", [dict(row) for row in registry])
        dump_json(output / "baselines_30d.json", [dict(row) for row in baselines])
        dump_json(output / "latest_values.json", latest)
        metadata = {
            "schema_version": "abc33.input-snapshot.v1",
            "exported_at": database_now["now"],
            "snapshot_day": snapshot_day,
            "day_start": day_start,
            "day_end": day_end,
            "registry_rows": len(registry),
            "baseline_rows": len(baselines),
            "observation_rows": row_count,
            "observation_counts": counts,
            "variables_with_observations": len(counts),
            "credentials_included": False,
        }
        dump_json(output / "metadata.json", metadata)
    manifest = {}
    for path in sorted(output.iterdir()):
        if path.name != "manifest.sha256.json" and path.is_file():
            manifest[path.name] = {"bytes": path.stat().st_size, "sha256": sha256(path)}
    dump_json(output / "manifest.sha256.json", manifest)
    print(json.dumps({"ok": True, **metadata, "output_dir": str(output)}, ensure_ascii=False, default=serial))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
