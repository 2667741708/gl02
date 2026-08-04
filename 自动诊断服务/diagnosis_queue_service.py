from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from diagnosis_scheduler import floor_to_interval
from store import DiagnosisStore


DESCRIPTION = "Maintain the rolling 12-item, 1-hour furnace diagnosis queue and stable queue IDs."
EPILOG = """
Examples:
  python 自动诊断服务/diagnosis_queue_service.py --build-current --write
  python 自动诊断服务/diagnosis_queue_service.py --build-at "2026-05-10 18:50:00" --window-minutes 60 --step-minutes 5
  python 自动诊断服务/diagnosis_queue_service.py --query --queue-id dq_20260510_185000
"""


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("T", " ")).replace(second=0, microsecond=0)


def build_queue(
    config_path: str | Path | None = None,
    queue_end_ts: datetime | None = None,
    window_minutes: int = 60,
    step_minutes: int = 5,
    queue_size: int = 12,
    write: bool = False,
) -> dict:
    store = DiagnosisStore(config_path)
    if write:
        store.ensure_schema()
    if queue_end_ts is None:
        latest_data_ts = store.latest_data_ts()
        latest_diagnosis_ts = store.latest_diagnosis_ts()
        data_target = floor_to_interval(latest_data_ts, step_minutes) if latest_data_ts else None
        if data_target and latest_diagnosis_ts:
            queue_end_ts = min(latest_diagnosis_ts, data_target)
        else:
            queue_end_ts = latest_diagnosis_ts or data_target or floor_to_interval(datetime.now(), step_minutes)
    payload = store.make_queue_payload(queue_end_ts, window_minutes=window_minutes, step_minutes=step_minutes, queue_size=queue_size)
    if write:
        return store.upsert_diagnosis_queue(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=DESCRIPTION, epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--build-current", action="store_true", help="Build queue ending at the latest available diagnosis.")
    parser.add_argument("--build-at", default="", help="Build queue ending at a specific diagnosis timestamp.")
    parser.add_argument("--query", action="store_true", help="Query a queue by --queue-id.")
    parser.add_argument("--queue-id", default="", help="Queue id or hash.")
    parser.add_argument("--window-minutes", type=int, default=60, help="Queue time span.")
    parser.add_argument("--step-minutes", type=int, default=5, help="Diagnosis step.")
    parser.add_argument("--queue-size", type=int, default=12, help="Number of diagnosis records per queue.")
    parser.add_argument("--config", default="", help="Optional config.yaml path.")
    parser.add_argument("--write", action="store_true", help="Write queue to PostgreSQL.")
    parser.add_argument("--dry-run", action="store_true", help="Report without writing.")
    args = parser.parse_args()
    store = DiagnosisStore(args.config or None)
    if args.query:
        if not args.queue_id:
            raise SystemExit("--query requires --queue-id")
        queue = store.get_diagnosis_queue(args.queue_id)
        print(json.dumps({"ok": bool(queue), "queue": queue}, ensure_ascii=False, default=str, indent=2))
        return 0
    queue_end = parse_time(args.build_at) if args.build_at else None
    result = build_queue(
        args.config or None,
        queue_end_ts=queue_end,
        window_minutes=args.window_minutes,
        step_minutes=args.step_minutes,
        queue_size=args.queue_size,
        write=args.write and not args.dry_run,
    )
    print(json.dumps({"ok": True, "queue": result}, ensure_ascii=False, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
