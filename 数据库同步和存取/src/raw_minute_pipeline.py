from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any


SEMANTIC_VERSION = "valid_raw_mean_v1"
STATE_HOLD_SEMANTIC_VERSION = "bounded_state_hold_v1"


def _parse_series_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(microsecond=0)
    text = str(value or "").strip().replace("Z", "+00:00")
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).replace(microsecond=0)
    except ValueError:
        return None


def materialize_bounded_state_minutes(
    series_by_tag: dict[str, dict[str, float]],
    audit_by_tag: dict[str, dict[str, dict[str, Any]]],
    *,
    hold_minutes_by_tag: dict[str, int],
    seed_by_tag: dict[str, tuple[datetime, float]] | None,
    start_time: datetime,
    end_time: datetime,
    target_interval_seconds: int = 60,
    expected_sample_count: int = 12,
) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, dict[str, Any]]], int]:
    """Materialize auditable minute state without inventing raw samples.

    A held row keeps the timestamp of the target minute but is explicitly
    labelled PS_STATE_HOLD/Uncertain and never resets the age of its source
    observation.  A later real pSpace row wins for the same minute.
    """
    if target_interval_seconds <= 0:
        raise ValueError("target_interval_seconds must be positive")
    seeds = seed_by_tag or {}
    inserted = 0
    for tag, hold_minutes in hold_minutes_by_tag.items():
        maximum_age = max(0, int(hold_minutes)) * 60
        if maximum_age <= 0:
            continue
        real_series = series_by_tag.setdefault(tag, {})
        audits = audit_by_tag.setdefault(tag, {})
        real_by_ts = {
            parsed: float(value)
            for key, value in list(real_series.items())
            if value is not None and (parsed := _parse_series_timestamp(key)) is not None
        }
        latest = seeds.get(tag)
        cursor = start_time.replace(second=0, microsecond=0)
        final_minute = end_time.replace(second=0, microsecond=0)
        while cursor < final_minute:
            if cursor in real_by_ts:
                latest = (cursor, real_by_ts[cursor])
                cursor += timedelta(seconds=target_interval_seconds)
                continue
            if latest is not None:
                source_ts, value = latest
                age_seconds = int((cursor-source_ts).total_seconds())
                if 0 < age_seconds <= maximum_age:
                    key = cursor.isoformat(sep=" ")
                    real_series[key] = value
                    audits[key] = {
                        "aggregate": "PS_STATE_HOLD",
                        "sample_count": 0,
                        "numeric_sample_count": 0,
                        "good_sample_count": 0,
                        "expected_sample_count": expected_sample_count,
                        "coverage_ratio": 0.0,
                        "min_value": value,
                        "max_value": value,
                        "last_value": value,
                        "quality": f"Held:{age_seconds}s",
                        "window_complete": True,
                        "semantic_version": STATE_HOLD_SEMANTIC_VERSION,
                    }
                    inserted += 1
            cursor += timedelta(seconds=target_interval_seconds)
    return series_by_tag, audit_by_tag, inserted


def quality_is_good(value: Any) -> bool:
    """Return whether a pSpace raw quality value is acceptable for averaging."""
    normalized = str(value or "").strip().lower()
    if not normalized:
        return True
    if normalized == "192":
        return True
    return normalized.startswith("good")


