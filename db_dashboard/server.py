from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import threading
import time
import zipfile
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from openpyxl import Workbook
import psycopg
from psycopg.rows import dict_row

import heat_service
import external_sources


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = Path(__file__).resolve().parent
REVIEW_BACKEND_DIR = ROOT / "高炉前端数据" / "智能助手" / "backend"
if str(REVIEW_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(REVIEW_BACKEND_DIR))
import diagnosis_review

HOST = os.getenv("BF_DB_DASHBOARD_HOST", "127.0.0.1")
PORT = int(os.getenv("BF_DB_DASHBOARD_PORT", "8890"))
SYNC_INTERVAL_SECONDS = int(os.getenv("BF_DB_DASHBOARD_SYNC_INTERVAL_SECONDS", "300"))

SYNC_STATUS: dict[str, Any] = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "exit_code": None,
    "message": "",
    "tail": [],
}


def pg_params() -> dict[str, Any]:
    file_values = heat_service._credential_values()
    password = os.getenv("GL02_PGPASSWORD") or file_values.get("GL02_PGPASSWORD")
    if not password:
        raise RuntimeError("缺少 GL02 PostgreSQL 只读账号密码配置")
    return {
        "host": os.getenv("GL02_PGHOST") or file_values.get("GL02_PGHOST", "127.0.0.1"),
        "port": int(os.getenv("GL02_PGPORT") or file_values.get("GL02_PGPORT", "15432")),
        "dbname": os.getenv("GL02_PGDATABASE") or file_values.get("GL02_PGDATABASE", "bf_trend"),
        "user": os.getenv("GL02_PGUSER") or file_values.get("GL02_PGUSER", "gl02_sync"),
        "password": password,
        "connect_timeout": int(
            os.getenv("BF_DB_CONNECT_TIMEOUT_SECONDS")
            or file_values.get("BF_DB_CONNECT_TIMEOUT_SECONDS", "2")
        ),
        "options": (
            "-c default_transaction_read_only=on "
            "-c statement_timeout=8000 "
            "-c lock_timeout=2000 "
            "-c idle_in_transaction_session_timeout=10000"
        ),
        "application_name": "standalone_heat_dashboard_8891",
    }


def connect():
    return psycopg.connect(**pg_params(), row_factory=dict_row)


def json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def parse_time(value: str | None, default: datetime) -> datetime:
    if not value:
        return default.replace(second=0, microsecond=0)
    text = value.replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).replace(second=0, microsecond=0)
        except ValueError:
            pass
    return datetime.fromisoformat(text).replace(second=0, microsecond=0)


def csv_param(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def rows_to_csv(rows: list[dict[str, Any]], columns: list[str] | None = None) -> bytes:
    if columns is None:
        columns = sorted({key for row in rows for key in row.keys()}) if rows else ["empty"]
    from io import StringIO

    buf = StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        item = {}
        for key, value in row.items():
            if isinstance(value, (dict, list)):
                item[key] = json.dumps(value, ensure_ascii=False, default=json_default)
            else:
                item[key] = json_default(value) if isinstance(value, datetime) else value
        writer.writerow(item)
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def rows_to_xlsx(rows: list[dict[str, Any]], columns: list[str] | None = None, sheet_name: str = "data") -> bytes:
    if columns is None:
        columns = sorted({key for row in rows for key in row.keys()}) if rows else ["empty"]
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name[:31] or "data"
    ws.append(columns)
    for row in rows:
        values = []
        for column in columns:
            value = row.get(column)
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False, default=json_default)
            elif isinstance(value, (datetime, date)):
                value = json_default(value)
            values.append(value)
        ws.append(values)
    for col in ws.columns:
        letter = col[0].column_letter
        max_len = max(len(str(cell.value)) if cell.value is not None else 0 for cell in col[:200])
        ws.column_dimensions[letter].width = min(max(max_len + 2, 10), 48)
    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()


def parse_date_boundary(value: str | None, *, end_exclusive: bool = False) -> datetime | None:
    if not value:
        return None
    parsed = datetime.strptime(value, "%Y-%m-%d")
    return parsed + timedelta(days=1) if end_exclusive else parsed


