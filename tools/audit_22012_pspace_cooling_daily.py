"""Read-only daily raw-history audit for GL02 cooling-system pSpace tags."""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

TAGS = {
    "Q_soft_water": r"\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0056",
    "P_soft_water": r"\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0137",
    "Q_high_pressure_water": r"\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0021",
    "P_high_pressure_water": r"\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0148",
    "P_medium_pressure_water": r"\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0147",
    "ExpansionTankLevel": r"\冀南钢铁\SIO\GL02\BT\SIO_GL02_BT_T0097",
}


def find_runtime() -> tuple[Path, Path]:
    candidates = list(Path("F:/").glob("*V3/trend_analysis/trend_backend/pspace_history.py"))
    candidates += list(Path("F:/").glob("*V4_8093_PREVIEW/*/trend_backend/pspace_history.py"))
    if not candidates:
        raise RuntimeError("pspace_history.py not found")
    module = candidates[0]
    root = module.parents[2]
    return root, module.parent


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * fraction))
    return round(ordered[index], 3)


def main() -> int:
    root, trend = find_runtime()
    sys.path.insert(0, str(trend))
    import pspace_history  # type: ignore

    config_candidates = [
        root / "ghsc" / "src" / "main" / "resources" / "application-prod.yml",
        root / "ghsc" / "src" / "main" / "resources" / "application-dev.yml",
    ]
    config_path = next((path for path in config_candidates if path.exists()), config_candidates[-1])
    connection = pspace_history.resolve_connection(
        config_path=config_path, server="10.22.181.243", port="8889"
    )
    PsObject, fields = pspace_history.load_sdk(root / "pythonSDK(1)")
    end_day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start_day = end_day - timedelta(days=30)
    output = {
        "audit_id": "Q-PSPACE-COOLING-DAILY-20260809",
        "source": f"{connection['server']}:{connection['port']}",
        "window_start": start_day.isoformat(),
        "window_end_exclusive": end_day.isoformat(),
        "read_only": True,
        "variables": {},
    }
    pspace = pspace_history.connect_pspace(PsObject, fields, connection)
    try:
        for variable, tag in TAGS.items():
            daily = []
            all_times: list[datetime] = []
            errors = []
            day = start_day
            while day < end_day:
                next_day = day + timedelta(days=1)
                try:
                    result = pspace.HisReadRaw({
                        fields.HisReadRawTagLongName: [tag],
                        fields.HisReadRawstartTime: pspace_history.format_ps_time(day),
                        fields.HisReadRawendTime: pspace_history.format_ps_time(next_day),
                        fields.HisReadRawMaxValues: 50000,
                        fields.HisReadRawBounds: 0,
                    })
                    rows = []
                    records = result.get(tag, {}) if isinstance(result, dict) else {}
                    if isinstance(records, dict):
                        for _, record in pspace_history.numeric_items(records):
                            if not isinstance(record, dict):
                                continue
                            ts = pspace_history.parse_timestamp(record.get(fields.HisReadRawTimeStamp))
                            value = pspace_history.coerce_number(record.get(fields.HisReadRawValueDict))
                            if ts is not None:
                                rows.append((ts, value))
                    rows.sort(key=lambda item: item[0])
                    times = [item[0] for item in rows]
                    all_times.extend(times)
                    gaps = [(b - a).total_seconds() for a, b in zip(times, times[1:]) if b > a]
                    minutes = {ts.replace(second=0, microsecond=0) for ts in times}
                    hours = Counter(ts.hour for ts in times)
                    daily.append({
                        "date": day.date().isoformat(),
                        "raw_rows": len(rows),
                        "numeric_rows": sum(value is not None for _, value in rows),
                        "unique_minutes": len(minutes),
                        "minute_coverage_ratio": round(len(minutes) / 1440, 6),
                        "first_ts": times[0].isoformat() if times else None,
                        "last_ts": times[-1].isoformat() if times else None,
                        "median_gap_seconds": round(statistics.median(gaps), 3) if gaps else None,
                        "p95_gap_seconds": percentile(gaps, 0.95),
                        "active_hours": sorted(hours),
                    })
                except Exception as exc:  # retain per-day evidence
                    errors.append({"date": day.date().isoformat(), "error": str(exc)})
                day = next_day
            counts = [row["raw_rows"] for row in daily]
            minute_counts = [row["unique_minutes"] for row in daily]
            cross_gaps = [(b - a).total_seconds() for a, b in zip(all_times, all_times[1:]) if b > a]
            output["variables"][variable] = {
                "tag": tag,
                "days_queried": len(daily),
                "total_raw_rows": sum(counts),
                "daily_raw_min": min(counts) if counts else None,
                "daily_raw_median": statistics.median(counts) if counts else None,
                "daily_raw_max": max(counts) if counts else None,
                "daily_unique_minutes_median": statistics.median(minute_counts) if minute_counts else None,
                "overall_median_gap_seconds": round(statistics.median(cross_gaps), 3) if cross_gaps else None,
                "overall_p95_gap_seconds": percentile(cross_gaps, 0.95),
                "zero_row_days": sum(count == 0 for count in counts),
                "errors": errors,
                "daily": daily,
            }
    finally:
        pspace_history.close_pspace(pspace)
    print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