def parse_raw_result_details(
    result: dict[str, Any],
    T,
    tags: list[str],
    pspace_history,
    *,
    target_interval_seconds: int = 60,
    source_interval_seconds: int = 5,
    minute_completion_lag_seconds: int = 60,
    observed_at: datetime | None = None,
) -> tuple[
    dict[str, dict[str, float]],
    dict[str, dict[str, dict[str, Any]]],
    dict[str, list[dict[str, Any]]],
    dict[str, str],
]:
    """Parse one HisReadRaw response into minute means, audits and raw rows."""
    series_by_tag: dict[str, dict[str, float]] = {}
    audit_by_tag: dict[str, dict[str, dict[str, Any]]] = {}
    raw_records_by_tag: dict[str, list[dict[str, Any]]] = {}
    errors_by_tag: dict[str, str] = {}
    expected_count = max(1, round(target_interval_seconds / max(1, source_interval_seconds)))
    completion_cutoff = (observed_at or datetime.now()) - timedelta(
        seconds=max(0, minute_completion_lag_seconds)
    )

    for tag in tags:
        tag_result = result.get(tag)
        if not isinstance(tag_result, dict):
            errors_by_tag[tag] = f"missing_raw_result return={result.get(T.Return)}"
            continue

        item_error = tag_result.get("ErrorInfo") or tag_result.get("Error")
        if item_error not in (None, "", 0, "0"):
            errors_by_tag[tag] = str(item_error)

        records_by_bucket: dict[datetime, list[tuple[datetime, float | None, str]]] = {}
        raw_records: list[dict[str, Any]] = []
        for _, record in pspace_history.numeric_items(tag_result):
            if not isinstance(record, dict):
                continue
            parsed_ts = pspace_history.parse_timestamp(record.get(T.HisReadRawTimeStamp))
            if parsed_ts is None:
                continue
            parsed_ts = parsed_ts.replace(microsecond=0)
            value = pspace_history.coerce_number(record.get(T.HisReadRawValueDict))
            quality = str(record.get(T.HisReadRawQualityDict, "") or "")
            bucket = pspace_history.floor_timestamp(parsed_ts, target_interval_seconds)
            records_by_bucket.setdefault(bucket, []).append((parsed_ts, value, quality))
            raw_records.append({"ts": parsed_ts, "value": value, "quality": quality})

        minute_series: dict[str, float] = {}
        minute_audits: dict[str, dict[str, Any]] = {}
        for bucket, records in sorted(records_by_bucket.items()):
            ordered = sorted(records, key=lambda item: item[0])
            numeric = [item for item in ordered if item[1] is not None]
            good = [item for item in numeric if quality_is_good(item[2])]
            bucket_key = pspace_history.timestamp_text(bucket)
            good_values = [float(item[1]) for item in good if item[1] is not None]
            coverage_ratio = min(1.0, len(good_values) / expected_count)
            minute_audits[bucket_key] = {
                "sample_count": len(ordered),
                "numeric_sample_count": len(numeric),
                "good_sample_count": len(good_values),
                "expected_sample_count": expected_count,
                "coverage_ratio": coverage_ratio,
                "min_value": min(good_values) if good_values else None,
                "max_value": max(good_values) if good_values else None,
                "last_value": good_values[-1] if good_values else None,
                "quality": "Good" if good_values and len(good_values) == len(numeric) else "Uncertain",
                "window_complete": (
                    bucket + timedelta(seconds=target_interval_seconds) <= completion_cutoff
                ),
                "semantic_version": SEMANTIC_VERSION,
            }
            if good_values:
                minute_series[bucket_key] = sum(good_values) / len(good_values)

        if raw_records:
            raw_records_by_tag[tag] = raw_records
        if minute_audits:
            audit_by_tag[tag] = minute_audits
        if minute_series:
            series_by_tag[tag] = minute_series
        elif tag not in errors_by_tag:
            errors_by_tag[tag] = "no good raw rows returned"

    return series_by_tag, audit_by_tag, raw_records_by_tag, errors_by_tag


def fetch_raw_history_concurrent(
    PsObject,
    T,
    connection: dict[str, str],
    tags: list[str],
    start_time: datetime,
    end_time: datetime,
    *,
    pspace_history,
    target_interval_seconds: int,
    source_interval_seconds: int,
    batch_size: int,
    max_workers: int,
    raw_max_values: int,
    raw_bounds: int,
    minute_completion_lag_seconds: int = 60,
) -> tuple[
    dict[str, dict[str, float]],
    dict[str, dict[str, dict[str, Any]]],
    dict[str, list[dict[str, Any]]],
    dict[str, str],
]:
    """Read raw pSpace history once and return both minute and raw payloads."""
    if not tags:
        return {}, {}, {}, {}
    batches = pspace_history.chunked(tags, batch_size)
    worker_count = max(1, min(int(max_workers), len(batches)))
    query_observed_at = datetime.now()

    def worker(batch: list[str]):
        pspace = pspace_history.connect_pspace(PsObject, T, connection)
        try:
            result = pspace_history.read_raw_batch(
                pspace,
                T,
                batch,
                start_time,
                end_time,
                raw_max_values,
                raw_bounds,
            )
            return parse_raw_result_details(
                result,
                T,
                batch,
                pspace_history,
                target_interval_seconds=target_interval_seconds,
                source_interval_seconds=source_interval_seconds,
                minute_completion_lag_seconds=minute_completion_lag_seconds,
                observed_at=query_observed_at,
            )
        finally:
            pspace_history.close_pspace(pspace)

    all_series: dict[str, dict[str, float]] = {}
    all_audits: dict[str, dict[str, dict[str, Any]]] = {}
    all_raw_records: dict[str, list[dict[str, Any]]] = {}
    all_errors: dict[str, str] = {}

    if worker_count == 1:
        results = [worker(batch) for batch in batches]
    else:
        results = []
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [executor.submit(worker, batch) for batch in batches]
            for future in as_completed(futures):
                results.append(future.result())

    for series, audits, raw_records, errors in results:
        all_series.update(series)
        all_audits.update(audits)
        all_raw_records.update(raw_records)
        all_errors.update(errors)
    return all_series, all_audits, all_raw_records, all_errors


def raw_records_to_db_rows(
    raw_records_by_tag: dict[str, list[dict[str, Any]]],
    *,
    source_interval_seconds: int,
    source_server: str,
    read_start: datetime,
    read_end: datetime,
    collected_at: datetime,
) -> list[tuple[Any, ...]]:
    """Convert deduplicated raw records to pg_store upsert tuples."""
    rows: list[tuple[Any, ...]] = []
    for tag, records in raw_records_by_tag.items():
        for record in records:
            rows.append(
                (
                    tag,
                    record["ts"],
                    record.get("value"),
                    record.get("quality", ""),
                    None,
                    source_interval_seconds,
                    source_server,
                    read_start,
                    read_end,
                    collected_at,
                )
            )
    return rows