def heat_export_zip(
    meltno: str,
    window_kind: str,
    sensor_group: str,
    variables_: list[str],
    pre_tap_minutes: int,
) -> bytes:
    detail = heat_service.heat_detail(
        connect, meltno, window_kind, sensor_group, variables_, pre_tap_minutes
    )
    with connect() as pg_conn:
        minute_rows = heat_service.sensor_window_rows(
            pg_conn,
            detail["heat"],
            window_kind,
            sensor_group,
            variables_,
            pre_tap_minutes,
        )
    diagnosis_rows = detail["diagnosis"].get("items") or []
    recommendations = [
        {
            "diagnosis_ts": row.get("diagnosis_ts"),
            "main_label": row.get("main_label"),
            "main_label_display": row.get("main_label_display"),
            "recommendation_status": row.get("recommendation_status"),
            "recommendation": row.get("recommendation"),
        }
        for row in diagnosis_rows
    ]
    manifest = {
        "schema_version": "heat_dataset_bundle_v1",
        "generated_at": datetime.now(),
        "meltno": meltno,
        "window": detail["sensor_window"],
        "data_availability": detail["data_availability"],
        "alignment_audit": detail["alignment_audit"],
        "sources": detail["sources"],
    }
    heat_master = dict(detail["heat"])
    for nested in (
        "hot_metal_samples",
        "slag_samples",
        "sinter_context",
        "latest_hot_metal",
        "latest_slag",
    ):
        heat_master.pop(nested, None)
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2, default=json_default),
        )
        archive.writestr("heat_master.csv", rows_to_csv([heat_master]))
        archive.writestr(
            "hot_metal_chemistry.csv",
            rows_to_csv(detail["heat"].get("hot_metal_samples") or []),
        )
        archive.writestr(
            "slag_chemistry.csv",
            rows_to_csv(detail["heat"].get("slag_samples") or []),
        )
        archive.writestr(
            "sinter_context.csv",
            rows_to_csv(detail["heat"].get("sinter_context") or []),
        )
        archive.writestr(
            "sensor_window_features.csv",
            rows_to_csv(detail["sensor_window"].get("statistics") or []),
        )
        archive.writestr("sensor_minute_values.csv", rows_to_csv(minute_rows))
        archive.writestr("diagnosis_timeline.csv", rows_to_csv(diagnosis_rows))
        archive.writestr(
            "recommendations.json",
            json.dumps(recommendations, ensure_ascii=False, indent=2, default=json_default),
        )
        archive.writestr(
            "model_feature_row.csv", rows_to_csv([detail["model_feature_row"]])
        )
    return output.getvalue()


