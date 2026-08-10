"""Synchronize IMES heat facts into PostgreSQL one row per official meltno."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import re
import sys
import time
from typing import Any

from psycopg import OperationalError


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "db_dashboard"))
sys.path.insert(0, str(ROOT / "高炉前端数据" / "智能助手" / "backend"))

import heat_service  # noqa: E402
from heat_performance_quality import (  # noqa: E402
    HeatPerformanceQualityStore,
    build_summary_row,
)
try:  # Older standalone bundles can still run the local-mirror-only path.
    from heat_performance_quality import build_gap_audit  # type: ignore  # noqa: E402
except ImportError:  # pragma: no cover - exercised by the remote compatibility bundle.
    build_gap_audit = None


def run_db_with_retry(operation, *, label: str, max_attempts: int = 5):
    """Retry transient PostgreSQL connectivity failures without hiding data errors."""
    for attempt in range(1, max_attempts + 1):
        try:
            return operation()
        except OperationalError as exc:
            if attempt >= max_attempts:
                raise
            delay_seconds = min(8, 2 ** (attempt - 1))
            print(json.dumps({
                "event": "postgres_retry",
                "label": label,
                "attempt": attempt,
                "next_attempt": attempt + 1,
                "delay_seconds": delay_seconds,
                "error_type": type(exc).__name__,
            }, ensure_ascii=False), flush=True)
            time.sleep(delay_seconds)


def fetch_batches(*, since: datetime | None, batch_size: int, max_heats: int | None):
    cursor = datetime.now() + timedelta(minutes=5)
    emitted = 0
    while True:
        rows = heat_service._fetch_heat_rows(
            limit=batch_size,
            furnace_no="2",
            date_from=since,
            max_open_time=cursor,
        )
        if not rows:
            return
        heat_service._attach_outputs(rows)
        hot_rows, slag_rows = heat_service._fetch_lab_rows_for_heats(rows)
        heat_service._attach_lab_samples(rows, hot_rows, slag_rows)
        if max_heats is not None:
            rows = rows[: max(0, max_heats - emitted)]
        if rows:
            yield rows
            emitted += len(rows)
        if len(rows) < batch_size or (max_heats is not None and emitted >= max_heats):
            return
        oldest = min(row["open_ts"] for row in rows if row.get("open_ts"))
        cursor = oldest - timedelta(microseconds=1)
        if since and cursor < since:
            return


def _date_from_value(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None or value == "":
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def _date_from_meltno(value: Any) -> date | None:
    match = re.search(r"#(\d{8})-", str(value or ""))
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%d").date()
    except ValueError:
        return None


def _repair_times_from_workdate(row: dict[str, Any]) -> tuple[datetime | None, datetime | None, list[str]]:
    """Infer real open/close datetimes from MES workdate plus time-of-day fields."""
    work_date = _date_from_value(row.get("workdate"))
    meltno_date = _date_from_meltno(row.get("meltno"))
    raw_open = heat_service.parse_datetime(row.get("opentime"))
    raw_close = heat_service.parse_datetime(row.get("closetime"))
    reasons: list[str] = []
    if not work_date or not raw_open:
        return raw_open, raw_close, reasons
    if meltno_date and meltno_date != work_date:
        reasons.append("meltno_workdate_date_mismatch")
    elif meltno_date is None:
        reasons.append("meltno_date_unavailable")

    repaired_open = datetime.combine(work_date, raw_open.time())
    if raw_open.date() != work_date:
        reasons.append("opentime_date_rebased_to_workdate")

    repaired_close = None
    if raw_close:
        close_date = work_date
        if raw_close.time() < raw_open.time():
            close_date = work_date + timedelta(days=1)
            reasons.append("closetime_rollover_next_day")
        elif raw_close.date() != work_date:
            reasons.append("closetime_date_rebased_to_workdate")
        repaired_close = datetime.combine(close_date, raw_close.time())

    original_duration = heat_service.number(row.get("tappingtime"))
    if raw_close and raw_open and raw_close < raw_open:
        reasons.append("raw_closetime_before_opentime")
    if original_duration is not None and original_duration < 0:
        reasons.append("negative_tappingtime")
    if repaired_open > datetime.now() + timedelta(minutes=5):
        reasons.append("raw_or_repaired_opentime_future")
    return repaired_open, repaired_close, reasons


def _repair_related_timestamp(value: Any, open_ts: datetime | None) -> datetime | Any:
    parsed = heat_service.parse_datetime(value)
    if not parsed or not open_ts:
        return value
    repaired_date = open_ts.date()
    if parsed.time() < open_ts.time():
        repaired_date = repaired_date + timedelta(days=1)
    return datetime.combine(repaired_date, parsed.time())


def build_local_mirror_recovery_heat(row: dict[str, Any]) -> dict[str, Any] | None:
    """Build a conservative heat fact from the 220.12-local IMES mirror.

    The mirrored lab row is already the MES per-heat arithmetic mean, so it is
    represented as one aggregate sample and is never described as an original
    ladle sample. Placeholder future heats without ``openTime`` remain
    candidates and are not inserted into the fact table.
    """

    output = dict(row.get("output_json") or {})
    lab = dict(row.get("lab_json") or {})
    meltno = str(row.get("meltno") or output.get("meltNo") or "").strip()
    if not meltno:
        return None
    repaired_open, repaired_close, reasons = _repair_times_from_workdate({
        "meltno": meltno,
        "workdate": output.get("workDate") or row.get("work_date"),
        "opentime": output.get("openTime"),
        "closetime": output.get("closeTime"),
        "tappingtime": output.get("tappingTime"),
    })
    if repaired_open is None:
        return None
    mirrored_at = row.get("mirrored_at")
    sample_values = {
        "C": lab.get("value_01"),
        "Si": lab.get("value_02"),
        "Mn": lab.get("value_03"),
        "P": lab.get("value_04"),
        "S": lab.get("value_05"),
    }
    has_chemistry = any(value not in (None, "") for value in sample_values.values())
    samples = []
    if has_chemistry:
        samples.append({
            **sample_values,
            "result_ts": mirrored_at,
            "source": "bf_imes.raw_rows:heat_average",
            "sample_kind": "per_heat_average_not_original_sample",
        })
    duration = heat_service.number(output.get("tappingTime"))
    if duration is None and repaired_close:
        duration = (repaired_close - repaired_open).total_seconds() / 60.0
    future_pending = bool(
        repaired_open > datetime.now() + timedelta(minutes=5)
        or "meltno_workdate_date_mismatch" in reasons
    )
    return {
        "meltno": meltno,
        "workdate": output.get("workDate") or row.get("work_date"),
        "open_ts": repaired_open,
        "close_ts": repaired_close,
        "raw_open_ts": heat_service.parse_datetime(output.get("openTime")),
        "raw_close_ts": heat_service.parse_datetime(output.get("closeTime")),
        "repaired_open_ts": repaired_open if reasons else None,
        "repaired_close_ts": repaired_close if reasons else None,
        "duration_minutes": duration,
        "batch_count": output.get("sumBatch"),
        "work_class": output.get("workClass"),
        "hot_metal_samples": samples,
        "outputs": [],
        "output_count": 0,
        "alignment_status": (
            "future_pending" if future_pending
            else "time_anomaly_repaired" if reasons
            else "local_imes_mirror_recovered"
        ),
        "time_anomaly_reasons": reasons,
        "repair_checked_at": mirrored_at,
        "future_pending": future_pending,
    }


def fetch_local_mirror_recovery_heats(
    store: HeatPerformanceQualityStore,
    *,
    since_date: date,
    furnace_no: str = "2",
    limit: int = 500,
) -> tuple[list[dict[str, Any]], int]:
    """Read missing completed heats and unopened candidates from local PostgreSQL."""

    limit = max(1, min(int(limit), 5000))
    tomorrow = date.today() + timedelta(days=1)
    with store.connect(read_only=True) as connection:
        available = connection.execute(
            "SELECT to_regclass('bf_imes.raw_rows') AS relation_name"
        ).fetchone()
        if not available or not available["relation_name"]:
            raise RuntimeError("220.12 local IMES mirror bf_imes.raw_rows is unavailable")
        rows = connection.execute(
            """
            WITH output_latest AS (
                SELECT DISTINCT ON (meltno)
                       meltno, work_date, row_json AS output_json, mirrored_at
                  FROM (
                        SELECT COALESCE(row_json->>'meltNo', row_json->>'meltno') AS meltno,
                               COALESCE(workdate, (row_json->>'workDate')::date) AS work_date,
                               row_json,
                               COALESCE(fetched_at, updated_at) AS mirrored_at
                          FROM bf_imes.raw_rows
                         WHERE dataset_key = 'bf2_output_list_cond_data'
                           AND COALESCE(workdate, (row_json->>'workDate')::date) >= %s
                           AND COALESCE(workdate, (row_json->>'workDate')::date) < %s
                           AND COALESCE(row_json->>'meltNo', row_json->>'meltno') LIKE %s
                       ) source
                 WHERE meltno IS NOT NULL
                 ORDER BY meltno, mirrored_at DESC NULLS LAST
            ), lab_latest AS (
                SELECT DISTINCT ON (meltno)
                       meltno, row_json AS lab_json,
                       COALESCE(fetched_at, updated_at) AS lab_mirrored_at
                  FROM (
                        SELECT COALESCE(row_json->>'meltNo', row_json->>'meltno') AS meltno,
                               row_json, fetched_at, updated_at
                          FROM bf_imes.raw_rows
                         WHERE dataset_key = 'bf2_heat_lab_list_cond_data_avg2'
                           AND COALESCE(workdate, (row_json->>'workDate')::date) >= %s
                           AND COALESCE(workdate, (row_json->>'workDate')::date) < %s
                           AND COALESCE(row_json->>'meltNo', row_json->>'meltno') LIKE %s
                       ) source
                 WHERE meltno IS NOT NULL
                 ORDER BY meltno, COALESCE(fetched_at, updated_at) DESC NULLS LAST
            )
            SELECT o.meltno, o.work_date, o.output_json, l.lab_json,
                   GREATEST(o.mirrored_at, l.lab_mirrored_at) AS mirrored_at
              FROM output_latest o
              LEFT JOIN lab_latest l ON l.meltno = o.meltno
              LEFT JOIN bf_assistant.heat_performance_quality_summary h
                     ON h.meltno = o.meltno
             WHERE h.meltno IS NULL
                OR h.si_avg IS NULL
             ORDER BY o.work_date, o.meltno
             LIMIT %s
            """,
            (
                since_date, tomorrow, f"{furnace_no}#%",
                since_date, tomorrow, f"{furnace_no}#%", limit,
            ),
        ).fetchall()
    candidates = 0
    heats: list[dict[str, Any]] = []
    for raw in rows:
        heat = build_local_mirror_recovery_heat(dict(raw))
        if heat is None:
            candidates += 1
            continue
        heats.append(heat)
    return heats, candidates


def fetch_local_mirror_time_repairs(
    store: HeatPerformanceQualityStore,
    *,
    since_date: date,
    furnace_no: str = "2",
    limit: int = 5000,
) -> tuple[list[dict[str, Any]], bool]:
    """Recheck existing summaries against formal meltno + MES workdate.

    Only time-lineage fields are later updated.  Chemistry samples and output
    details already stored in the summary table remain untouched.
    """

    limit = max(1, min(int(limit), 50000))
    tomorrow = date.today() + timedelta(days=1)
    with store.connect(read_only=True) as connection:
        rows = connection.execute(
            """
            WITH output_latest AS (
                SELECT DISTINCT ON (meltno)
                       meltno, work_date, row_json AS output_json,
                       COALESCE(fetched_at, updated_at) AS mirrored_at
                  FROM (
                        SELECT COALESCE(row_json->>'meltNo', row_json->>'meltno') AS meltno,
                               COALESCE(workdate, (row_json->>'workDate')::date) AS work_date,
                               row_json, fetched_at, updated_at
                          FROM bf_imes.raw_rows
                         WHERE dataset_key = 'bf2_output_list_cond_data'
                           AND COALESCE(workdate, (row_json->>'workDate')::date) >= %s
                           AND COALESCE(workdate, (row_json->>'workDate')::date) < %s
                           AND COALESCE(row_json->>'meltNo', row_json->>'meltno') LIKE %s
                       ) source
                 WHERE meltno IS NOT NULL
                 ORDER BY meltno, mirrored_at DESC NULLS LAST
            )
            SELECT o.meltno, o.work_date, o.output_json, o.mirrored_at,
                   h.work_date AS existing_work_date,
                   h.open_ts AS existing_open_ts,
                   h.close_ts AS existing_close_ts
              FROM output_latest o
              JOIN bf_assistant.heat_performance_quality_summary h
                ON h.meltno = o.meltno
             ORDER BY o.work_date, o.meltno
             LIMIT %s
            """,
            (since_date, tomorrow, f"{furnace_no}#%", limit + 1),
        ).fetchall()
    truncated = len(rows) > limit
    repairs: list[dict[str, Any]] = []
    for raw in rows[:limit]:
        heat = build_local_mirror_time_repair(dict(raw))
        if heat is not None:
            repairs.append(heat)
    return repairs, truncated


def build_local_mirror_time_repair(row: dict[str, Any]) -> dict[str, Any] | None:
    """Build a time-only repair when source lineage or stored summary differs."""

    heat = build_local_mirror_recovery_heat(row)
    if heat is None:
        return None
    reasons = list(heat.get("time_anomaly_reasons") or [])
    existing_work_date = _date_from_value(row.get("existing_work_date"))
    existing_open = heat_service.parse_datetime(row.get("existing_open_ts"))
    existing_close = heat_service.parse_datetime(row.get("existing_close_ts"))
    source_work_date = _date_from_value(heat.get("workdate"))
    stored_summary_differs = bool(
        existing_work_date != source_work_date
        or existing_open != heat.get("open_ts")
        or existing_close != heat.get("close_ts")
    )
    if stored_summary_differs:
        reasons.append("summary_time_differs_from_imes_mirror")
    if not reasons:
        return None
    reasons = sorted(set(reasons))
    future_pending = bool(
        heat.get("open_ts") > datetime.now() + timedelta(minutes=5)
        or "meltno_workdate_date_mismatch" in reasons
    )
    heat["alignment_status"] = "future_pending" if future_pending else "time_anomaly_repaired"
    heat["time_anomaly_reasons"] = reasons
    heat["future_pending"] = future_pending
    heat["repaired_open_ts"] = heat.get("open_ts")
    heat["repaired_close_ts"] = heat.get("close_ts")
    return heat


def build_summary_lineage_repair(row: dict[str, Any]) -> dict[str, Any] | None:
    """Rebuild time lineage from an existing summary when mirror rows expired."""

    raw_open = row.get("raw_open_ts") or row.get("open_ts")
    raw_close = row.get("raw_close_ts") or row.get("close_ts")
    repaired_open, repaired_close, reasons = _repair_times_from_workdate({
        "meltno": row.get("meltno"),
        "workdate": row.get("work_date"),
        "opentime": raw_open,
        "closetime": raw_close,
        "tappingtime": row.get("duration_minutes"),
    })
    if not reasons or repaired_open is None:
        return None
    existing_reasons = set(row.get("time_anomaly_reasons") or [])
    desired_reasons = set(reasons)
    future_pending = bool(
        repaired_open > datetime.now() + timedelta(minutes=5)
        or "meltno_workdate_date_mismatch" in desired_reasons
    )
    desired_status = "future_pending" if future_pending else "time_anomaly_repaired"
    already_current = bool(
        heat_service.parse_datetime(row.get("open_ts")) == repaired_open
        and heat_service.parse_datetime(row.get("close_ts")) == repaired_close
        and str(row.get("source_status") or "") == desired_status
        and desired_reasons.issubset(existing_reasons)
        and bool(row.get("future_pending")) == future_pending
    )
    if already_current:
        return None
    duration = row.get("duration_minutes")
    if repaired_close and repaired_close >= repaired_open:
        duration = round((repaired_close - repaired_open).total_seconds() / 60.0, 1)
    return {
        "meltno": row.get("meltno"),
        "workdate": row.get("work_date"),
        "open_ts": repaired_open,
        "close_ts": repaired_close,
        "raw_open_ts": heat_service.parse_datetime(raw_open),
        "raw_close_ts": heat_service.parse_datetime(raw_close),
        "repaired_open_ts": repaired_open,
        "repaired_close_ts": repaired_close,
        "duration_minutes": duration,
        "hot_metal_samples": [],
        "outputs": [],
        "alignment_status": desired_status,
        "time_anomaly_reasons": sorted(desired_reasons),
        "repair_checked_at": datetime.now().astimezone(),
        "future_pending": future_pending,
    }


def fetch_summary_lineage_repairs(
    store: HeatPerformanceQualityStore,
    *,
    since_date: date,
    limit: int = 5000,
) -> tuple[list[dict[str, Any]], bool]:
    """Find existing summaries whose formal heat date/time lineage is stale."""

    limit = max(1, min(int(limit), 50000))
    with store.connect(read_only=True) as connection:
        rows = connection.execute(
            """
            SELECT meltno, work_date, open_ts, close_ts,
                   raw_open_ts, raw_close_ts, duration_minutes,
                   source_status, time_anomaly_reasons, future_pending
              FROM bf_assistant.heat_performance_quality_summary
             WHERE work_date >= %s
               AND work_date < %s
             ORDER BY work_date, meltno
             LIMIT %s
            """,
            (since_date, date.today() + timedelta(days=1), limit + 1),
        ).fetchall()
    truncated = len(rows) > limit
    repairs: list[dict[str, Any]] = []
    for raw in rows[:limit]:
        heat = build_summary_lineage_repair(dict(raw))
        if heat is not None:
            repairs.append(heat)
    return repairs, truncated


def _repair_output_times(heats: list[dict[str, Any]]) -> None:
    for heat in heats:
        if heat.get("alignment_status") not in {"time_anomaly_repaired", "future_pending"}:
            continue
        open_ts = heat.get("open_ts")
        for item in heat.get("outputs") or []:
            item["workdate"] = _repair_related_timestamp(item.get("workdate"), open_ts)
            item["weight_time"] = _repair_related_timestamp(item.get("weight_time"), open_ts)


def fetch_time_anomaly_repair_scan(
    *,
    since_date: date,
    furnace_no: str = "2",
    page_size: int = 200,
    max_rows: int = 5000,
) -> dict[str, Any]:
    """Scan bounded MES workdates and classify every time anomaly."""

    page_size = max(1, min(int(page_size), 500))
    max_rows = max(page_size, min(int(max_rows), 50000))
    tomorrow = date.today() + timedelta(days=1)
    source_rows: list[Any] = []
    offset = 0
    truncated = False
    with heat_service._vastbase_connect(heat_service.imes_ops_params()) as conn:
        future_workdate_filtered = int(conn.execute(
            """
            SELECT count(*) AS n
              FROM public.t_ipes_cond
             WHERE workdate >= %s
               AND (prodcentercode = %s OR meltno LIKE %s)
               AND opentime IS NOT NULL
            """,
            (tomorrow.isoformat(), f"{furnace_no}D012", f"{furnace_no}#%"),
        ).fetchone()["n"] or 0)
        while len(source_rows) < max_rows:
            request_size = min(page_size, max_rows - len(source_rows))
            page = conn.execute(
                """
                SELECT meltno, workdate, prodcentercode, sumbatchstart, sumbatchend,
                       sumbatch, opentime, closetime, tappingtime, theoryquan,
                       slagrate, workshift, workclass
                  FROM public.t_ipes_cond
                 WHERE workdate >= %s
                   AND workdate < %s
                   AND (prodcentercode = %s OR meltno LIKE %s)
                   AND opentime IS NOT NULL
                 ORDER BY workdate DESC, meltno DESC
                 LIMIT %s OFFSET %s
                """,
                (
                    since_date.isoformat(), tomorrow.isoformat(),
                    f"{furnace_no}D012", f"{furnace_no}#%",
                    request_size + 1, offset,
                ),
            ).fetchall()
            source_rows.extend(page[:request_size])
            if len(page) <= request_size:
                break
            offset += request_size
            if len(source_rows) >= max_rows:
                truncated = True
                break

    now_guard = datetime.now() + timedelta(minutes=5)
    checked_at = datetime.now().astimezone()
    anomaly_heats: list[dict[str, Any]] = []
    for raw in source_rows:
        row = dict(raw)
        raw_open = heat_service.parse_datetime(row.get("opentime"))
        raw_close = heat_service.parse_datetime(row.get("closetime"))
        tapping = heat_service.number(row.get("tappingtime"))
        repaired_open, repaired_close, reasons = _repair_times_from_workdate(row)
        has_anomaly = bool(reasons)
        if raw_open and raw_open > now_guard:
            has_anomaly = True
            if "opentime_future_filtered_by_incremental_sync" not in reasons:
                reasons.append("opentime_future_filtered_by_incremental_sync")
        if raw_open and raw_close and raw_close < raw_open:
            has_anomaly = True
        if tapping is not None and tapping < 0:
            has_anomaly = True
        if not has_anomaly:
            continue

        heat = heat_service._normalize_heat(row)
        heat["raw_open_ts"] = raw_open
        heat["raw_close_ts"] = raw_close
        heat["repaired_open_ts"] = repaired_open
        heat["repaired_close_ts"] = repaired_close
        heat["open_ts"] = repaired_open
        heat["close_ts"] = repaired_close
        heat["duration_minutes"] = (
            round((repaired_close - repaired_open).total_seconds() / 60, 1)
            if repaired_open and repaired_close and repaired_close >= repaired_open
            else None
        )
        heat["identity"] = heat_service._heat_identity(str(row.get("meltno") or ""), repaired_open)
        future_pending = bool(
            (repaired_open and repaired_open > now_guard)
            or "meltno_workdate_date_mismatch" in reasons
        )
        heat["alignment_status"] = "future_pending" if future_pending else "time_anomaly_repaired"
        heat["time_anomaly_reasons"] = sorted(set(reasons))
        heat["repair_checked_at"] = checked_at
        heat["future_pending"] = future_pending
        anomaly_heats.append(heat)

    if anomaly_heats:
        heat_service._attach_outputs(anomaly_heats)
        _repair_output_times(anomaly_heats)
        hot_rows, slag_rows = heat_service._fetch_lab_rows_for_heats(anomaly_heats)
        heat_service._attach_lab_samples(anomaly_heats, hot_rows, slag_rows)
    eligible = [
        heat for heat in anomaly_heats
        if heat.get("output_count", 0) > 0 or len(heat.get("hot_metal_samples") or []) > 0
    ]
    return {
        "heats": eligible,
        "anomaly_detected": len(anomaly_heats),
        "evidence_eligible": len(eligible),
        "skipped_no_evidence": len(anomaly_heats) - len(eligible),
        "future_pending": sum(1 for heat in eligible if heat.get("future_pending")),
        "future_workdate_filtered": future_workdate_filtered,
        "scanned": len(source_rows),
        "page_size": page_size,
        "max_rows": max_rows,
        "truncated": truncated,
    }


def fetch_time_anomaly_repairs(*, since_date: date, furnace_no: str = "2") -> list[dict[str, Any]]:
    """Compatibility wrapper returning evidence-eligible anomaly heats."""

    return list(fetch_time_anomaly_repair_scan(
        since_date=since_date,
        furnace_no=furnace_no,
    )["heats"])


def _merge_gap_audit(total: dict[str, Any], item: dict[str, Any], detail_limit: int) -> None:
    """Merge bounded per-batch audit evidence into one final report."""

    for key in (
        "source_present_mirror_missing", "source_field_mirror_empty",
        "summary_missing", "sample_count_changes",
    ):
        values = total.setdefault(key, [])
        values.extend(item.get(key) or [])
        del values[detail_limit:]
    counts = total.setdefault("counts", {})
    for key, value in (item.get("counts") or {}).items():
        counts[key] = int(counts.get(key) or 0) + int(value or 0)
    total["truncated"] = bool(total.get("truncated") or item.get("truncated"))
    total["mirror_audit_available"] = bool(
        total.get("mirror_audit_available") or item.get("mirror_audit_available")
    )
    total["detail_limit"] = detail_limit
    total["target"] = item.get("target")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        choices=("local_mirror", "direct_imes"),
        default="local_mirror",
        help="Default to the IMES data already mirrored in 220.12 PostgreSQL",
    )
    parser.add_argument("--full", action="store_true", help="Backfill all available official heats")
    parser.add_argument("--since-days", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--max-heats", type=int)
    parser.add_argument("--repair-days", type=int, default=3, help="Back-check recent MES workdates for time anomaly repairs")
    parser.add_argument("--repair-page-size", type=int, default=200)
    parser.add_argument("--repair-max-rows", type=int, default=5000)
    parser.add_argument("--audit-detail-limit", type=int, default=100)
    parser.add_argument("--no-repair", action="store_true", help="Disable workdate+meltno repair pass")
    parser.add_argument("--dry-run", action="store_true", help="Read and aggregate sources without PostgreSQL writes")
    args = parser.parse_args()
    since = None if args.full else datetime.now() - timedelta(days=max(1, args.since_days))
    store = HeatPerformanceQualityStore() if (not args.dry_run or args.source == "local_mirror") else None
    if store and not args.dry_run:
        run_db_with_retry(store.ensure_schema, label="ensure_schema")
    if args.source == "local_mirror":
        if store is None:
            raise RuntimeError("local_mirror source requires the 220.12 PostgreSQL store")
        mirror_since = (
            date(2000, 1, 1)
            if args.full
            else (datetime.now() - timedelta(days=max(1, args.since_days))).date()
        )
        heats, pending_candidates = run_db_with_retry(
            lambda: fetch_local_mirror_recovery_heats(
                store,
                since_date=mirror_since,
                limit=args.max_heats or 500,
            ),
            label="read_local_imes_mirror",
        )
        rows = [build_summary_row(heat) for heat in heats]
        written = 0
        if rows and not args.dry_run:
            written = run_db_with_retry(
                lambda: store.upsert_rows(rows),
                label="upsert_local_imes_mirror_recovery",
            )
        repair_rows: list[dict[str, Any]] = []
        repair_truncated = False
        repaired = 0
        if not args.no_repair:
            repair_since = (
                datetime.now() - timedelta(days=max(1, args.repair_days))
            ).date()
            repair_heats, repair_truncated = run_db_with_retry(
                lambda: fetch_local_mirror_time_repairs(
                    store,
                    since_date=repair_since,
                    limit=args.repair_max_rows,
                ),
                label="read_local_imes_mirror_time_repairs",
            )
            summary_repairs, summary_repair_truncated = run_db_with_retry(
                lambda: fetch_summary_lineage_repairs(
                    store,
                    since_date=repair_since,
                    limit=args.repair_max_rows,
                ),
                label="read_summary_time_lineage_repairs",
            )
            repair_truncated = bool(repair_truncated or summary_repair_truncated)
            repairs_by_meltno = {
                str(heat.get("meltno")): heat for heat in summary_repairs
            }
            repairs_by_meltno.update({
                str(heat.get("meltno")): heat for heat in repair_heats
            })
            repair_heats = list(repairs_by_meltno.values())
            repair_rows = [build_summary_row(heat) for heat in repair_heats]
            if repair_rows and not args.dry_run:
                repaired = run_db_with_retry(
                    lambda: store.apply_time_repairs(repair_rows),
                    label="apply_local_imes_mirror_time_repairs",
                )
            for row in repair_rows:
                print(json.dumps({
                    "event": "local_imes_mirror_time_repair",
                    "meltno": row.get("meltno"),
                    "open_ts": row.get("open_ts").isoformat() if row.get("open_ts") else None,
                    "close_ts": row.get("close_ts").isoformat() if row.get("close_ts") else None,
                    "source_status": row.get("source_status"),
                    "reasons": row.get("time_anomaly_reasons") or [],
                }, ensure_ascii=False), flush=True)
        times = [row.get("open_ts") for row in rows if row.get("open_ts")]
        for row in rows:
            print(json.dumps({
                "event": "local_imes_mirror_recovered",
                "meltno": row.get("meltno"),
                "open_ts": row.get("open_ts").isoformat() if row.get("open_ts") else None,
                "si_avg": row.get("si_avg"),
                "source_status": row.get("source_status"),
            }, ensure_ascii=False), flush=True)
        print(json.dumps({
            "ok": True,
            "mode": "full" if args.full else "incremental",
            "source": "22012_local_imes_mirror",
            "dry_run": args.dry_run,
            "mirror_completed_missing": len(rows),
            "synced": written if not args.dry_run else 0,
            "anomaly_detected": len(repair_rows),
            "evidence_eligible": len(repair_rows),
            "repair_prepared": sum(
                1 for row in repair_rows if not row.get("future_pending")
            ),
            "repaired": repaired if not args.dry_run else 0,
            "future_pending": sum(
                1 for row in repair_rows if row.get("future_pending")
            ),
            "repair_truncated": repair_truncated,
            "candidate_heats_without_open_time": pending_candidates,
            "latest_open_ts": max(times).isoformat() if times else None,
            "oldest_open_ts": min(times).isoformat() if times else None,
        }, ensure_ascii=False))
        return 0
    if build_gap_audit is None:
        raise RuntimeError("direct_imes source requires the current heat_performance_quality module")
    synced = 0
    batches = 0
    latest = None
    oldest = None
    audit_limit = max(1, min(args.audit_detail_limit, 1000))
    gap_audit: dict[str, Any] = {"available": not args.dry_run}
    for heats in fetch_batches(
        since=since,
        batch_size=max(1, min(args.batch_size, 200)),
        max_heats=args.max_heats,
    ):
        rows = [build_summary_row(heat) for heat in heats]
        if store:
            existing = run_db_with_retry(
                lambda rows=rows: store.existing_lineage(row["meltno"] for row in rows),
                label=f"audit_batch_{batches + 1}",
            )
            mirror = run_db_with_retry(
                lambda rows=rows: store.existing_mirror_lineage(row["meltno"] for row in rows),
                label=f"audit_mirror_batch_{batches + 1}",
            )
            _merge_gap_audit(
                gap_audit,
                build_gap_audit(rows, existing, mirror=mirror, detail_limit=audit_limit),
                audit_limit,
            )
            run_db_with_retry(
                lambda rows=rows: store.upsert_rows(rows),
                label=f"upsert_batch_{batches + 1}",
            )
        synced += len(rows)
        batches += 1
        times = [row.get("open_ts") for row in rows if row.get("open_ts")]
        if times:
            latest = max([latest, *times] if latest else times)
            oldest = min([oldest, *times] if oldest else times)
        print(json.dumps({"batch": batches, "synced": synced}, ensure_ascii=False), flush=True)
    repaired = 0
    repair_scan: dict[str, Any] = {
        "anomaly_detected": 0, "evidence_eligible": 0,
        "skipped_no_evidence": 0, "future_pending": 0,
        "future_workdate_filtered": 0, "scanned": 0, "truncated": False,
    }
    if not args.no_repair:
        repair_since = (datetime.now() - timedelta(days=max(1, args.repair_days))).date()
        repair_scan = fetch_time_anomaly_repair_scan(
            since_date=repair_since,
            page_size=args.repair_page_size,
            max_rows=args.repair_max_rows,
        )
        repair_heats = list(repair_scan["heats"])
        repair_rows = [build_summary_row(heat) for heat in repair_heats]
        for row, heat in zip(repair_rows, repair_heats):
            details = row.get("output_details") or []
            row["source_status"] = str(heat.get("alignment_status"))
            if isinstance(details, list):
                row["output_details"] = details
            suffix = (
                "；MES时间异常待未来时间核验"
                if heat.get("future_pending")
                else "；MES时间异常已按workdate和时分秒回看修复"
            )
            row["quality_summary"] = row["quality_summary"] + suffix
        if store and repair_rows:
            existing = run_db_with_retry(
                lambda rows=repair_rows: store.existing_lineage(row["meltno"] for row in rows),
                label="audit_time_anomaly_repairs",
            )
            mirror = run_db_with_retry(
                lambda rows=repair_rows: store.existing_mirror_lineage(row["meltno"] for row in rows),
                label="audit_mirror_time_anomaly_repairs",
            )
            _merge_gap_audit(
                gap_audit,
                build_gap_audit(
                    repair_rows, existing, mirror=mirror, detail_limit=audit_limit
                ),
                audit_limit,
            )
            run_db_with_retry(
                lambda rows=repair_rows: store.upsert_rows(rows),
                label="upsert_time_anomaly_repairs",
            )
        prepared_repairs = sum(1 for row in repair_rows if not row.get("future_pending"))
        repaired = prepared_repairs if store else 0
        for heat in repair_heats:
            print(json.dumps({
                "event": "time_anomaly_repair",
                "meltno": heat.get("meltno"),
                "open_ts": heat.get("open_ts").isoformat() if heat.get("open_ts") else None,
                "close_ts": heat.get("close_ts").isoformat() if heat.get("close_ts") else None,
                "reasons": heat.get("time_anomaly_reasons") or [],
                "output_count": heat.get("output_count"),
                "hot_metal_sample_count": len(heat.get("hot_metal_samples") or []),
            }, ensure_ascii=False), flush=True)
    print(json.dumps({
        "ok": True,
        "mode": "full" if args.full else "incremental",
        "dry_run": args.dry_run,
        "synced": synced,
        "batches": batches,
        "anomaly_detected": repair_scan["anomaly_detected"],
        "evidence_eligible": repair_scan["evidence_eligible"],
        "repair_prepared": prepared_repairs if not args.no_repair else 0,
        "repaired": repaired,
        "future_pending": repair_scan["future_pending"],
        "skipped_no_evidence": repair_scan["skipped_no_evidence"],
        "future_workdate_filtered": repair_scan["future_workdate_filtered"],
        "repair_scanned": repair_scan["scanned"],
        "repair_truncated": repair_scan["truncated"],
        "gap_audit": gap_audit,
        "latest_open_ts": latest.isoformat() if latest else None,
        "oldest_open_ts": oldest.isoformat() if oldest else None,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
