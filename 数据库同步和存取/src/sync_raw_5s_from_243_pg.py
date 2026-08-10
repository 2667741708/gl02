from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from catalog import physical_points
from pg_store import (
    apply_raw_5s_retention,
    connect,
    ensure_raw_5s_partitions,
    ensure_schema,
    raw_5s_summary,
    upsert_raw_5s_values,
    upsert_registry,
)


ROOT_DIR = Path(__file__).resolve().parents[0].parent
WORKSPACE_ROOT = ROOT_DIR.parents[0]
TREND_BACKEND_CANDIDATES = [
    WORKSPACE_ROOT / "trend_analysis" / "trend_backend",
    WORKSPACE_ROOT / "趋势分析" / "trend_backend",
]
for candidate in TREND_BACKEND_CANDIDATES:
    if candidate.exists():
        if str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
        break

import pspace_history  # noqa: E402


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = pspace_history.parse_timestamp(value)
    if parsed is None:
        raise argparse.ArgumentTypeError(f"Unsupported time: {value}")
    return parsed.replace(microsecond=0)


def chunked(items: list[Any], size: int) -> list[list[Any]]:
    size = max(1, int(size))
    return [items[index : index + size] for index in range(0, len(items), size)]


def parse_raw_rows(
    result: dict[str, Any],
    T,
    tags: list[str],
    *,
    source_server: str,
    read_start: datetime,
    read_end: datetime,
    raw_interval_seconds: int,
    collected_at: datetime,
) -> tuple[list[tuple[Any, ...]], dict[str, str], dict[str, int]]:
    rows: list[tuple[Any, ...]] = []
    errors: dict[str, str] = {}
    row_counts: dict[str, int] = {}

    for tag in tags:
        tag_result = result.get(tag)
        if not isinstance(tag_result, dict):
            errors[tag] = f"missing_raw_result return={result.get(T.Return)}"
            continue

        item_error = tag_result.get("ErrorInfo") or tag_result.get("Error")
        if item_error not in (None, "", 0, "0"):
            errors[tag] = str(item_error)

        count = 0
        for _, record in pspace_history.numeric_items(tag_result):
            if not isinstance(record, dict):
                continue
            parsed_ts = pspace_history.parse_timestamp(record.get(T.HisReadRawTimeStamp))
            if parsed_ts is None:
                continue
            value = pspace_history.coerce_number(record.get(T.HisReadRawValueDict))
            quality = str(record.get(T.HisReadRawQualityDict, "") or "")
            rows.append(
                (
                    tag,
                    parsed_ts.replace(microsecond=0),
                    value,
                    quality,
                    None,
                    raw_interval_seconds,
                    source_server,
                    read_start,
                    read_end,
                    collected_at,
                )
            )
            count += 1

        if count:
            row_counts[tag] = count
        elif tag not in errors:
            errors[tag] = "no raw rows returned"

    return rows, errors, row_counts


def read_raw_batch(
    PsObject,
    T,
    connection: dict[str, str],
    tags: list[str],
    start: datetime,
    end: datetime,
    *,
    raw_max_values: int,
    raw_bounds: int,
    raw_interval_seconds: int,
    source_server: str,
) -> tuple[list[tuple[Any, ...]], dict[str, str], dict[str, int]]:
    pspace = pspace_history.connect_pspace(PsObject, T, connection)
    try:
        result = pspace_history.read_raw_batch(pspace, T, tags, start, end, raw_max_values, raw_bounds)
        return parse_raw_rows(
            result,
            T,
            tags,
            source_server=source_server,
            read_start=start,
            read_end=end,
            raw_interval_seconds=raw_interval_seconds,
            collected_at=datetime.now().replace(microsecond=0),
        )
    finally:
        pspace_history.close_pspace(pspace)


