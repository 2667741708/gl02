from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from catalog import load_config, physical_points
from coal_hourly import refresh_coal_injection_hourly
from pg_store import (
    apply_retention,
    apply_raw_5s_retention,
    connect,
    ensure_partitions,
    ensure_raw_5s_partitions,
    ensure_schema,
    finish_run,
    latest_values_before,
    start_run,
    summary,
    update_sync_state,
    upsert_raw_5s_values,
    upsert_registry,
    upsert_values,
)
import raw_minute_pipeline


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


def resolve_state_hold_minutes(config: dict[str, object], points) -> dict[str, int]:
    materialization = dict(config.get("state_materialization") or {})
    if not materialization.get("enabled", False):
        return {}
    policies = list(materialization.get("policies") or [])
    result: dict[str, int] = {}
    for point in points:
        variable = str(point.variable_name)
        for policy in policies:
            item = dict(policy)
            variables = {str(value) for value in item.get("variables", [])}
            prefix = str(item.get("variable_prefix") or "")
            if variable in variables or (prefix and variable.startswith(prefix)):
                result[str(point.tag_long_name)] = int(item.get("maximum_hold_minutes") or 0)
                break
    return {tag: minutes for tag, minutes in result.items() if minutes > 0}


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
    parser = argparse.ArgumentParser(description="Sync required GL02/GF2 points from pSpace 243 into PostgreSQL.")
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
    parser.add_argument("--poll-seconds", type=float, default=30)
    parser.add_argument("--lookback-minutes", type=float, default=10)
    parser.add_argument("--source-mode", choices=["processed", "raw"], default=None, help="Read pSpace processed 1min rows or raw rows aggregated before write.")
    parser.add_argument("--source-interval-seconds", type=int, default=None, help="Expected raw sample interval, used for run metadata and sizing.")
    parser.add_argument(
        "--source-aggregate",
        default=None,
        help="Method for raw rows before 1min write: sample/last/first/average/median. sample uses the latest valid raw value in each minute.",
    )
    parser.add_argument("--raw-max-values", type=int, default=None, help="Max raw values per tag requested from HisReadRaw.")
    parser.add_argument("--raw-bounds", type=int, default=None, help="HisReadRaw Bounds flag.")
    parser.add_argument("--target-aggregate", default=None, help="Aggregate label written to one_minute_values.")
    parser.add_argument("--target-interval-seconds", type=int, default=None, help="Interval written to one_minute_values.")
    raw_persist_group = parser.add_mutually_exclusive_group()
    raw_persist_group.add_argument("--persist-raw-5s", dest="persist_raw_5s", action="store_true")
    raw_persist_group.add_argument("--no-persist-raw-5s", dest="persist_raw_5s", action="store_false")
    parser.set_defaults(persist_raw_5s=None)
    parser.add_argument("--raw-retention-days", type=int, default=None)
    parser.add_argument("--minute-completion-lag-seconds", type=int, default=None)
    parser.add_argument("--max-tags", type=int, default=0, help="Smoke-test limit.")
    parser.add_argument("--variables", default="", help="Comma-separated variable_name allowlist for a scoped backfill.")
    parser.add_argument("--skip-retention", action="store_true")
    parser.add_argument("--skip-schema", action="store_true")
    return parser.parse_args()