def overview() -> dict[str, Any]:
    with connect() as conn:
        sensor = conn.execute(
            """
            WITH table_oids AS (
                SELECT 'bf_sensor.one_minute_values'::regclass::oid AS oid
                UNION ALL
                SELECT inhrelid
                FROM pg_inherits
                WHERE inhparent = 'bf_sensor.one_minute_values'::regclass
            )
            SELECT
                (
                    SELECT COALESCE(sum(GREATEST(c.reltuples, 0)), 0)::bigint
                    FROM table_oids o
                    JOIN pg_class c ON c.oid = o.oid
                ) AS rows,
                (
                    SELECT count(*)
                    FROM bf_sensor.sensor_registry
                    WHERE is_enabled IS TRUE
                      AND COALESCE(is_derived, FALSE) IS FALSE
                ) AS tags,
                (
                    SELECT ts
                    FROM bf_sensor.one_minute_values
                    ORDER BY ts ASC
                    LIMIT 1
                ) AS min_ts,
                (
                    SELECT ts
                    FROM bf_sensor.one_minute_values
                    ORDER BY ts DESC
                    LIMIT 1
                ) AS max_ts,
                TRUE AS rows_is_estimate
            """
        ).fetchone()
        baseline = conn.execute(
            """
            SELECT count(*) AS rows, count(distinct baseline_day) AS days, min(baseline_day) AS min_day, max(baseline_day) AS max_day
            FROM bf_sensor.daily_baselines
            """
        ).fetchone()
        diagnosis = conn.execute(
            """
            SELECT count(*) AS rows, min(diagnosis_ts) AS min_ts, max(diagnosis_ts) AS max_ts
            FROM bf_sensor.diagnosis_snapshots
            """
        ).fetchone()
        latest = conn.execute(
            """
            SELECT diagnosis_ts, main_label, main_score, secondary_label, secondary_score, data_coverage, evidence
            FROM bf_sensor.diagnosis_snapshots
            ORDER BY diagnosis_ts DESC, updated_at DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
        latest_summary = conn.execute(
            """
            SELECT summary_id, queue_id, model_name, status, llm_summary, docx_path, markdown_path, created_at
            FROM bf_sensor.short_window_summaries
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()
        dist = conn.execute(
            """
            SELECT main_label, count(*) AS n,
                   round(count(*) * 100.0 / sum(count(*)) over (), 2) AS pct
            FROM (
                SELECT DISTINCT ON (diagnosis_ts) diagnosis_ts, main_label
                FROM bf_sensor.diagnosis_snapshots
                ORDER BY diagnosis_ts, updated_at DESC, id DESC
            ) latest
            GROUP BY main_label
            ORDER BY n DESC
            """
        ).fetchall()
    return {
        "ok": True,
        "checked_at": datetime.now(),
        "database": {
            "profile": "GL02 PostgreSQL 只读镜像",
            "read_only": True,
        },
        "sensor": dict(sensor or {}),
        "baseline": dict(baseline or {}),
        "diagnosis": dict(diagnosis or {}),
        "latest_diagnosis": dict(latest or {}) if latest else None,
        "latest_summary": dict(latest_summary or {}) if latest_summary else None,
        "diagnosis_distribution": [dict(row) for row in dist],
        "sync": SYNC_STATUS,
    }


def variables() -> dict[str, Any]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT variable_name, chinese_name, branch, short_name, tag_long_name, description, is_derived, is_enabled
            FROM bf_sensor.sensor_registry
            WHERE is_enabled = true
            ORDER BY is_derived ASC, variable_name ASC
            """
        ).fetchall()
    return {"ok": True, "variables": [dict(row) for row in rows]}


def sensor_rows(params: dict[str, list[str]]) -> tuple[list[dict[str, Any]], list[str]]:
    now = datetime.now().replace(second=0, microsecond=0)
    end = parse_time(params.get("end", [""])[0], now)
    start = parse_time(params.get("start", [""])[0], end - timedelta(hours=8))
    requested_vars = csv_param(params.get("variables", [""])[0])
    vars_ = list(requested_vars)
    derive_t_top = "T_top" in vars_
    if derive_t_top:
        for item in ("T_top_A", "T_top_B", "T_top_C", "T_top_D"):
            if item not in vars_:
                vars_.append(item)
    limit = min(int(params.get("limit", ["20000"])[0]), 200000)
    long_format = params.get("shape", ["wide"])[0] == "long"
    with connect() as conn:
        if vars_:
            registry = conn.execute(
                """
                SELECT variable_name, tag_long_name
                FROM bf_sensor.sensor_registry
                WHERE is_enabled = true AND is_derived = false AND variable_name = ANY(%s)
                """,
                (vars_,),
            ).fetchall()
        else:
            registry = conn.execute(
                """
                SELECT variable_name, tag_long_name
                FROM bf_sensor.sensor_registry
                WHERE is_enabled = true AND is_derived = false
                ORDER BY variable_name
                LIMIT 20
                """
            ).fetchall()
        tag_to_var = {row["tag_long_name"]: row["variable_name"] for row in registry}
        if not tag_to_var:
            return [], ["timestamp"]
        rows = conn.execute(
            """
            SELECT tag_long_name, ts, value, quality
            FROM bf_sensor.one_minute_values
            WHERE ts >= %s AND ts <= %s AND tag_long_name = ANY(%s)
            ORDER BY ts ASC, tag_long_name ASC
            LIMIT %s
            """,
            (start, end, list(tag_to_var), limit),
        ).fetchall()
    if long_format:
        out = [
            {
                "timestamp": row["ts"],
                "variable_name": tag_to_var.get(row["tag_long_name"], row["tag_long_name"]),
                "value": row["value"],
                "quality": row["quality"],
            }
            for row in rows
        ]
        return out, ["timestamp", "variable_name", "value", "quality"]
    by_ts: dict[datetime, dict[str, Any]] = {}
    for row in rows:
        item = by_ts.setdefault(row["ts"], {"timestamp": row["ts"]})
        item[tag_to_var.get(row["tag_long_name"], row["tag_long_name"])] = row["value"]
    if derive_t_top:
        for item in by_ts.values():
            values = [item.get(name) for name in ("T_top_A", "T_top_B", "T_top_C", "T_top_D") if item.get(name) is not None]
            item["T_top"] = sum(values) / len(values) if values else None
    columns = ["timestamp"] + (requested_vars if requested_vars else [row["variable_name"] for row in registry])
    return [by_ts[key] for key in sorted(by_ts)], columns


def baseline_rows(params: dict[str, list[str]]) -> tuple[list[dict[str, Any]], list[str]]:
    now = datetime.now()
    end = parse_time(params.get("end", [""])[0], now).date()
    start = parse_time(params.get("start", [""])[0], now - timedelta(days=7)).date()
    vars_ = csv_param(params.get("variables", [""])[0])
    baseline_days = int(params.get("baseline_days", ["30"])[0])
    sql_vars = ""
    values: list[Any] = [start, end, baseline_days]
    if vars_:
        sql_vars = "AND variable_name = ANY(%s)"
        values.append(vars_)
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT baseline_day, variable_name, median_ref, iqr_ref, p10, p50, p90,
                   sample_count, expected_minutes, coverage_ratio
            FROM bf_sensor.daily_baselines
            WHERE baseline_day >= %s AND baseline_day <= %s AND baseline_days = %s
              {sql_vars}
            ORDER BY baseline_day ASC, variable_name ASC
            """,
            values,
        ).fetchall()
    columns = [
        "baseline_day",
        "variable_name",
        "median_ref",
        "iqr_ref",
        "p10",
        "p50",
        "p90",
        "sample_count",
        "expected_minutes",
        "coverage_ratio",
    ]
    return [dict(row) for row in rows], columns