def resolve_connection() -> dict[str, str]:
    pspace_config_candidates = [
        WORKSPACE_ROOT / "ghsc" / "src" / "main" / "resources" / "application-prod.yml",
        WORKSPACE_ROOT / "ghsc" / "src" / "main" / "resources" / "application-dev.yml",
        WORKSPACE_ROOT.parent / f"{WORKSPACE_ROOT.name}_AUTO_PREVIEW" / "ghsc" / "src" / "main" / "resources" / "application-prod.yml",
        WORKSPACE_ROOT.parent / f"{WORKSPACE_ROOT.name}_AUTO_PREVIEW" / "ghsc" / "src" / "main" / "resources" / "application-dev.yml",
    ]
    pspace_config_path = next((path for path in pspace_config_candidates if path.exists()), None)
    return pspace_history.resolve_connection(config_path=pspace_config_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch-read pSpace 5s raw rows for required GL02/GF2 points and write bf_sensor.raw_5s_values."
    )
    parser.add_argument("--config", default=str(ROOT_DIR / "config" / "sync_config.json"))
    parser.add_argument("--minutes", type=float, default=10, help="Lookback minutes when start/end are omitted.")
    parser.add_argument("--start-time", default="")
    parser.add_argument("--end-time", default="")
    parser.add_argument("--batch-size", type=int, default=115, help="Number of point tags per HisReadRaw request.")
    parser.add_argument("--max-workers", type=int, default=1, help="Concurrent SDK connections. Keep 1 for production safety.")
    parser.add_argument("--raw-max-values", type=int, default=200000)
    parser.add_argument("--raw-bounds", type=int, default=0)
    parser.add_argument("--raw-interval-seconds", type=int, default=5)
    parser.add_argument("--max-tags", type=int, default=0, help="Smoke-test limit.")
    parser.add_argument("--retention-days", type=int, default=30)
    parser.add_argument("--skip-schema", action="store_true")
    parser.add_argument("--skip-retention", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    end = parse_time(args.end_time) or datetime.now().replace(microsecond=0)
    start = parse_time(args.start_time) or (end - timedelta(minutes=args.minutes))
    if start >= end:
        raise SystemExit("start-time must be earlier than end-time")

    points = physical_points(args.config)
    if args.max_tags > 0:
        points = points[: args.max_tags]
    tags = [point.tag_long_name for point in points]
    batches = chunked(tags, args.batch_size)
    worker_count = max(1, min(int(args.max_workers), len(batches)))

    connection = resolve_connection()
    source_server = f"{connection['server']}:{connection['port']}"
    PsObject, T = pspace_history.load_sdk(WORKSPACE_ROOT / "pythonSDK(1)")

    all_rows: list[tuple[Any, ...]] = []
    all_errors: dict[str, str] = {}
    row_counts: dict[str, int] = {}
    started = time.time()

    def worker(batch: list[str]):
        return read_raw_batch(
            PsObject,
            T,
            connection,
            batch,
            start,
            end,
            raw_max_values=args.raw_max_values,
            raw_bounds=args.raw_bounds,
            raw_interval_seconds=args.raw_interval_seconds,
            source_server=source_server,
        )

    if worker_count == 1:
        for batch in batches:
            rows, errors, counts = worker(batch)
            all_rows.extend(rows)
            all_errors.update(errors)
            row_counts.update(counts)
    else:
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [executor.submit(worker, batch) for batch in batches]
            for future in as_completed(futures):
                rows, errors, counts = future.result()
                all_rows.extend(rows)
                all_errors.update(errors)
                row_counts.update(counts)

    written = 0
    db_summary: dict[str, Any] = {}
    if not args.dry_run:
        with connect(args.config) as conn:
            if not args.skip_schema:
                ensure_schema(conn, args.config)
            ensure_raw_5s_partitions(conn, start, end)
            upsert_registry(conn, points)
            written = upsert_raw_5s_values(conn, all_rows)
            dropped = 0 if args.skip_retention else apply_raw_5s_retention(conn, args.retention_days)
            db_summary = raw_5s_summary(conn)
            db_summary["dropped_old_partitions"] = dropped

    result = {
        "ok": True,
        "dry_run": bool(args.dry_run),
        "source_server": source_server,
        "start": str(start),
        "end": str(end),
        "physical_tags": len(tags),
        "batch_size": args.batch_size,
        "batches": len(batches),
        "max_workers": worker_count,
        "raw_rows_read": len(all_rows),
        "raw_rows_written": written,
        "tags_ok": len(row_counts),
        "tags_error": len(all_errors),
        "sample_errors": dict(list(all_errors.items())[:10]),
        "elapsed_seconds": round(time.time() - started, 3),
        "database": db_summary,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if not all_errors or all_rows else 2


if __name__ == "__main__":
    raise SystemExit(main())