def resolve_source_options(args: argparse.Namespace) -> dict[str, object]:
    config = load_config(args.config)
    source_cfg = config.get("source", {})
    sync_cfg = config.get("sync", {})

    source_mode = str(
        args.source_mode
        or source_cfg.get("source_mode")
        or sync_cfg.get("source_mode")
        or "processed"
    ).strip().lower()
    if source_mode not in {"processed", "raw"}:
        raise ValueError(f"Unsupported source mode: {source_mode}")

    target_interval_seconds = int(
        args.target_interval_seconds
        or source_cfg.get("target_interval_seconds")
        or source_cfg.get("interval_seconds")
        or 60
    )
    if args.target_aggregate:
        target_aggregate = str(args.target_aggregate)
    elif source_mode == "raw":
        target_aggregate = str(source_cfg.get("target_aggregate") or "PS_RAW_AVERAGE")
    else:
        target_aggregate = str(source_cfg.get("aggregate") or "PS_HIS_AVERAGE")
    source_interval_seconds = int(
        args.source_interval_seconds
        or source_cfg.get("source_interval_seconds")
        or (5 if source_mode == "raw" else target_interval_seconds)
    )
    source_aggregate = str(
        args.source_aggregate
        or source_cfg.get("source_aggregate")
        or "average"
    )
    raw_max_values = int(args.raw_max_values or source_cfg.get("raw_max_values") or 20000)
    raw_bounds = int(args.raw_bounds if args.raw_bounds is not None else source_cfg.get("raw_bounds", 0))
    persist_raw_5s = (
        bool(args.persist_raw_5s)
        if args.persist_raw_5s is not None
        else bool(source_cfg.get("persist_raw_5s", source_mode == "raw"))
    )
    raw_retention_days = int(args.raw_retention_days or source_cfg.get("raw_retention_days") or 30)
    minute_completion_lag_seconds = int(
        args.minute_completion_lag_seconds
        if args.minute_completion_lag_seconds is not None
        else source_cfg.get("minute_completion_lag_seconds", 60)
    )

    return {
        "source_mode": source_mode,
        "source_interval_seconds": source_interval_seconds,
        "source_aggregate": source_aggregate,
        "raw_max_values": raw_max_values,
        "raw_bounds": raw_bounds,
        "persist_raw_5s": persist_raw_5s,
        "raw_retention_days": raw_retention_days,
        "minute_completion_lag_seconds": minute_completion_lag_seconds,
        "target_aggregate": target_aggregate,
        "target_interval_seconds": target_interval_seconds,
    }


def fetch_history_with_retries(
    PsObject,
    T,
    connection: dict[str, str],
    tags: list[str],
    start: datetime,
    end: datetime,
    *,
    batch_size: int,
    max_workers: int,
    retries: int,
    retry_sleep: float,
    source_options: dict[str, object],
) -> tuple[
    dict[str, dict[str, float | None]],
    dict[str, dict[str, dict[str, object]]],
    dict[str, list[dict[str, object]]],
    dict[str, str],
]:
    """Retry only tags that returned no history rows or raised SDK errors."""
    pending = list(tags)
    merged_series: dict[str, dict[str, float | None]] = {}
    merged_audits: dict[str, dict[str, dict[str, object]]] = {}
    merged_raw_records: dict[tuple[str, datetime], dict[str, object]] = {}
    last_errors: dict[str, str] = {}
    attempts = max(1, int(retries))

    for attempt in range(1, attempts + 1):
        try:
            if str(source_options["source_mode"]) == "raw":
                series_by_tag, audits_by_tag, raw_records_by_tag, errors_by_tag = (
                    raw_minute_pipeline.fetch_raw_history_concurrent(
                        PsObject,
                        T,
                        connection,
                        pending,
                        start,
                        end,
                        pspace_history=pspace_history,
                        target_interval_seconds=int(source_options["target_interval_seconds"]),
                        source_interval_seconds=int(source_options["source_interval_seconds"]),
                        batch_size=batch_size,
                        max_workers=max_workers,
                        raw_max_values=int(source_options["raw_max_values"]),
                        raw_bounds=int(source_options["raw_bounds"]),
                        minute_completion_lag_seconds=int(
                            source_options["minute_completion_lag_seconds"]
                        ),
                    )
                )
            else:
                series_by_tag, errors_by_tag = pspace_history.fetch_history_concurrent(
                    PsObject,
                    T,
                    connection,
                    pending,
                    start,
                    end,
                    int(source_options["target_interval_seconds"]),
                    str(source_options["target_aggregate"]),
                    batch_size=batch_size,
                    max_workers=max_workers,
                    source_mode="processed",
                )
                audits_by_tag = {}
                raw_records_by_tag = {}
        except Exception as exc:  # noqa: BLE001
            series_by_tag = {}
            audits_by_tag = {}
            raw_records_by_tag = {}
            errors_by_tag = {tag: str(exc) for tag in pending}

        merged_series.update(series_by_tag)
        merged_audits.update(audits_by_tag)
        for tag, records in raw_records_by_tag.items():
            for record in records:
                parsed_ts = record.get("ts")
                if isinstance(parsed_ts, datetime):
                    merged_raw_records[(tag, parsed_ts)] = record
        last_errors.update(errors_by_tag)
        pending = [tag for tag in pending if tag not in series_by_tag]
        if not pending:
            raw_by_tag: dict[str, list[dict[str, object]]] = {}
            for (tag, _), record in sorted(merged_raw_records.items(), key=lambda item: item[0]):
                raw_by_tag.setdefault(tag, []).append(record)
            return merged_series, merged_audits, raw_by_tag, {}
        if attempt < attempts:
            time.sleep(retry_sleep)

    raw_by_tag: dict[str, list[dict[str, object]]] = {}
    for (tag, _), record in sorted(merged_raw_records.items(), key=lambda item: item[0]):
        raw_by_tag.setdefault(tag, []).append(record)
    errors = {
        tag: last_errors.get(tag, f"no {source_options['source_mode']} rows returned after retries")
        for tag in pending
    }
    return merged_series, merged_audits, raw_by_tag, errors


