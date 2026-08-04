from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta

from baseline_maintainer import build_day
from data_quality_monitor import DataQualityMonitor
from diagnosis_queue_service import build_queue
from diagnosis_scheduler import AutoDiagnosisScheduler, floor_to_interval
from llm_short_window_summarizer import summarize
from pspace_sync_watchdog import check as sync_check
from store import DiagnosisStore


DESCRIPTION = "Inspect and repair the full automatic furnace diagnosis pipeline."
EPILOG = """
Examples:
  python 自动诊断服务/pipeline_doctor.py --check-all
  python 自动诊断服务/pipeline_doctor.py --check-all --repair --dry-run
  python 自动诊断服务/pipeline_doctor.py --since-hours 24 --repair
  python 自动诊断服务/pipeline_doctor.py --repair --start "2026-05-10 18:55:00" --end "2026-05-12 15:10:00" --skip-inspection --skip-summary
"""


def inspect(config_path: str | None, since_hours: float = 24.0) -> dict:
    store = DiagnosisStore(config_path)
    store.ensure_schema()
    now = datetime.now().replace(second=0, microsecond=0)
    start = now - timedelta(hours=since_hours)
    step = 5
    latest_data = store.latest_data_ts()
    scheduler = AutoDiagnosisScheduler(config_path)
    target, sync_wait = scheduler.latest_complete_target(wait=False)
    latest_baseline = store.latest_baseline_day()
    latest_diag = store.latest_diagnosis_ts()
    latest_queue = store.latest_diagnosis_queue()
    summaries = store.list_short_window_summaries(limit=1)
    end = target or floor_to_interval(now, step)
    missing_diag, work_stats = scheduler.find_diagnosis_work_points(
        floor_to_interval(start, step),
        end,
        include_invalid=bool(scheduler.diag_cfg.get("repair_invalid_snapshots", True)),
    )
    quality = DataQualityMonitor(config_path).check_all(write=False)
    return {
        "checked_at": now,
        "latest_data_ts": latest_data,
        "sync_wait": sync_wait,
        "latest_baseline_day": latest_baseline,
        "latest_diagnosis_ts": latest_diag,
        "latest_queue": latest_queue,
        "latest_summary": summaries[0] if summaries else None,
        "missing_diagnosis_count": len(missing_diag),
        "missing_diagnosis_points": missing_diag[:50],
        "diagnosis_work_stats": work_stats,
        "quality": quality,
        "sync": sync_check(config_path, 115, 60, write=False),
    }


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("T", " ")).replace(second=0, microsecond=0)


def iter_days(start: datetime, end: datetime):
    day = start.date()
    final = end.date()
    while day <= final:
        yield day
        day += timedelta(days=1)


def repair(
    config_path: str | None,
    since_hours: float,
    dry_run: bool,
    *,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    skip_summary: bool = False,
) -> dict:
    store = DiagnosisStore(config_path)
    now = datetime.now().replace(second=0, microsecond=0)
    actions = []
    scheduler = AutoDiagnosisScheduler(config_path)
    interval = int(scheduler.diag_cfg["diagnosis_interval_minutes"])
    requested_end = end_at or now
    start = floor_to_interval(start_at or (requested_end - timedelta(hours=since_hours)), interval)
    target, sync_wait = scheduler.latest_complete_target(requested_end, wait=False)
    end = target or floor_to_interval(now, int(scheduler.diag_cfg["diagnosis_interval_minutes"]))
    baseline_days = list(iter_days(start, end))
    actions.append({"action": "build_baselines", "days": [day.isoformat() for day in baseline_days], "dry_run": dry_run})
    if not dry_run:
        for day in baseline_days:
            build_day(day, config_path=config_path, write=True)
    missing, work_stats = scheduler.find_diagnosis_work_points(
        start,
        end,
        include_invalid=bool(scheduler.diag_cfg.get("repair_invalid_snapshots", True)),
    )
    deleted_invalid = 0
    if not dry_run:
        deleted_invalid = store.delete_invalid_diagnosis_snapshots(
            missing,
            baseline_days=int(scheduler.diag_cfg["baseline_days"]),
            window_minutes=int(scheduler.diag_cfg["window_minutes"]),
            min_coverage_ratio=float(scheduler.diag_cfg.get("min_window_coverage_ratio", 0.75)),
        )
    actions.append(
        {
            "action": "backfill_missing_or_invalid_diagnoses",
            "start": start,
            "end": end,
            "count": len(missing),
            "work_stats": work_stats,
            "deleted_invalid": deleted_invalid,
            "sync_wait": sync_wait,
            "dry_run": dry_run,
        }
    )
    if not dry_run:
        for ts in missing:
            scheduler.diagnose_point(ts, dry_run=False)
    actions.append({"action": "build_current_queue", "dry_run": dry_run})
    queue = None if dry_run else build_queue(config_path, write=True)
    actions.append({"action": "summarize_latest_queue", "dry_run": dry_run, "skipped": skip_summary})
    if not dry_run and not skip_summary:
        summarize(config_path, latest=True, write=True, export_word=True)
    return {"actions": actions, "queue": queue}


def main() -> int:
    parser = argparse.ArgumentParser(description=DESCRIPTION, epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check-all", action="store_true", help="Run all pipeline checks.")
    parser.add_argument("--since-hours", type=float, default=24.0, help="Lookback window for health checks.")
    parser.add_argument("--repair", action="store_true", help="Repair missing baselines, diagnoses, queues, and summaries.")
    parser.add_argument("--start", default="", help="Optional repair start timestamp, e.g. 2026-05-10 18:55:00.")
    parser.add_argument("--end", default="", help="Optional repair end timestamp, e.g. 2026-05-12 15:10:00.")
    parser.add_argument("--skip-inspection", action="store_true", help="Skip pre-repair full inspection output.")
    parser.add_argument("--skip-summary", action="store_true", help="Skip LLM summary generation after repair.")
    parser.add_argument("--config", default="", help="Optional config.yaml path.")
    parser.add_argument("--dry-run", action="store_true", help="Show repair plan without writing.")
    args = parser.parse_args()
    config_path = args.config or None
    store = DiagnosisStore(config_path)
    run_id = None
    repair_start = parse_time(args.start) if args.start else None
    repair_end = parse_time(args.end) if args.end else None
    if args.repair and not args.dry_run:
        store.ensure_schema()
        run_id = store.start_run(
            "pipeline_doctor",
            repair_start or (datetime.now() - timedelta(hours=args.since_hours)),
            repair_end or datetime.now(),
        )
    try:
        result = {"ok": True}
        if not args.skip_inspection:
            result["inspection"] = inspect(config_path, args.since_hours)
        if args.repair:
            result["repair"] = repair(
                config_path,
                args.since_hours,
                args.dry_run,
                start_at=repair_start,
                end_at=repair_end,
                skip_summary=args.skip_summary,
            )
        if run_id is not None:
            store.finish_run(run_id, "ok", details=result)
        print(json.dumps(result, ensure_ascii=False, default=str, indent=2))
        return 0
    except Exception as exc:
        if run_id is not None:
            store.finish_run(run_id, "error", message=str(exc))
        raise


if __name__ == "__main__":
    raise SystemExit(main())
