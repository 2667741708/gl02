from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from baseline_maintainer import build_day
from diagnosis_queue_service import build_queue
from diagnosis_scheduler import AutoDiagnosisScheduler, floor_to_interval
from store import DiagnosisStore


SERVICE_DIR = Path(__file__).resolve().parent
LOG_DIR = SERVICE_DIR / "logs"


def json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def parse_day(value: str) -> date:
    return datetime.fromisoformat(value.replace("T", " ")).date()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill daily baselines and 5-minute diagnoses for a recent production window.")
    parser.add_argument("--config", default="", help="Optional auto_diagnosis_service config path.")
    parser.add_argument("--days", type=int, default=60, help="Number of diagnosis days to backfill.")
    parser.add_argument("--baseline-days", type=int, default=30, help="Rolling baseline lookback days.")
    parser.add_argument("--end-day", default="", help="End day, defaults to today.")
    parser.add_argument("--max-diagnosis-points", type=int, default=0, help="Optional safety limit; 0 means no limit.")
    parser.add_argument("--force-baseline", action="store_true", help="Recompute existing baseline days instead of skipping them.")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def each_day(first: date, last: date):
    cursor = first
    while cursor <= last:
        yield cursor
        cursor += timedelta(days=1)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    args = parse_args()
    config_path = args.config or None
    end_day = parse_day(args.end_day) if args.end_day else datetime.now().date()
    start_day = end_day - timedelta(days=max(args.days - 1, 0))
    start_ts = datetime.combine(start_day, datetime.min.time())
    scheduler_for_target = AutoDiagnosisScheduler(config_path)
    target, sync_wait = scheduler_for_target.latest_complete_target(wait=False)
    end_ts = target or floor_to_interval(datetime.now(), 5)

    store = DiagnosisStore(config_path)
    if not args.dry_run:
        store.ensure_schema()
    run_id = None
    if not args.dry_run:
        run_id = store.start_run("initial_backfill_60d", start_ts, end_ts)

    report: dict[str, Any] = {
        "ok": True,
        "started_at": datetime.now(),
        "start_day": start_day,
        "end_day": end_day,
        "diagnosis_start": start_ts,
        "diagnosis_end": end_ts,
        "sync_wait": sync_wait,
        "days": args.days,
        "dry_run": args.dry_run,
        "baselines": [],
        "diagnoses_written": 0,
    }
    try:
        for day in each_day(start_day, end_day):
            existing = store.baseline_meta_for_day(day, baseline_days=args.baseline_days)
            if existing and not args.force_baseline:
                report["baselines"].append(
                    {
                        "day": day.isoformat(),
                        "status": "exists",
                        "variables": len(existing),
                        "written": 0,
                    }
                )
                continue
            result = build_day(day, baseline_days=args.baseline_days, config_path=config_path, write=not args.dry_run)
            report["baselines"].append(
                {
                    "day": day.isoformat(),
                    "status": "built" if not args.dry_run else "dry_run",
                    "variables": result.get("variables", 0),
                    "written": result.get("written", 0),
                }
            )

        scheduler = scheduler_for_target
        interval = int(scheduler.diag_cfg["diagnosis_interval_minutes"])
        missing, work_stats = scheduler.find_diagnosis_work_points(
            floor_to_interval(start_ts, interval),
            floor_to_interval(end_ts, interval),
            include_invalid=bool(scheduler.diag_cfg.get("repair_invalid_snapshots", True)),
        )
        if args.max_diagnosis_points > 0 and len(missing) > args.max_diagnosis_points:
            missing = missing[-args.max_diagnosis_points :]
            report["missing_truncated_to"] = args.max_diagnosis_points
        report["missing_diagnosis_count"] = len(missing)
        report["diagnosis_work_stats"] = work_stats
        report["diagnosis_range"] = [missing[0], missing[-1]] if missing else []
        deleted_invalid = 0
        if missing and not args.dry_run:
            deleted_invalid = store.delete_invalid_diagnosis_snapshots(
                missing,
                baseline_days=int(scheduler.diag_cfg["baseline_days"]),
                window_minutes=int(scheduler.diag_cfg["window_minutes"]),
                min_coverage_ratio=float(scheduler.diag_cfg.get("min_window_coverage_ratio", 0.75)),
            )
        report["invalid_snapshots_deleted"] = deleted_invalid

        for ts in missing:
            result = scheduler.diagnose_point(ts, dry_run=args.dry_run)
            if not result.get("skipped"):
                report["diagnoses_written"] += 0 if args.dry_run else 1

        queue = build_queue(
            config_path,
            queue_end_ts=floor_to_interval(end_ts, interval),
            window_minutes=60,
            step_minutes=interval,
            queue_size=max(1, int(60 / interval)),
            write=not args.dry_run,
        )
        report["queue"] = {
            "queue_id": queue.get("queue_id"),
            "status": queue.get("status"),
            "diagnosis_count": queue.get("diagnosis_count"),
            "expected_count": queue.get("expected_count"),
        }
        report["finished_at"] = datetime.now()
        if run_id is not None:
            store.finish_run(run_id, "ok", rows_written=int(report["diagnoses_written"]), details=report)
    except Exception as exc:
        report["ok"] = False
        report["error"] = str(exc)
        report["finished_at"] = datetime.now()
        if run_id is not None:
            store.finish_run(run_id, "error", rows_written=int(report.get("diagnoses_written", 0)), message=str(exc), details=report)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"initial_backfill_60d_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    log_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=json_default))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
