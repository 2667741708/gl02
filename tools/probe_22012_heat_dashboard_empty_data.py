from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any


def json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    return str(value)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only audit of heat, sensor, diagnosis and lab alignment."
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=24)
    args = parser.parse_args()

    root = args.root.resolve()
    dashboard_dir = root / "db_dashboard"
    if not dashboard_dir.exists():
        raise SystemExit(f"missing dashboard directory: {dashboard_dir}")
    sys.path.insert(0, str(dashboard_dir))

    import heat_service  # type: ignore  # noqa: PLC0415
    import server  # type: ignore  # noqa: PLC0415

    payload = heat_service.list_heats(limit=max(1, min(args.limit, 200)))
    now_local = datetime.now()
    with server.connect() as conn:
        sensor_bounds = conn.execute(
            """
            SELECT min(ts) AS min_ts, max(ts) AS max_ts,
                   count(*) AS row_count,
                   count(DISTINCT tag_long_name) AS tag_count
            FROM bf_sensor.one_minute_values
            """
        ).fetchone()
        diagnosis_bounds = conn.execute(
            """
            SELECT min(diagnosis_ts) AS min_ts, max(diagnosis_ts) AS max_ts,
                   count(DISTINCT diagnosis_ts) AS timestamp_count
            FROM bf_sensor.diagnosis_snapshots
            """
        ).fetchone()
        pg_clock = conn.execute(
            "SELECT now() AS now_ts, current_setting('TimeZone') AS timezone"
        ).fetchone()

        heat_audit: list[dict[str, Any]] = []
        for heat in payload["heats"]:
            start, end, _ = heat_service.resolve_sensor_window(
                heat, "pre_tap", 120
            )
            sensor = conn.execute(
                """
                SELECT count(*) AS rows,
                       count(DISTINCT tag_long_name) AS tags,
                       min(ts) AS min_ts,
                       max(ts) AS max_ts
                FROM bf_sensor.one_minute_values
                WHERE ts >= %s AND ts < %s
                """,
                (start, end),
            ).fetchone()
            diagnosis = conn.execute(
                """
                SELECT count(DISTINCT diagnosis_ts) AS rows,
                       min(diagnosis_ts) AS min_ts,
                       max(diagnosis_ts) AS max_ts
                FROM bf_sensor.diagnosis_snapshots
                WHERE diagnosis_ts >= %s AND diagnosis_ts < %s
                """,
                (start, end),
            ).fetchone()
            open_ts = heat.get("open_ts")
            heat_audit.append(
                {
                    "meltno": heat.get("meltno"),
                    "open_ts": open_ts,
                    "close_ts": heat.get("close_ts"),
                    "future_open_minutes": (
                        round((open_ts - now_local).total_seconds() / 60, 1)
                        if open_ts and open_ts > now_local
                        else 0
                    ),
                    "pre_tap_start": start,
                    "pre_tap_end": end,
                    "sensor_rows": int(sensor["rows"] or 0),
                    "sensor_tags": int(sensor["tags"] or 0),
                    "sensor_min_ts": sensor["min_ts"],
                    "sensor_max_ts": sensor["max_ts"],
                    "diagnosis_rows": int(diagnosis["rows"] or 0),
                    "diagnosis_min_ts": diagnosis["min_ts"],
                    "diagnosis_max_ts": diagnosis["max_ts"],
                    "output_count": heat.get("output_count"),
                    "hot_metal_sample_count": heat.get(
                        "hot_metal_sample_count"
                    ),
                    "slag_sample_count": heat.get("slag_sample_count"),
                    "alignment_status": heat.get("alignment_status"),
                }
            )

    result = {
        "checked_at": now_local,
        "pg_clock": dict(pg_clock),
        "sensor_bounds": dict(sensor_bounds),
        "diagnosis_bounds": dict(diagnosis_bounds),
        "heat_summary": payload["summary"],
        "heats": heat_audit,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