def sync_window(args: argparse.Namespace, start: datetime, end: datetime, sync_mode: str) -> dict[str, object]:
    config = load_config(args.config)
    conn = connect(args.config)
    if not args.skip_schema:
        ensure_schema(conn, args.config)
    ensure_partitions(conn, start, end)
    source_options = resolve_source_options(args)
    points = physical_points(args.config)
    if args.variables:
        requested = {item.strip() for item in args.variables.split(",") if item.strip()}
        points = [point for point in points if point.variable_name in requested]
        found = {point.variable_name for point in points}
        missing = sorted(requested - found)
        if missing:
            raise SystemExit(f"Requested variables are absent from point catalog: {missing}")
    if args.max_tags > 0:
        points = points[: args.max_tags]
    upsert_registry(conn, points)
    realtime_window = end-start <= timedelta(hours=2)
    hold_minutes_by_tag = resolve_state_hold_minutes(config, points) if realtime_window else {}
    held_rows_total = 0

    pspace_config_candidates = [
        WORKSPACE_ROOT / "ghsc" / "src" / "main" / "resources" / "application-prod.yml",
        WORKSPACE_ROOT / "ghsc" / "src" / "main" / "resources" / "application-dev.yml",
        WORKSPACE_ROOT.parent / f"{WORKSPACE_ROOT.name}_AUTO_PREVIEW" / "ghsc" / "src" / "main" / "resources" / "application-prod.yml",
        WORKSPACE_ROOT.parent / f"{WORKSPACE_ROOT.name}_AUTO_PREVIEW" / "ghsc" / "src" / "main" / "resources" / "application-dev.yml",
    ]
    pspace_config_path = next((path for path in pspace_config_candidates if path.exists()), None)
    connection = pspace_history.resolve_connection(config_path=pspace_config_path)
    source_server = f"{connection['server']}:{connection['port']}"
    PsObject, T = pspace_history.load_sdk(WORKSPACE_ROOT / "pythonSDK(1)")
    tags = [point.tag_long_name for point in points]
    inserted_total = 0
    raw_written_total = 0
    failed_chunks = 0
    persist_raw = bool(source_options["persist_raw_5s"] and source_options["source_mode"] == "raw")
    if persist_raw:
        ensure_raw_5s_partitions(conn, start, end)

    for index, (chunk_start, chunk_end) in enumerate(chunk_windows(start, end, args.chunk_hours), start=1):
        run_id = start_run(conn, sync_mode, chunk_start, chunk_end)
        series_by_tag = {}
        audits_by_tag = {}
        raw_records_by_tag = {}
        errors_by_tag = {}
        chunk_error = ""
        series_by_tag, audits_by_tag, raw_records_by_tag, errors_by_tag = fetch_history_with_retries(
            PsObject,
            T,
            connection,
            tags,
            chunk_start,
            chunk_end,
            batch_size=args.batch_size,
            max_workers=args.max_workers,
            retries=args.retries,
            retry_sleep=args.retry_sleep,
            source_options=source_options,
        )
        if not series_by_tag and len(errors_by_tag) == len(tags):
            failed_chunks += 1
            update_sync_state(conn, tags, chunk_end, errors_by_tag)
            chunk_error = "; ".join(sorted(set(errors_by_tag.values())))[:1000]
            finish_run(conn, run_id, 0, 0, len(errors_by_tag), chunk_error)
            print(json.dumps({"chunk": index, "start": text_time(chunk_start), "end": text_time(chunk_end), "error": chunk_error}, ensure_ascii=False), flush=True)
            continue

        held_rows = 0
        if hold_minutes_by_tag:
            maximum_hold = max(hold_minutes_by_tag.values())
            seeds = latest_values_before(
                conn,
                list(hold_minutes_by_tag),
                chunk_start,
                maximum_lookback_minutes=maximum_hold,
            )
            series_by_tag, audits_by_tag, held_rows = raw_minute_pipeline.materialize_bounded_state_minutes(
                series_by_tag,
                audits_by_tag,
                hold_minutes_by_tag=hold_minutes_by_tag,
                seed_by_tag=seeds,
                start_time=chunk_start,
                end_time=chunk_end,
                target_interval_seconds=int(source_options["target_interval_seconds"]),
                expected_sample_count=max(1, round(
                    int(source_options["target_interval_seconds"])
                    / max(1, int(source_options["source_interval_seconds"]))
                )),
            )
            held_rows_total += held_rows

        raw_written = 0
        if persist_raw:
            raw_rows = raw_minute_pipeline.raw_records_to_db_rows(
                raw_records_by_tag,
                source_interval_seconds=int(source_options["source_interval_seconds"]),
                source_server=source_server,
                read_start=chunk_start,
                read_end=chunk_end,
                collected_at=datetime.now().replace(microsecond=0),
            )
            raw_written = upsert_raw_5s_values(conn, raw_rows)
            raw_written_total += raw_written

        inserted = upsert_values(
            conn,
            series_by_tag,
            source_server,
            aggregate=str(source_options["target_aggregate"]),
            interval_seconds=int(source_options["target_interval_seconds"]),
            audit_by_tag=audits_by_tag,
            semantic_version=(
                raw_minute_pipeline.SEMANTIC_VERSION
                if source_options["source_mode"] == "raw"
                else "pspace_processed_average_v1"
            ),
        )
        inserted_total += inserted
        update_sync_state(conn, tags, chunk_end, errors_by_tag)
        finish_run(conn, run_id, inserted, len(series_by_tag), len(errors_by_tag))
        print(
            json.dumps(
                {
                    "chunk": index,
                    "start": text_time(chunk_start),
                    "end": text_time(chunk_end),
                    "inserted": inserted,
                    "state_hold_rows": held_rows,
                    "raw_rows_written": raw_written,
                    "tags_ok": len(series_by_tag),
                    "tags_error": len(errors_by_tag),
                    "source_mode": source_options["source_mode"],
                    "source_aggregate": source_options["source_aggregate"],
                    "target_aggregate": source_options["target_aggregate"],
                    "target_interval_seconds": source_options["target_interval_seconds"],
                    "persist_raw_5s": persist_raw,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    dropped = 0 if args.skip_retention else apply_retention(conn, retain_years=3)
    raw_dropped = (
        apply_raw_5s_retention(conn, int(source_options["raw_retention_days"]))
        if persist_raw and not args.skip_retention
        else 0
    )
    # FOREMAN-COAL-HOURLY-20260806-BEGIN
    coal_hourly = refresh_coal_injection_hourly(conn, start, end)
    # FOREMAN-COAL-HOURLY-20260806-END
    return {
        "inserted_rows": inserted_total,
        "raw_rows_written": raw_written_total,
        "failed_chunks": failed_chunks,
        "dropped_old_partitions": dropped,
        "dropped_old_raw_partitions": raw_dropped,
        "source_options": source_options,
        "state_hold_rows": held_rows_total,
        "coal_injection_hourly": coal_hourly,
        # FOREMAN-SYNC-LIGHT-SUMMARY-20260806
        "summary": {
            "physical_points": len(points),
            "current_window_rows_written": inserted_total,
            "current_window_raw_rows_written": raw_written_total,
            "failed_chunks": failed_chunks,
        },
    }


def main() -> int:
    args = parse_args()
    while True:
        end = parse_time(args.end_time) or datetime.now().replace(second=0, microsecond=0)
        if args.continuous:
            start = end - timedelta(minutes=args.lookback_minutes)
            mode = "continuous"
        elif args.start_time:
            start = parse_time(args.start_time)
            mode = "history_range"
        else:
            span = timedelta(hours=args.hours) if args.hours is not None else timedelta(days=args.days)
            start = end - span
            mode = "history"
        if start is None:
            raise ValueError("start time is required")
        result = sync_window(args, start.replace(second=0, microsecond=0), end, mode)
        print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2), flush=True)
        if not args.continuous:
            return 0
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
