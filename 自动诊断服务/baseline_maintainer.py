from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from store import DiagnosisStore


DESCRIPTION = "Maintain daily 30-day historical baselines in PostgreSQL for later diagnosis queries."
EPILOG = """
Examples:
  python 自动诊断服务/baseline_maintainer.py --build-day 2026-05-10 --write
  python 自动诊断服务/baseline_maintainer.py --backfill-days 30 --end-day 2026-05-10 --dry-run
  python 自动诊断服务/baseline_maintainer.py --query --day 2026-05-10 --variable PI
"""


def parse_day(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(value.replace("T", " ")).date()


def baseline_window(day: date, baseline_days: int) -> tuple[datetime, datetime]:
    end = datetime.combine(day, datetime.min.time())
    start = end - timedelta(days=baseline_days)
    return start, end - timedelta(minutes=1)


def build_day(day: date, baseline_days: int = 30, config_path: str | Path | None = None, write: bool = False) -> dict[str, Any]:
    store = DiagnosisStore(config_path)
    start, end = baseline_window(day, baseline_days)
    frame = store.fetch_wide_frame(start, end)
    expected_minutes = int((end - start).total_seconds() // 60) + 1
    rows: list[dict[str, Any]] = []
    if not frame.empty:
        for col in frame.columns:
            if col == "timestamp":
                continue
            series = pd.to_numeric(frame[col], errors="coerce").dropna()
            if len(series) < 10:
                continue
            q1 = float(series.quantile(0.25))
            q3 = float(series.quantile(0.75))
            rows.append(
                {
                    "baseline_window_start": start,
                    "baseline_window_end": end,
                    "baseline_days": baseline_days,
                    "variable_name": col,
                    "median_ref": round(float(series.median()), 6),
                    "iqr_ref": round(max(q3 - q1, 1e-6), 6),
                    "p10": round(float(series.quantile(0.10)), 6),
                    "p50": round(float(series.quantile(0.50)), 6),
                    "p90": round(float(series.quantile(0.90)), 6),
                    "sample_count": int(len(series)),
                    "expected_minutes": expected_minutes,
                    "coverage_ratio": round(float(len(series) / expected_minutes), 6) if expected_minutes else 0,
                    "source": {"type": "local_pg", "table": "bf_sensor.one_minute_values"},
                }
            )
    written = 0
    if write:
        store.ensure_schema()
        written = store.upsert_daily_baselines(day, rows)
    return {
        "ok": True,
        "baseline_day": day.isoformat(),
        "baseline_window_start": start,
        "baseline_window_end": end,
        "baseline_days": baseline_days,
        "variables": len(rows),
        "written": written,
        "rows": rows,
    }


def backfill(end_day: date, days: int, baseline_days: int, config_path: str | Path | None, write: bool) -> list[dict[str, Any]]:
    outputs = []
    first = end_day - timedelta(days=max(days - 1, 0))
    cursor = first
    while cursor <= end_day:
        outputs.append(build_day(cursor, baseline_days=baseline_days, config_path=config_path, write=write))
        cursor += timedelta(days=1)
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=DESCRIPTION, epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--build-day", default="", help="Build and optionally write one day's 30-day baseline.")
    parser.add_argument("--backfill-days", type=int, default=0, help="Build baselines for N days ending at --end-day.")
    parser.add_argument("--end-day", default="", help="Backfill end day, for example 2026-05-10.")
    parser.add_argument("--query", action="store_true", help="Query persisted baseline rows.")
    parser.add_argument("--day", default="", help="Baseline day to query.")
    parser.add_argument("--variable", default="", help="Optional variable name to query.")
    parser.add_argument("--baseline-days", type=int, default=30, help="Lookback days used to build baselines.")
    parser.add_argument("--config", default="", help="Optional config.yaml path.")
    parser.add_argument("--write", action="store_true", help="Write baseline records to PostgreSQL.")
    parser.add_argument("--dry-run", action="store_true", help="Calculate/report without writing.")
    args = parser.parse_args()
    config_path = args.config or None
    store = DiagnosisStore(config_path)
    if args.query:
        if not args.day:
            raise SystemExit("--query requires --day")
        rows = store.query_daily_baselines(args.day, variable=args.variable, baseline_days=args.baseline_days)
        print(json.dumps({"ok": True, "count": len(rows), "rows": rows}, ensure_ascii=False, default=str, indent=2))
        return 0
    if args.backfill_days:
        end_day = parse_day(args.end_day) if args.end_day else datetime.now().date()
        rows = backfill(end_day, args.backfill_days, args.baseline_days, config_path, write=args.write and not args.dry_run)
        print(json.dumps({"ok": True, "count": len(rows), "days": rows}, ensure_ascii=False, default=str, indent=2))
        return 0
    day = parse_day(args.build_day) if args.build_day else datetime.now().date()
    result = build_day(day, baseline_days=args.baseline_days, config_path=config_path, write=args.write and not args.dry_run)
    print(json.dumps(result, ensure_ascii=False, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
