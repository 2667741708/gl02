from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, time as dtime, timedelta

from backfill_missing import create_tasks_from_quality
from baseline_maintainer import build_day
from data_quality_monitor import DataQualityMonitor
from diagnosis_queue_service import build_queue
from diagnosis_scheduler import AutoDiagnosisScheduler, floor_to_interval
from llm_short_window_summarizer import summarize
from pg_pspace_reconcile import reconcile
from pipeline_doctor import inspect as inspect_pipeline, repair as repair_pipeline
from zero_value_auditor import audit_recent_zeros


def due(last: float, interval_seconds: float) -> bool:
    return last <= 0 or time.time() - last >= interval_seconds


def run_cycle(
    config_path: str | None,
    dry_run: bool = False,
    export_docx: bool = True,
    call_llm: bool = True,
    skip_zero_audit: bool = False,
) -> dict:
    scheduler = AutoDiagnosisScheduler(config_path)
    monitor = DataQualityMonitor(config_path)
    target, sync_wait = scheduler.latest_complete_target(wait=True)
    if target is None:
        return {"sync_wait": sync_wait, "skipped": True, "reason": "no_source_data"}
    zero_audit = {"skipped": True}
    env_skip = str(os.getenv("BF_SKIP_ZERO_AUDIT", "")).lower() in {"1", "true", "yes"}
    if not skip_zero_audit and not env_skip:
        try:
            zero_audit = audit_recent_zeros(config_path, minutes=180, limit=1000, dry_run=dry_run)
        except Exception as exc:  # noqa: BLE001
            zero_audit = {"ok": False, "error": str(exc)}
    quality = monitor.check_all(write=not dry_run)
    tasks = create_tasks_from_quality(config_path, write=not dry_run)
    diagnosis = scheduler.diagnose_point(target, dry_run=dry_run)
    queue = build_queue(config_path, queue_end_ts=target, write=not dry_run)
    summary = None
    if call_llm:
        summary = summarize(config_path, queue_id=queue["queue_id"], latest=False, write=not dry_run, dry_run=dry_run, export_word=export_docx)
    return {
        "sync_wait": sync_wait,
        "zero_value_audit": zero_audit,
        "quality": quality,
        "backfill_tasks": len(tasks),
        "diagnosis": diagnosis,
        "queue": queue,
        "summary": summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run V3 automatic diagnosis service.")
    parser.add_argument("--config", default="")
    parser.add_argument("--once", action="store_true", help="Run one complete automation cycle and exit.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-llm", action="store_true", help="Skip Ollama short-window summary.")
    parser.add_argument("--no-docx", action="store_true", help="Skip Word export.")
    parser.add_argument("--skip-zero-audit", action="store_true", help="Skip direct pSpace zero-value audit in this service.")
    parser.add_argument("--doctor-interval-minutes", type=int, default=30)
    parser.add_argument("--reconcile-interval-minutes", type=int, default=60)
    args = parser.parse_args()
    config_path = args.config or None

    result = run_cycle(
        config_path,
        dry_run=args.dry_run,
        export_docx=not args.no_docx,
        call_llm=not args.no_llm,
        skip_zero_audit=args.skip_zero_audit,
    )
    result["pipeline"] = inspect_pipeline(config_path, since_hours=24)
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, default=str, indent=2))
    if args.once:
        return 0

    last_doctor = 0.0
    last_reconcile = 0.0
    last_baseline_day = None
    while True:
        now = datetime.now()
        if last_baseline_day != now.date() and now.time() >= dtime(0, 10):
            build_day(now.date(), config_path=config_path, write=not args.dry_run)
            last_baseline_day = now.date()
        try:
            run_cycle(
                config_path,
                dry_run=args.dry_run,
                export_docx=not args.no_docx,
                call_llm=not args.no_llm,
                skip_zero_audit=args.skip_zero_audit,
            )
            if due(last_reconcile, args.reconcile_interval_minutes * 60):
                reconcile(config_path, dry_run=True)
                last_reconcile = time.time()
            if due(last_doctor, args.doctor_interval_minutes * 60):
                if not args.dry_run:
                    repair_pipeline(config_path, since_hours=24, dry_run=False)
                last_doctor = time.time()
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"ok": False, "error": str(exc), "at": datetime.now()}, ensure_ascii=False, default=str), flush=True)
        time.sleep(300)


if __name__ == "__main__":
    raise SystemExit(main())
