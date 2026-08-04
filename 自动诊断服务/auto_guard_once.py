from __future__ import annotations

import argparse
import json
import os
import sys
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from backfill_missing import create_tasks_from_quality
from baseline_maintainer import build_day
from data_quality_monitor import DataQualityMonitor
from diagnosis_queue_service import build_queue
from diagnosis_scheduler import AutoDiagnosisScheduler, floor_to_interval
from llm_short_window_summarizer import summarize
from pipeline_doctor import inspect as inspect_pipeline
from store import DiagnosisStore
from zero_value_auditor import audit_recent_zeros


SERVICE_DIR = Path(__file__).resolve().parent
LOG_DIR = SERVICE_DIR / "logs"
LOCK_PATH = LOG_DIR / "auto_guard_once.lock"
STATE_PATH = LOG_DIR / "auto_guard_state.json"


def json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def timestamp_text(value: datetime) -> str:
    return value.replace(second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one idempotent V3 automatic diagnosis guard cycle.")
    parser.add_argument("--config", default="", help="Optional auto_diagnosis_service config path.")
    parser.add_argument("--since-hours", type=float, default=24.0, help="Backfill missing diagnoses within this lookback.")
    parser.add_argument("--max-diagnosis-points", type=int, default=288, help="Safety limit per run; 288 = 24h at 5min.")
    parser.add_argument("--quality-write", action="store_true", default=True, help="Write data quality status rows.")
    parser.add_argument("--no-quality-write", dest="quality_write", action="store_false")
    parser.add_argument("--with-llm", action="store_true", help="Also summarize the latest diagnosis queue via Ollama.")
    parser.add_argument("--export-docx", action="store_true", help="When --with-llm is set, export Word report too.")
    parser.add_argument("--doctor", action="store_true", help="Run a readonly full-pipeline inspection at the end.")
    parser.add_argument("--dry-run", action="store_true", help="Calculate without writing database changes.")
    parser.add_argument("--lock-stale-minutes", type=float, default=30.0)
    parser.add_argument("--sync-wait-timeout-seconds", type=float, default=None)
    parser.add_argument("--sync-wait-poll-seconds", type=float, default=None)
    parser.add_argument("--skip-zero-audit", action="store_true", help="Skip pSpace verification for zero sensor values.")
    parser.add_argument("--zero-audit-minutes", type=int, default=180, help="Recent minutes to audit zero values before diagnosis.")
    parser.add_argument("--zero-audit-limit", type=int, default=1000, help="Maximum zero values to verify in one guard cycle.")
    return parser.parse_args()


@contextmanager
def single_instance(stale_minutes: float):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    now = time.time()
    if LOCK_PATH.exists():
        age_minutes = (now - LOCK_PATH.stat().st_mtime) / 60.0
        if age_minutes <= stale_minutes:
            yield False
            return
        try:
            LOCK_PATH.unlink()
        except OSError:
            yield False
            return
    fd = os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(fd, f"pid={os.getpid()} started={datetime.now().isoformat()}".encode("utf-8"))
        yield True
    finally:
        os.close(fd)
        try:
            LOCK_PATH.unlink()
        except OSError:
            pass


def days_between(start: datetime, end: datetime) -> list[date]:
    first = start.date()
    last = end.date()
    days: list[date] = []
    cursor = first
    while cursor <= last:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


def ensure_baselines(store: DiagnosisStore, days: list[date], baseline_days: int, config_path: str | None, dry_run: bool) -> list[dict[str, Any]]:
    results = []
    for day in days:
        existing = store.baseline_meta_for_day(day, baseline_days=baseline_days)
        if existing:
            results.append({"day": day.isoformat(), "status": "exists", "variables": len(existing)})
            continue
        result = build_day(day, baseline_days=baseline_days, config_path=config_path, write=not dry_run)
        results.append(
            {
                "day": day.isoformat(),
                "status": "built" if not dry_run else "dry_run",
                "variables": result.get("variables", 0),
                "written": result.get("written", 0),
            }
        )
    return results


def run_cycle(args: argparse.Namespace) -> dict[str, Any]:
    config_path = args.config or None
    scheduler = AutoDiagnosisScheduler(config_path)
    if args.sync_wait_timeout_seconds is not None:
        scheduler.diag_cfg["sync_wait_timeout_seconds"] = args.sync_wait_timeout_seconds
    if args.sync_wait_poll_seconds is not None:
        scheduler.diag_cfg["sync_wait_poll_seconds"] = args.sync_wait_poll_seconds
    store = scheduler.store
    if not args.dry_run:
        store.ensure_schema()

    interval = int(scheduler.diag_cfg["diagnosis_interval_minutes"])
    baseline_days = int(scheduler.diag_cfg["baseline_days"])
    target, sync_wait = scheduler.latest_complete_target(wait=True)
    latest_data_ts = sync_wait.get("latest_data_ts")
    if target is None:
        return {
            "ok": False,
            "started_at": datetime.now(),
            "error": "no_source_data",
            "sync_wait": sync_wait,
            "dry_run": args.dry_run,
        }
    start = floor_to_interval(target - timedelta(hours=float(args.since_hours)), interval)

    run_id = None
    if not args.dry_run:
        run_id = store.start_run("auto_guard_once", start, target)

    report: dict[str, Any] = {
        "ok": True,
        "started_at": datetime.now(),
        "target": target,
        "window_start": start,
        "interval_minutes": interval,
        "latest_data_ts": latest_data_ts,
        "sync_wait": sync_wait,
        "dry_run": args.dry_run,
        "actions": [],
    }
    try:
        if not args.skip_zero_audit and scheduler.config.get("zero_value_policy", {}).get("enabled", True):
            try:
                report["zero_value_audit"] = audit_recent_zeros(
                    config_path,
                    minutes=args.zero_audit_minutes,
                    limit=args.zero_audit_limit,
                    dry_run=args.dry_run,
                )
            except Exception as exc:  # noqa: BLE001
                report["zero_value_audit"] = {"ok": False, "error": str(exc)}

        quality = DataQualityMonitor(config_path).check_all(write=args.quality_write and not args.dry_run)
        report["quality"] = quality
        tasks = create_tasks_from_quality(config_path, write=not args.dry_run)
        report["backfill_tasks_created"] = len(tasks)

        baseline_days_touched = days_between(start, target)
        report["baselines"] = ensure_baselines(store, baseline_days_touched, baseline_days, config_path, args.dry_run)

        missing, work_stats = scheduler.find_diagnosis_work_points(
            start,
            target,
            include_invalid=bool(scheduler.diag_cfg.get("repair_invalid_snapshots", True)),
        )
        if args.max_diagnosis_points > 0 and len(missing) > args.max_diagnosis_points:
            missing = missing[-args.max_diagnosis_points :]
            report["missing_truncated_to"] = args.max_diagnosis_points
        report["missing_diagnosis_count"] = len(missing)
        report["diagnosis_work_stats"] = work_stats
        report["diagnosis_backfill_range"] = [timestamp_text(missing[0]), timestamp_text(missing[-1])] if missing else []
        deleted_invalid = 0
        if missing and not args.dry_run:
            deleted_invalid = store.delete_invalid_diagnosis_snapshots(
                missing,
                baseline_days=baseline_days,
                window_minutes=int(scheduler.diag_cfg["window_minutes"]),
                min_coverage_ratio=float(scheduler.diag_cfg.get("min_window_coverage_ratio", 0.75)),
            )
        report["invalid_snapshots_deleted"] = deleted_invalid

        written = 0
        skipped = 0
        last_diagnosis = None
        for ts in missing:
            last_diagnosis = scheduler.diagnose_point(ts, dry_run=args.dry_run)
            if last_diagnosis.get("skipped"):
                skipped += 1
            else:
                written += 0 if args.dry_run else 1
        report["diagnoses_written"] = written
        report["diagnoses_skipped"] = skipped
        report["last_diagnosis"] = last_diagnosis
        future_deleted = 0
        if not args.dry_run:
            future_deleted = store.delete_diagnosis_snapshots_after(target)
        report["future_snapshots_deleted"] = future_deleted

        queue = build_queue(
            config_path,
            queue_end_ts=target,
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

        if args.with_llm:
            report["summary"] = summarize(
                config_path,
                queue_id=queue.get("queue_id"),
                latest=False,
                write=not args.dry_run,
                dry_run=args.dry_run,
                export_word=args.export_docx,
            )

        if args.doctor:
            report["inspection"] = inspect_pipeline(config_path, since_hours=min(args.since_hours, 24.0))

        report["finished_at"] = datetime.now()
        if run_id is not None:
            store.finish_run(run_id, "ok", rows_written=written, details=report)
        return report
    except Exception as exc:
        report["ok"] = False
        report["error"] = str(exc)
        report["finished_at"] = datetime.now()
        if run_id is not None:
            store.finish_run(run_id, "error", rows_written=int(report.get("diagnoses_written", 0)), message=str(exc), details=report)
        return report


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    args = parse_args()
    with single_instance(args.lock_stale_minutes) as acquired:
        if not acquired:
            report = {"ok": True, "skipped": True, "reason": "auto_guard_once lock is active", "at": datetime.now()}
        else:
            report = run_cycle(args)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"auto_guard_{datetime.now().strftime('%Y%m%d')}.jsonl"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(report, ensure_ascii=False, default=json_default) + "\n")
    STATE_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=json_default))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
