from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from psycopg.types.json import Jsonb

from service_config import project_path
from store import DiagnosisStore


SERVICE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SERVICE_DIR.parent
TREND_BACKEND_CANDIDATES = [
    PROJECT_ROOT / "趋势分析" / "trend_backend",
    PROJECT_ROOT / "trend_analysis" / "trend_backend",
]
for candidate in TREND_BACKEND_CANDIDATES:
    if (candidate / "pspace_history.py").exists() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
        break

import pspace_history  # noqa: E402


DEFAULT_AGGREGATE = "PS_HIS_AVERAGE"


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("T", " ")).replace(second=0, microsecond=0)


def timestamp_text(value: datetime) -> str:
    return value.replace(second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def load_pspace_connection() -> tuple[Any, Any, dict[str, str]]:
    config_candidates = [
        PROJECT_ROOT / "ghsc" / "src" / "main" / "resources" / "application-prod.yml",
        PROJECT_ROOT / "ghsc" / "src" / "main" / "resources" / "application-dev.yml",
        PROJECT_ROOT.parent / f"{PROJECT_ROOT.name}_AUTO_PREVIEW" / "ghsc" / "src" / "main" / "resources" / "application-prod.yml",
        PROJECT_ROOT.parent / f"{PROJECT_ROOT.name}_AUTO_PREVIEW" / "ghsc" / "src" / "main" / "resources" / "application-dev.yml",
    ]
    config_path = next((path for path in config_candidates if path.exists()), None)
    connection = pspace_history.resolve_connection(config_path=config_path)
    PsObject, T = pspace_history.load_sdk(PROJECT_ROOT / "pythonSDK(1)")
    return PsObject, T, connection


def parse_processed_with_quality(result: dict[str, Any], T, tags: list[str]) -> tuple[dict[str, dict[str, dict[str, Any]]], dict[str, str]]:
    series_by_tag: dict[str, dict[str, dict[str, Any]]] = {}
    errors_by_tag: dict[str, str] = {}
    for tag in tags:
        tag_result = result.get(tag)
        if not isinstance(tag_result, dict):
            errors_by_tag[tag] = f"missing_result return={result.get(T.Return)}"
            continue
        item_error = tag_result.get("Error")
        if item_error not in (None, "", 0, "0"):
            errors_by_tag[tag] = str(item_error)
        series: dict[str, dict[str, Any]] = {}
        for _, record in pspace_history.numeric_items(tag_result):
            if not isinstance(record, dict):
                continue
            parsed_time = pspace_history.parse_timestamp(record.get(T.TimeStamp))
            if parsed_time is None:
                continue
            series[timestamp_text(parsed_time)] = {
                "value": pspace_history.coerce_number(record.get(T.ValueDict)),
                "quality": str(record.get(T.QualityDict, "") or ""),
            }
        if series:
            series_by_tag[tag] = series
        elif tag not in errors_by_tag:
            errors_by_tag[tag] = "no processed rows returned"
    return series_by_tag, errors_by_tag


def select_raw_record(
    records: list[tuple[datetime, float | None, str]],
    method: str,
) -> dict[str, Any] | None:
    ordered = sorted(records, key=lambda item: item[0])
    numeric_records = [(ts, float(value), quality) for ts, value, quality in ordered if value is not None]
    if not numeric_records:
        return None
    normalized = str(method or "sample").strip().lower()
    if normalized in {"sample", "last", "latest", "any"}:
        raw_ts, value, quality = numeric_records[-1]
        return {"value": value, "quality": quality, "raw_timestamp": raw_ts, "raw_count": len(numeric_records)}
    if normalized in {"first", "earliest"}:
        raw_ts, value, quality = numeric_records[0]
        return {"value": value, "quality": quality, "raw_timestamp": raw_ts, "raw_count": len(numeric_records)}
    value = pspace_history.aggregate_numeric_values([value for _, value, _ in numeric_records], normalized)
    return {
        "value": value,
        "quality": f"RAW_{normalized.upper()}",
        "raw_timestamp": numeric_records[-1][0],
        "raw_count": len(numeric_records),
    }


def parse_raw_with_quality(
    result: dict[str, Any],
    T,
    tags: list[str],
    *,
    target_interval_seconds: int = 60,
    aggregate_method: str = "sample",
) -> tuple[dict[str, dict[str, dict[str, Any]]], dict[str, str]]:
    series_by_tag: dict[str, dict[str, dict[str, Any]]] = {}
    errors_by_tag: dict[str, str] = {}
    for tag in tags:
        tag_result = result.get(tag)
        if not isinstance(tag_result, dict):
            errors_by_tag[tag] = f"missing_raw_result return={result.get(T.Return)}"
            continue
        item_error = tag_result.get("ErrorInfo") or tag_result.get("Error")
        if item_error not in (None, "", 0, "0"):
            errors_by_tag[tag] = str(item_error)

        records_by_bucket: dict[datetime, list[tuple[datetime, float | None, str]]] = {}
        for _, record in pspace_history.numeric_items(tag_result):
            if not isinstance(record, dict):
                continue
            parsed_time = pspace_history.parse_timestamp(record.get(T.HisReadRawTimeStamp))
            if parsed_time is None:
                continue
            bucket = pspace_history.floor_timestamp(parsed_time, target_interval_seconds)
            records_by_bucket.setdefault(bucket, []).append(
                (
                    parsed_time,
                    pspace_history.coerce_number(record.get(T.HisReadRawValueDict)),
                    str(record.get(T.HisReadRawQualityDict, "") or ""),
                )
            )

        series: dict[str, dict[str, Any]] = {}
        for bucket, records in sorted(records_by_bucket.items()):
            selected = select_raw_record(records, aggregate_method)
            if selected is not None:
                series[timestamp_text(bucket)] = selected
        if series:
            series_by_tag[tag] = series
        elif tag not in errors_by_tag:
            errors_by_tag[tag] = "no raw rows returned"
    return series_by_tag, errors_by_tag


def load_sync_source_options(store: DiagnosisStore) -> dict[str, Any]:
    source_options: dict[str, Any] = {
        "source_mode": "processed",
        "source_aggregate": "average",
        "source_interval_seconds": 5,
        "raw_max_values": 20000,
        "raw_bounds": 0,
        "target_aggregate": DEFAULT_AGGREGATE,
        "target_interval_seconds": 60,
    }
    sync_path = store.config.get("paths", {}).get("sync_config")
    if not sync_path:
        return source_options
    try:
        config = json.loads(project_path(sync_path).read_text(encoding="utf-8"))
    except Exception as exc:
        source_options["config_error"] = str(exc)
        return source_options
    source_cfg = config.get("source", {})
    source_options.update(
        {
            "source_mode": str(source_cfg.get("source_mode") or source_options["source_mode"]).strip().lower(),
            "source_aggregate": str(source_cfg.get("source_aggregate") or source_options["source_aggregate"]).strip().lower(),
            "source_interval_seconds": int(source_cfg.get("source_interval_seconds") or source_options["source_interval_seconds"]),
            "raw_max_values": int(source_cfg.get("raw_max_values") or source_options["raw_max_values"]),
            "raw_bounds": int(source_cfg.get("raw_bounds", source_options["raw_bounds"])),
            "target_aggregate": str(source_cfg.get("target_aggregate") or source_cfg.get("aggregate") or source_options["target_aggregate"]),
            "target_interval_seconds": int(source_cfg.get("target_interval_seconds") or source_cfg.get("interval_seconds") or source_options["target_interval_seconds"]),
        }
    )
    return source_options


def fetch_pspace_processed(
    tags: list[str],
    start: datetime,
    end: datetime,
    *,
    batch_size: int,
    aggregate: str = DEFAULT_AGGREGATE,
) -> tuple[dict[str, dict[str, dict[str, Any]]], dict[str, str], str]:
    PsObject, T, connection = load_pspace_connection()
    source_server = f"{connection['server']}:{connection['port']}"
    merged: dict[str, dict[str, dict[str, Any]]] = {}
    errors: dict[str, str] = {}
    for batch in pspace_history.chunked(tags, batch_size):
        pspace = pspace_history.connect_pspace(PsObject, T, connection)
        try:
            result = pspace_history.read_processed_batch(pspace, T, batch, start, end, 60, aggregate)
            series, batch_errors = parse_processed_with_quality(result, T, batch)
            merged.update(series)
            errors.update(batch_errors)
        finally:
            pspace_history.close_pspace(pspace)
    return merged, errors, source_server


def fetch_pspace_raw(
    tags: list[str],
    start: datetime,
    end: datetime,
    *,
    batch_size: int,
    target_interval_seconds: int,
    aggregate_method: str,
    raw_max_values: int,
    raw_bounds: int,
) -> tuple[dict[str, dict[str, dict[str, Any]]], dict[str, str], str]:
    PsObject, T, connection = load_pspace_connection()
    source_server = f"{connection['server']}:{connection['port']}"
    merged: dict[str, dict[str, dict[str, Any]]] = {}
    errors: dict[str, str] = {}
    for batch in pspace_history.chunked(tags, batch_size):
        pspace = pspace_history.connect_pspace(PsObject, T, connection)
        try:
            result = pspace_history.read_raw_batch(pspace, T, batch, start, end, raw_max_values, raw_bounds)
            series, batch_errors = parse_raw_with_quality(
                result,
                T,
                batch,
                target_interval_seconds=target_interval_seconds,
                aggregate_method=aggregate_method,
            )
            merged.update(series)
            errors.update(batch_errors)
        finally:
            pspace_history.close_pspace(pspace)
    return merged, errors, source_server


def zero_candidates(
    store: DiagnosisStore,
    start: datetime,
    end: datetime,
    *,
    limit: int,
    aggregate: str = DEFAULT_AGGREGATE,
) -> list[dict[str, Any]]:
    params: list[Any] = [start, end, aggregate, limit]
    with store.connection_scope() as conn:
        rows = conn.execute(
            """
            SELECT v.tag_long_name, r.variable_name, v.ts, v.value AS db_value,
                   v.aggregate, v.source_server, v.collected_at,
                   z.verification_status, z.verified_at
            FROM bf_sensor.one_minute_values v
            JOIN bf_sensor.sensor_registry r ON r.tag_long_name = v.tag_long_name
            LEFT JOIN bf_sensor.zero_value_audits z
              ON z.tag_long_name = v.tag_long_name
             AND z.ts = v.ts
             AND z.pspace_aggregate = v.aggregate
            WHERE r.is_enabled = true
              AND r.is_derived = false
              AND v.value = 0
              AND v.ts >= %s
              AND v.ts <= %s
              AND v.aggregate = %s
              AND (
                    z.tag_long_name IS NULL
                 OR z.verification_status <> 'verified_zero'
                 OR z.verified_at < v.collected_at
              )
            ORDER BY v.ts DESC, r.variable_name ASC
            LIMIT %s
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def write_audits(store: DiagnosisStore, audits: list[dict[str, Any]]) -> int:
    if not audits:
        return 0
    with store.connection_scope() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO bf_sensor.zero_value_audits (
                    tag_long_name, variable_name, ts, db_value, pspace_value,
                    pspace_quality, pspace_aggregate, source_server,
                    verification_status, error, details, verified_at
                )
                VALUES (
                    %(tag_long_name)s, %(variable_name)s, %(ts)s, %(db_value)s, %(pspace_value)s,
                    %(pspace_quality)s, %(pspace_aggregate)s, %(source_server)s,
                    %(verification_status)s, %(error)s, %(details)s, now()
                )
                ON CONFLICT(tag_long_name, ts, pspace_aggregate) DO UPDATE SET
                    variable_name=excluded.variable_name,
                    db_value=excluded.db_value,
                    pspace_value=excluded.pspace_value,
                    pspace_quality=excluded.pspace_quality,
                    source_server=excluded.source_server,
                    verification_status=excluded.verification_status,
                    error=excluded.error,
                    details=excluded.details,
                    verified_at=excluded.verified_at
                """,
                [{**audit, "details": Jsonb(json.loads(json.dumps(audit.get("details", {}), ensure_ascii=False, default=str)))} for audit in audits],
            )
        conn.commit()
    return len(audits)


def audit_zero_values(
    config_path: str | Path | None = None,
    *,
    start: datetime,
    end: datetime,
    limit: int = 1000,
    batch_size: int = 20,
    aggregate: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    store = DiagnosisStore(config_path)
    store.ensure_schema()
    policy = store.config.get("zero_value_policy", {})
    epsilon = float(policy.get("epsilon", 1.0e-9))
    source_options = load_sync_source_options(store)
    target_aggregate = str(aggregate or source_options.get("target_aggregate") or DEFAULT_AGGREGATE)
    candidates = zero_candidates(store, start, end, limit=limit, aggregate=target_aggregate)
    if not candidates:
        return {"ok": True, "candidate_count": 0, "written": 0, "status_counts": {}, "source_options": source_options}

    tags = sorted({row["tag_long_name"] for row in candidates})
    if str(source_options.get("source_mode", "processed")).lower() == "raw":
        series_by_tag, errors_by_tag, source_server = fetch_pspace_raw(
            tags,
            start,
            end,
            batch_size=batch_size,
            target_interval_seconds=int(source_options.get("target_interval_seconds") or 60),
            aggregate_method=str(source_options.get("source_aggregate") or "sample"),
            raw_max_values=int(source_options.get("raw_max_values") or 20000),
            raw_bounds=int(source_options.get("raw_bounds") or 0),
        )
        verification_source_mode = "raw"
    else:
        series_by_tag, errors_by_tag, source_server = fetch_pspace_processed(
            tags,
            start,
            end,
            batch_size=batch_size,
            aggregate=target_aggregate,
        )
        verification_source_mode = "processed"
    audits: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    for row in candidates:
        tag = str(row["tag_long_name"])
        ts = row["ts"].replace(second=0, microsecond=0)
        ts_key = timestamp_text(ts)
        pspace_record = series_by_tag.get(tag, {}).get(ts_key)
        error = errors_by_tag.get(tag, "")
        pspace_value = None if not pspace_record else pspace_record.get("value")
        if error:
            status = "pspace_error"
        elif pspace_record is None or pspace_value is None:
            status = "pspace_missing"
        elif math.isfinite(float(pspace_value)) and abs(float(pspace_value)) <= epsilon:
            status = "verified_zero"
        else:
            status = "pspace_nonzero"
        status_counts[status] = status_counts.get(status, 0) + 1
        audits.append(
            {
                "tag_long_name": tag,
                "variable_name": row["variable_name"],
                "ts": ts,
                "db_value": row["db_value"],
                "pspace_value": pspace_value,
                "pspace_quality": "" if not pspace_record else str(pspace_record.get("quality", "") or ""),
                "pspace_aggregate": target_aggregate,
                "source_server": source_server,
                "verification_status": status,
                "error": error,
                "details": {
                    "db_source_server": row.get("source_server", ""),
                    "db_collected_at": row.get("collected_at"),
                    "epsilon": epsilon,
                    "verification_source_mode": verification_source_mode,
                    "verification_source_aggregate": source_options.get("source_aggregate"),
                    "raw_timestamp": None if not pspace_record else pspace_record.get("raw_timestamp"),
                    "raw_count": None if not pspace_record else pspace_record.get("raw_count"),
                },
            }
        )
    written = 0 if dry_run else write_audits(store, audits)
    return {
        "ok": True,
        "start": start,
        "end": end,
        "candidate_count": len(candidates),
        "tag_count": len(tags),
        "written": written,
        "dry_run": dry_run,
        "status_counts": status_counts,
        "source_options": source_options,
    }


def audit_recent_zeros(
    config_path: str | Path | None = None,
    *,
    minutes: int = 180,
    limit: int = 1000,
    batch_size: int = 20,
    dry_run: bool = False,
) -> dict[str, Any]:
    store = DiagnosisStore(config_path)
    latest = store.latest_data_ts() or datetime.now().replace(second=0, microsecond=0)
    end = latest.replace(second=0, microsecond=0)
    start = end - timedelta(minutes=minutes)
    return audit_zero_values(config_path, start=start, end=end, limit=limit, batch_size=batch_size, dry_run=dry_run)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify PostgreSQL zero sensor values against the configured pSpace source mode.")
    parser.add_argument("--config", default="")
    parser.add_argument("--start", default="")
    parser.add_argument("--end", default="")
    parser.add_argument("--minutes", type=int, default=180)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--aggregate", default="", help="Target DB aggregate label to audit; defaults to sync_config target_aggregate.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.start or args.end:
        end = parse_time(args.end) if args.end else datetime.now().replace(second=0, microsecond=0)
        start = parse_time(args.start) if args.start else end - timedelta(minutes=args.minutes)
        result = audit_zero_values(
            args.config or None,
            start=start,
            end=end,
            limit=args.limit,
            batch_size=args.batch_size,
            aggregate=args.aggregate or None,
            dry_run=args.dry_run,
        )
    else:
        result = audit_recent_zeros(args.config or None, minutes=args.minutes, limit=args.limit, batch_size=args.batch_size, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, default=str, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
