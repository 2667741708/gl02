from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from catalog import physical_points
from store import connect, ensure_schema, summary, update_sync_state, upsert_registry, upsert_values


ROOT_DIR = Path(__file__).resolve().parents[0].parent
WORKSPACE_ROOT = ROOT_DIR.parents[0]
TREND_BACKEND = WORKSPACE_ROOT / "趋势分析" / "trend_backend"
if str(TREND_BACKEND) not in sys.path:
    sys.path.insert(0, str(TREND_BACKEND))

import pspace_history  # noqa: E402


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = pspace_history.parse_timestamp(value)
    if parsed is None:
        raise argparse.ArgumentTypeError(f"Unsupported time: {value}")
    return parsed.replace(second=0, microsecond=0)


def text_time(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def chunk_windows(start: datetime, end: datetime, hours: float):
    current = start
    delta = timedelta(hours=hours)
    while current < end:
        next_end = min(end, current + delta)
        yield current, next_end
        current = next_end


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync required GL02/GF2 points from pSpace 243 into SQLite.")
    parser.add_argument("--db", default="")
    parser.add_argument("--config", default=str(ROOT_DIR / "config" / "sync_config.json"))
    parser.add_argument("--days", type=float, default=90)
    parser.add_argument("--hours", type=float, default=None)
    parser.add_argument("--start-time", default="")
    parser.add_argument("--end-time", default="")
    parser.add_argument("--chunk-hours", type=float, default=12)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--max-workers", type=int, default=2)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--retry-sleep", type=float, default=8)
    parser.add_argument("--continuous", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=60)
    parser.add_argument("--lookback-minutes", type=float, default=8)
    parser.add_argument("--max-tags", type=int, default=0, help="Smoke-test limit.")
    return parser.parse_args()


def sync_window(args: argparse.Namespace, start: datetime, end: datetime) -> dict[str, object]:
    conn = connect(args.db or None, args.config)
    ensure_schema(conn, args.config)
    points = physical_points(args.config)
    if args.max_tags > 0:
        points = points[: args.max_tags]
    upsert_registry(conn, points)

    connection = pspace_history.resolve_connection(config_path=WORKSPACE_ROOT / "ghsc" / "src" / "main" / "resources" / "application-dev.yml")
    source_server = f"{connection['server']}:{connection['port']}"
    PsObject, T = pspace_history.load_sdk(WORKSPACE_ROOT / "pythonSDK(1)")
    tags = [point.tag_long_name for point in points]
    inserted_total = 0
    failed_chunks = 0

    for index, (chunk_start, chunk_end) in enumerate(chunk_windows(start, end, args.chunk_hours), start=1):
        series_by_tag = {}
        errors_by_tag = {}
        chunk_error = ""
        for attempt in range(1, args.retries + 1):
            try:
                series_by_tag, errors_by_tag = pspace_history.fetch_history_concurrent(
                    PsObject,
                    T,
                    connection,
                    tags,
                    chunk_start,
                    chunk_end,
                    60,
                    "PS_HIS_AVERAGE",
                    batch_size=args.batch_size,
                    max_workers=args.max_workers,
                )
                chunk_error = ""
                break
            except Exception as exc:  # noqa: BLE001
                chunk_error = str(exc)
                if attempt < args.retries:
                    time.sleep(args.retry_sleep)
        if chunk_error:
            failed_chunks += 1
            errors_by_tag = {tag: chunk_error for tag in tags}
            update_sync_state(conn, tags, text_time(chunk_end), errors_by_tag)
            print(json.dumps({"chunk": index, "start": text_time(chunk_start), "end": text_time(chunk_end), "error": chunk_error}, ensure_ascii=False), flush=True)
            continue

        inserted = upsert_values(conn, series_by_tag, source_server)
        inserted_total += inserted
        update_sync_state(conn, tags, text_time(chunk_end), errors_by_tag)
        print(
            json.dumps(
                {
                    "chunk": index,
                    "start": text_time(chunk_start),
                    "end": text_time(chunk_end),
                    "inserted": inserted,
                    "tags_ok": len(series_by_tag),
                    "tags_error": len(errors_by_tag),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    return {"inserted_rows": inserted_total, "failed_chunks": failed_chunks, "summary": summary(conn)}


def main() -> int:
    args = parse_args()
    while True:
        end = parse_time(args.end_time) or datetime.now().replace(second=0, microsecond=0)
        if args.continuous:
            start = end - timedelta(minutes=args.lookback_minutes)
        elif args.start_time:
            start = parse_time(args.start_time)
        else:
            span = timedelta(hours=args.hours) if args.hours is not None else timedelta(days=args.days)
            start = end - span
        if start is None:
            raise ValueError("start time is required")
        result = sync_window(args, start.replace(second=0, microsecond=0), end)
        print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2), flush=True)
        if not args.continuous:
            return 0
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