def diagnosis_rows(params: dict[str, list[str]]) -> tuple[list[dict[str, Any]], list[str]]:
    now = datetime.now().replace(second=0, microsecond=0)
    end = parse_time(params.get("end", [""])[0], now)
    start = parse_time(params.get("start", [""])[0], end - timedelta(hours=24))
    labels = csv_param(params.get("labels", [""])[0])
    limit = min(int(params.get("limit", ["5000"])[0]), 100000)
    extra = ""
    values: list[Any] = [start, end]
    if labels:
        extra = "AND main_label = ANY(%s)"
        values.append(labels)
    values.append(limit)
    with connect() as conn:
        rows = conn.execute(
            f"""
            WITH latest AS (
                SELECT DISTINCT ON (diagnosis_ts) *
                FROM bf_sensor.diagnosis_snapshots
                WHERE diagnosis_ts >= %s AND diagnosis_ts <= %s
                ORDER BY diagnosis_ts, updated_at DESC, id DESC
            )
            SELECT diagnosis_ts, main_label, main_score, main_confidence,
                   secondary_label, secondary_score, secondary_confidence,
                   data_coverage, evidence
            FROM latest
            WHERE 1=1
              {extra}
            ORDER BY diagnosis_ts ASC
            LIMIT %s
            """,
            values,
        ).fetchall()
        dist = conn.execute(
            f"""
            WITH latest AS (
                SELECT DISTINCT ON (diagnosis_ts) *
                FROM bf_sensor.diagnosis_snapshots
                WHERE diagnosis_ts >= %s AND diagnosis_ts <= %s
                ORDER BY diagnosis_ts, updated_at DESC, id DESC
            )
            SELECT main_label, count(*) AS n,
                   round(count(*) * 100.0 / sum(count(*)) over (), 2) AS pct
            FROM latest
            WHERE 1=1
              {extra}
            GROUP BY main_label
            ORDER BY n DESC
            """,
            values[:-1],
        ).fetchall()
    out = [dict(row) for row in rows]
    columns = [
        "diagnosis_ts",
        "main_label",
        "main_score",
        "main_confidence",
        "secondary_label",
        "secondary_score",
        "secondary_confidence",
        "data_coverage",
        "evidence",
    ]
    return out, columns + ["__distribution__" + json.dumps([dict(row) for row in dist], ensure_ascii=False, default=json_default)]


