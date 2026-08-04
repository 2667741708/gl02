from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta

from backfill_missing import create_tasks_from_quality
from data_quality_monitor import DataQualityMonitor
from pg_pspace_reconcile import reconcile
from store import DiagnosisStore


DESCRIPTION = "Watch pSpace -> local PostgreSQL synchronization and create repair work when local data is missing."
EPILOG = """
Examples:
  python 自动诊断服务/pspace_sync_watchdog.py --check --points 115 --minutes 60
  python 自动诊断服务/pspace_sync_watchdog.py --reconcile --start "2026-05-10 00:00" --end "2026-05-10 06:00" --dry-run
  python 自动诊断服务/pspace_sync_watchdog.py --backfill-missing --start "2026-05-10 00:00" --end "2026-05-10 06:00"
"""


def check(config_path: str | None, points: int, minutes: int, write: bool = False) -> dict:
    store = DiagnosisStore(config_path)
    monitor = DataQualityMonitor(config_path)
    counts = store.enabled_point_count()
    quality = monitor.check_window(minutes, f"recent_{minutes}min", write=write)
    ok = counts["physical"] >= points and quality["status"] in {"ok", "warn"}
    return {"ok": ok, "expected_points": points, "registry": counts, "quality": quality}


def main() -> int:
    parser = argparse.ArgumentParser(description=DESCRIPTION, epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="Check recent local database freshness and 115-point coverage.")
    parser.add_argument("--reconcile", action="store_true", help="Compare local PostgreSQL against pSpace historical aggregation.")
    parser.add_argument("--backfill-missing", action="store_true", help="Create and execute missing-data backfill tasks.")
    parser.add_argument("--config", default="", help="Optional config.yaml path.")
    parser.add_argument("--points", type=int, default=115, help="Expected enabled point count.")
    parser.add_argument("--minutes", type=int, default=60, help="Recent window length for freshness checks.")
    parser.add_argument("--start", default="", help="Historical start time, for example 2026-05-10 00:00.")
    parser.add_argument("--end", default="", help="Historical end time, for example 2026-05-10 06:00.")
    parser.add_argument("--write", action="store_true", help="Write quality/backfill task records.")
    parser.add_argument("--dry-run", action="store_true", help="Report planned actions without writing or fetching.")
    args = parser.parse_args()
    config_path = args.config or None
    out: dict = {"ok": True}
    if args.check or not (args.reconcile or args.backfill_missing):
        out["check"] = check(config_path, args.points, args.minutes, write=args.write and not args.dry_run)
    if args.reconcile:
        out["reconcile"] = reconcile(config_path, dry_run=True)
    if args.backfill_missing:
        tasks = create_tasks_from_quality(config_path, write=args.write and not args.dry_run)
        out["backfill_tasks"] = {"count": len(tasks), "tasks": tasks}
    print(json.dumps(out, ensure_ascii=False, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