def diagnosis_foreman_score_rows(
    params: dict[str, list[str]],
) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    """Join immutable system scores with optional local furnace-leader events."""
    now = datetime.now().replace(second=0, microsecond=0)
    end = parse_time(params.get("end", [""])[0], now)
    start = parse_time(params.get("start", [""])[0], end - timedelta(hours=24))
    labels = [label for label in csv_param(params.get("labels", [""])[0]) if label in diagnosis_review.DIAGNOSIS_KEYS]
    source_mode = (params.get("source", ["live_readonly"])[0] or "live_readonly").strip()
    if source_mode not in {"live_readonly", "local_fixture"}:
        raise ValueError("source 仅允许 live_readonly 或 local_fixture")
    limit = min(int(params.get("limit", ["20000"])[0]), 100000)
    snapshot_limit = max(1, min(20000, (limit + len(diagnosis_review.DIAGNOSIS_KEYS) - 1) // len(diagnosis_review.DIAGNOSIS_KEYS)))

    review_status: dict[str, Any] = {"configured": False, "available": False, "source_mode": source_mode}
    events: list[dict[str, Any]] = []
    try:
        store = diagnosis_review.DiagnosisReviewStore()
        store.ensure_schema()
        events = [
            event
            for event in store.list_human_score_events(start=start, end=end, labels=labels, limit=100000)
            if event.get("snapshot_source") == source_mode
        ]
        review_status = {"configured": True, "available": True, "source_mode": source_mode}
    except Exception as exc:  # noqa: BLE001
        review_status = {
            "configured": False,
            "available": False,
            "source_mode": source_mode,
            "message": str(exc),
        }

    if source_mode == "local_fixture":
        snapshots: list[dict[str, Any]] = []
        seen_snapshots: set[tuple[str, str]] = set()
        for event in events:
            diagnosis_ts = diagnosis_review.normalize_timestamp(event.get("diagnosis_ts"))
            snapshot_key = (str(event.get("diagnosis_snapshot_id") or ""), diagnosis_ts.isoformat())
            if snapshot_key in seen_snapshots:
                continue
            seen_snapshots.add(snapshot_key)
            snapshots.append(
                {
                    "id": event.get("diagnosis_snapshot_id"),
                    "diagnosis_ts": diagnosis_ts,
                    "main_label": event.get("system_main_label"),
                    "main_score": event.get("system_main_score"),
                    "raw_scores": event.get("system_raw_scores"),
                }
            )
            if len(snapshots) >= snapshot_limit:
                break
    else:
        with connect() as conn:
            snapshots = conn.execute(
                """
                WITH latest AS (
                    SELECT DISTINCT ON (diagnosis_ts)
                           id, diagnosis_ts, main_label, main_score, raw_scores, updated_at
                    FROM bf_sensor.diagnosis_snapshots
                    WHERE diagnosis_ts >= %s AND diagnosis_ts <= %s
                    ORDER BY diagnosis_ts, updated_at DESC, id DESC
                )
                SELECT id, diagnosis_ts, main_label, main_score, raw_scores
                FROM latest
                ORDER BY diagnosis_ts DESC
                LIMIT %s
                """,
                (start, end, snapshot_limit),
            ).fetchall()

    latest_by_id: dict[tuple[str, str], dict[str, Any]] = {}
    latest_by_time: dict[tuple[str, str], dict[str, Any]] = {}
    for event in events:
        label = str(event.get("target_label") or "")
        latest_by_id.setdefault((str(event.get("diagnosis_snapshot_id") or ""), label), event)
        try:
            event_time = diagnosis_review.normalize_timestamp(event.get("diagnosis_ts")).isoformat()
            latest_by_time.setdefault((event_time, label), event)
        except Exception:
            pass

    rows: list[dict[str, Any]] = []
    target_labels = labels or list(diagnosis_review.DIAGNOSIS_KEYS)
    for snapshot in snapshots:
        snapshot_id = str(snapshot.get("id") or "")
        diagnosis_ts = diagnosis_review.normalize_timestamp(snapshot.get("diagnosis_ts"))
        diagnosis_iso = diagnosis_ts.isoformat()
        raw_scores = diagnosis_review.normalize_scores(snapshot.get("raw_scores"))
        main_label = str(snapshot.get("main_label") or "normal")
        for label in target_labels:
            event = latest_by_id.get((snapshot_id, label)) or latest_by_time.get((diagnosis_iso, label))
            foreman_score = event.get("human_match_score") if event else None
            suggestion = str(event.get("suggestion") or "") if event else ""
            rows.append(
                {
                    "diagnosis_ts": diagnosis_ts,
                    "diagnosis_snapshot_id": snapshot_id,
                    "snapshot_source": source_mode,
                    "condition_label": label,
                    "condition_display": diagnosis_review.display_label(label),
                    "system_score": raw_scores.get(label, 0.0),
                    "system_main_label": main_label,
                    "system_main_display": diagnosis_review.display_label(main_label),
                    "is_system_main": label == main_label,
                    "foreman_score": foreman_score,
                    "foreman_score_status": "已打分" if foreman_score is not None else "未打分",
                    "suggestion": suggestion,
                    "suggestion_status": "已提交建议" if suggestion else "未提交建议",
                    "reviewer_username": event.get("reviewer_username") if event else None,
                    "reviewer_role": event.get("reviewer_role") if event else None,
                    "scored_at": event.get("created_at") if event else None,
                    "review_mode": event.get("review_mode") if event else None,
                }
            )
            if len(rows) >= limit:
                break
        if len(rows) >= limit:
            break
    columns = [
        "diagnosis_ts", "diagnosis_snapshot_id", "snapshot_source", "condition_label", "condition_display",
        "system_score", "system_main_label", "system_main_display", "is_system_main",
        "foreman_score", "foreman_score_status", "suggestion", "suggestion_status",
        "reviewer_username", "reviewer_role", "scored_at", "review_mode",
    ]
    return rows, columns, review_status


def quality_rows(params: dict[str, list[str]]) -> tuple[list[dict[str, Any]], list[str]]:
    now = datetime.now().replace(second=0, microsecond=0)
    end = parse_time(params.get("end", [""])[0], now)
    start = parse_time(params.get("start", [""])[0], end - timedelta(hours=24))
    kinds = csv_param(params.get("kinds", [""])[0])
    limit = min(int(params.get("limit", ["5000"])[0]), 100000)
    extra = ""
    values: list[Any] = [start, end]
    if kinds:
        extra = "AND window_kind = ANY(%s)"
        values.append(kinds)
    values.append(limit)
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT checked_at, window_kind, window_start, window_end, latest_data_ts,
                   source_lag_seconds, expected_minutes, observed_minutes,
                   coverage_ratio, status, missing_variables, stale_variables, details
            FROM bf_sensor.data_quality_status
            WHERE checked_at >= %s AND checked_at <= %s
              {extra}
            ORDER BY checked_at DESC
            LIMIT %s
            """,
            values,
        ).fetchall()
    columns = [
        "checked_at",
        "window_kind",
        "window_start",
        "window_end",
        "latest_data_ts",
        "source_lag_seconds",
        "expected_minutes",
        "observed_minutes",
        "coverage_ratio",
        "status",
        "missing_variables",
        "stale_variables",
        "details",
    ]
    return [dict(row) for row in rows], columns


def summary_rows(params: dict[str, list[str]]) -> tuple[list[dict[str, Any]], list[str]]:
    now = datetime.now().replace(second=0, microsecond=0)
    end = parse_time(params.get("end", [""])[0], now)
    start = parse_time(params.get("start", [""])[0], end - timedelta(hours=24))
    statuses = csv_param(params.get("statuses", [""])[0])
    limit = min(int(params.get("limit", ["200"])[0]), 5000)
    extra = ""
    values: list[Any] = [start, end]
    if statuses:
        extra = "AND status = ANY(%s)"
        values.append(statuses)
    values.append(limit)
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT created_at, queue_id, model_name, status, llm_summary,
                   docx_path, markdown_path, diagnosis_queue_json
            FROM bf_sensor.short_window_summaries
            WHERE created_at >= %s AND created_at <= %s
              {extra}
            ORDER BY created_at DESC
            LIMIT %s
            """,
            values,
        ).fetchall()
    columns = [
        "created_at",
        "queue_id",
        "model_name",
        "status",
        "llm_summary",
        "docx_path",
        "markdown_path",
        "diagnosis_queue_json",
    ]
    return [dict(row) for row in rows], columns


def run_sync() -> None:
    global SYNC_STATUS
    if SYNC_STATUS.get("running"):
        return
    SYNC_STATUS.update({"running": True, "started_at": datetime.now(), "finished_at": None, "exit_code": None, "message": "", "tail": []})
    cmd = [str(ROOT / ".venv" / "Scripts" / "python.exe"), str(ROOT / "tools" / "sync_22012_pg_to_local.py"), "--batch-size", "10000"]
    try:
        proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip()
            tail = list(SYNC_STATUS.get("tail") or [])
            tail.append(line)
            SYNC_STATUS["tail"] = tail[-40:]
        code = proc.wait()
        SYNC_STATUS.update({"exit_code": code, "message": "ok" if code == 0 else f"exit {code}"})
    except Exception as exc:  # noqa: BLE001
        SYNC_STATUS.update({"exit_code": -1, "message": str(exc)})
    finally:
        SYNC_STATUS.update({"running": False, "finished_at": datetime.now()})


def sync_scheduler() -> None:
    if SYNC_INTERVAL_SECONDS <= 0:
        return
    while True:
        time.sleep(SYNC_INTERVAL_SECONDS)
        if not SYNC_STATUS.get("running"):
            run_sync()


class Handler(BaseHTTPRequestHandler):
    server_version = "BFDBDashboard/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def send_json(self, payload: Any, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False, default=json_default).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_bytes(self, data: bytes, content_type: str, filename: str | None = None) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        try:
            if parsed.path in {"/", "/index.html"}:
                self.send_bytes((STATIC_DIR / "index.html").read_bytes(), "text/html; charset=utf-8")
            elif parsed.path in {"/heat", "/heat.html"}:
                self.send_bytes((STATIC_DIR / "heat.html").read_bytes(), "text/html; charset=utf-8")
            elif parsed.path == "/heat-data-explorer.js":
                self.send_bytes(
                    (STATIC_DIR / "heat_data_explorer.js").read_bytes(),
                    "application/javascript; charset=utf-8",
                )
            elif parsed.path == "/libs/echarts.min.js":
                self.send_bytes((ROOT / "高炉前端数据" / "libs" / "echarts.min.js").read_bytes(), "application/javascript; charset=utf-8")
            elif parsed.path == "/api/data-catalog":
                self.send_json(external_sources.full_catalog())
            elif parsed.path == "/api/data-source-health":
                source = params.get("source", [""])[0].strip()
                if not source:
                    raise ValueError("source is required")
                payload = external_sources.probe_source(source, connect)
                self.send_json(payload, 200 if payload.get("ok") else 503)
            elif parsed.path == "/api/data-query":
                dataset = params.get("dataset", [""])[0].strip()
                if not dataset:
                    raise ValueError("dataset is required")
                payload = external_sources.query_dataset(
                    dataset,
                    pg_connect=connect,
                    start=params.get("start", [""])[0],
                    end=params.get("end", [""])[0],
                    meltno=params.get("meltno", [""])[0].strip() or None,
                    search=params.get("search", [""])[0].strip() or None,
                    variables=csv_param(params.get("variables", [""])[0]),
                    limit=int(params.get("limit", ["200"])[0]),
                    offset=int(params.get("offset", ["0"])[0]),
                    interval_seconds=int(params.get("interval_seconds", ["60"])[0]),
                    aggregate=params.get("aggregate", ["PS_HIS_AVERAGE"])[0],
                )
                fmt = params.get("format", ["json"])[0]
                safe_dataset = "".join(
                    ch if ch.isalnum() or ch in "-_" else "_"
                    for ch in dataset
                )
                if fmt == "csv":
                    self.send_bytes(
                        rows_to_csv(payload["rows"], payload["columns"]),
                        "text/csv; charset=utf-8",
                        f"{safe_dataset}.csv",
                    )
                elif fmt == "xlsx":
                    self.send_bytes(
                        rows_to_xlsx(
                            payload["rows"],
                            payload["columns"],
                            sheet_name=safe_dataset[:31] or "data",
                        ),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        f"{safe_dataset}.xlsx",
                    )
                else:
                    self.send_json(payload)
            elif parsed.path == "/api/overview":
                self.send_json(overview())
            elif parsed.path == "/api/heats":
                limit = min(int(params.get("limit", ["16"])[0]), 200)
                furnace_no = params.get("furnace", ["2"])[0]
                date_from = parse_date_boundary(params.get("date_from", [""])[0])
                date_to_exclusive = parse_date_boundary(
                    params.get("date_to", [""])[0], end_exclusive=True
                )
                include_future = params.get("include_future", ["false"])[0].lower() == "true"
                payload = heat_service.list_heats(
                    limit=limit,
                    furnace_no=furnace_no,
                    date_from=date_from,
                    date_to_exclusive=date_to_exclusive,
                    include_future=include_future,
                )
                fmt = params.get("format", ["json"])[0]
                if fmt == "csv":
                    rows = heat_service.flatten_heats_for_export(payload["heats"])
                    self.send_bytes(rows_to_csv(rows), "text/csv; charset=utf-8", "heat_analysis.csv")
                elif fmt == "xlsx":
                    rows = heat_service.flatten_heats_for_export(payload["heats"])
                    self.send_bytes(
                        rows_to_xlsx(rows, sheet_name="heats"),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        "heat_analysis.xlsx",
                    )
                else:
                    self.send_json(payload)
            elif parsed.path == "/api/heat-detail":
                meltno = params.get("meltno", [""])[0].strip()
                if not meltno:
                    raise ValueError("meltno is required")
                window_kind = params.get("window", ["pre_tap"])[0]
                sensor_group = params.get("group", ["core"])[0]
                variables_ = csv_param(params.get("variables", [""])[0])
                pre_tap_minutes = int(params.get("pre_tap_minutes", ["120"])[0])
                self.send_json(
                    heat_service.heat_detail(
                        connect,
                        meltno=meltno,
                        window_kind=window_kind,
                        sensor_group=sensor_group,
                        variables=variables_,
                        pre_tap_minutes=pre_tap_minutes,
                    )
                )
            elif parsed.path == "/api/heat-export":
                meltno = params.get("meltno", [""])[0].strip()
                if not meltno:
                    raise ValueError("meltno is required")
                window_kind = params.get("window", ["pre_tap"])[0]
                sensor_group = params.get("group", ["all"])[0]
                variables_ = csv_param(params.get("variables", [""])[0])
                pre_tap_minutes = int(params.get("pre_tap_minutes", ["120"])[0])
                safe_name = "".join(
                    ch if ch.isalnum() or ch in "-_" else "_" for ch in meltno
                )
                self.send_bytes(
                    heat_export_zip(
                        meltno,
                        window_kind,
                        sensor_group,
                        variables_,
                        pre_tap_minutes,
                    ),
                    "application/zip",
                    f"heat_dataset_{safe_name}.zip",
                )
            elif parsed.path == "/api/variables":
                self.send_json(variables())
            elif parsed.path == "/api/sensor":
                rows, columns = sensor_rows(params)
                fmt = params.get("format", ["json"])[0]
                if fmt == "csv":
                    self.send_bytes(rows_to_csv(rows, columns), "text/csv; charset=utf-8", "sensor_export.csv")
                elif fmt == "xlsx":
                    self.send_bytes(rows_to_xlsx(rows, columns, "sensor"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "sensor_export.xlsx")
                else:
                    self.send_json({"ok": True, "rows": rows, "columns": columns})
            elif parsed.path == "/api/baselines":
                rows, columns = baseline_rows(params)
                fmt = params.get("format", ["json"])[0]
                if fmt == "csv":
                    self.send_bytes(rows_to_csv(rows, columns), "text/csv; charset=utf-8", "baseline_export.csv")
                elif fmt == "xlsx":
                    self.send_bytes(rows_to_xlsx(rows, columns, "baseline"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "baseline_export.xlsx")
                else:
                    self.send_json({"ok": True, "rows": rows, "columns": columns})
            elif parsed.path == "/api/diagnosis":
                rows, columns = diagnosis_rows(params)
                distribution = []
                if columns and columns[-1].startswith("__distribution__"):
                    distribution = json.loads(columns.pop()[16:])
                fmt = params.get("format", ["json"])[0]
                if fmt == "csv":
                    self.send_bytes(rows_to_csv(rows, columns), "text/csv; charset=utf-8", "diagnosis_export.csv")
                elif fmt == "xlsx":
                    self.send_bytes(rows_to_xlsx(rows, columns, "diagnosis"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "diagnosis_export.xlsx")
                else:
                    self.send_json({"ok": True, "rows": rows, "columns": columns, "distribution": distribution})
            elif parsed.path == "/api/diagnosis-foreman-scores":
                rows, columns, review_status = diagnosis_foreman_score_rows(params)
                fmt = params.get("format", ["json"])[0]
                if fmt == "csv":
                    self.send_bytes(rows_to_csv(rows, columns), "text/csv; charset=utf-8", "diagnosis_foreman_scores.csv")
                elif fmt == "xlsx":
                    self.send_bytes(
                        rows_to_xlsx(rows, columns, "foreman_scores"),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        "diagnosis_foreman_scores.xlsx",
                    )
                else:
                    self.send_json({"ok": True, "rows": rows, "columns": columns, "review_store": review_status})
            elif parsed.path == "/api/quality":
                rows, columns = quality_rows(params)
                fmt = params.get("format", ["json"])[0]
                if fmt == "csv":
                    self.send_bytes(rows_to_csv(rows, columns), "text/csv; charset=utf-8", "quality_export.csv")
                elif fmt == "xlsx":
                    self.send_bytes(rows_to_xlsx(rows, columns, "quality"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "quality_export.xlsx")
                else:
                    self.send_json({"ok": True, "rows": rows, "columns": columns})
            elif parsed.path == "/api/summaries":
                rows, columns = summary_rows(params)
                fmt = params.get("format", ["json"])[0]
                if fmt == "csv":
                    self.send_bytes(rows_to_csv(rows, columns), "text/csv; charset=utf-8", "summary_export.csv")
                elif fmt == "xlsx":
                    self.send_bytes(rows_to_xlsx(rows, columns, "summaries"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "summary_export.xlsx")
                else:
                    self.send_json({"ok": True, "rows": rows, "columns": columns})
            elif parsed.path == "/api/sync/status":
                self.send_json({"ok": True, "sync": SYNC_STATUS})
            else:
                self.send_json({"ok": False, "error": "not found"}, 404)
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error": str(exc)}, 500)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/sync/run":
                if not SYNC_STATUS.get("running"):
                    threading.Thread(target=run_sync, daemon=True).start()
                self.send_json({"ok": True, "sync": SYNC_STATUS})
            elif parsed.path == "/api/imes-web/login":
                length = min(int(self.headers.get("Content-Length", "0") or 0), 4096)
                body = self.rfile.read(length) if length else b"{}"
                payload = json.loads(body.decode("utf-8"))
                captcha = str(payload.get("captcha") or "").strip()
                if not captcha:
                    raise ValueError("captcha is required")
                self.send_json(external_sources.imes_web_login(captcha))
            else:
                self.send_json({"ok": False, "error": "not found"}, 404)
        except Exception as exc:  # noqa: BLE001
            self.send_json({"ok": False, "error": str(exc)}, 500)


def main() -> int:
    if SYNC_INTERVAL_SECONDS > 0:
        threading.Thread(target=sync_scheduler, daemon=True).start()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"DB dashboard: http://{HOST}:{PORT}/", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
