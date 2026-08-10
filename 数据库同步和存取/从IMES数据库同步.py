# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from imes_pg_store import (
    connect,
    ensure_schema,
    extract_row_workdate,
    finish_run,
    register_datasets,
    start_run,
    summary,
    upsert_payload,
)
from imes_readonly_client import (
    DEFAULT_BASE_URL,
    DEFAULT_ENV_FILE,
    DEFAULT_EXPORT_DIR,
    DYNAMIC_PAGE_GROUPS,
    IMESReadOnlyClient,
    DatasetDef,
    json_dumps,
    load_env_file,
    output_fetch_result,
    resolve_datasets,
)
from imes_report_client import RaqsoftReportClient


def parse_date(value: str | None) -> date:
    if not value:
        return datetime.now().date()
    return datetime.strptime(value, "%Y-%m-%d").date()


def iter_dates(start: date, end: date) -> list[date]:
    if end < start:
        raise ValueError("--end-date 不能早于 --start-date")
    days: list[date] = []
    cursor = start
    while cursor <= end:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


def get_sensor_pg_range(conn) -> dict[str, Any]:
    """Return the GL02 PostgreSQL sensor range that IMES must align to."""
    try:
        row = conn.execute(
            """
            SELECT MIN(ts)::date AS min_date,
                   MAX(ts)::date AS max_date,
                   MIN(ts) AS min_ts,
                   MAX(ts) AS max_ts
            FROM bf_sensor.one_minute_values
            """
        ).fetchone()
    except Exception:
        conn.rollback()
        return {
            "min_date": None,
            "max_date": None,
            "min_ts": None,
            "max_ts": None,
            "source": "bf_sensor.one_minute_values 未可用，未启用自动对齐",
        }
    return {
        "min_date": row["min_date"] if row else None,
        "max_date": row["max_date"] if row else None,
        "min_ts": row["min_ts"] if row else None,
        "max_ts": row["max_ts"] if row else None,
        "source": "bf_sensor.one_minute_values",
    }


def apply_sensor_range_to_dates(dates: list[date], sensor_range: dict[str, Any]) -> list[date]:
    lower = sensor_range.get("min_date")
    upper = sensor_range.get("max_date")
    filtered: list[date] = []
    for item in dates:
        if lower and item < lower:
            continue
        if upper and item > upper:
            continue
        filtered.append(item)
    return filtered


def filter_payload_rows_by_sensor_range(
    payload: dict[str, Any],
    workdate: date,
    sensor_range: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    lower = sensor_range.get("min_date")
    upper = sensor_range.get("max_date")
    if not lower and not upper:
        return payload, 0
    rows = payload.get("rows", [])
    kept: list[dict[str, Any]] = []
    skipped = 0
    for raw in rows:
        row_date = extract_row_workdate(raw, workdate)
        if row_date and lower and row_date < lower:
            skipped += 1
            continue
        if row_date and upper and row_date > upper:
            skipped += 1
            continue
        kept.append(raw)
    if skipped == 0:
        return payload, 0
    filtered = dict(payload)
    filtered["rows"] = kept
    filtered["rows_count"] = len(kept)
    filtered["filtered_out_of_sensor_range"] = skipped
    return filtered, skipped


def get_credentials(args: argparse.Namespace, require_credentials: bool = True) -> tuple[str, str, str]:
    import os

    base_url = args.base_url or os.environ.get("IMES_BASE_URL") or DEFAULT_BASE_URL
    username = args.username or os.environ.get("IMES_USERNAME") or ""
    password = args.password or os.environ.get("IMES_PASSWORD") or ""
    if require_credentials and (not username or not password):
        raise ValueError("请设置 IMES_USERNAME 和 IMES_PASSWORD，或使用本机 .env.imes.local。")
    return base_url, username, password


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="从 IMES Web 只读接口同步数据到 220.12 PostgreSQL。")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE), help="本机私有 env 文件，默认 .env.imes.local")
    parser.add_argument("--base-url", default="", help="IMES base URL；默认读取 IMES_BASE_URL 或内置地址")
    parser.add_argument("--report-base-url", default="", help="Raqsoft 报表代理地址；默认读取 IMES_REPORT_BASE_URL 或 http://127.0.0.1:18084/")
    parser.add_argument("--username", default="", help="IMES 用户名；默认读取 IMES_USERNAME")
    parser.add_argument("--password", default="", help="IMES 密码；默认读取 IMES_PASSWORD，不建议命令行明文传入")
    parser.add_argument("--dataset", default="bf2_batch_input_detail", help="数据集 key；10页面全量使用 imes_10_pages。")
    parser.add_argument("--date", default="", help="单日同步日期，格式 YYYY-MM-DD；默认今天。")
    parser.add_argument("--start-date", default="", help="历史同步起始日期，格式 YYYY-MM-DD。")
    parser.add_argument("--end-date", default="", help="历史同步结束日期，格式 YYYY-MM-DD。")
    parser.add_argument("--lot", default="", help="批次筛选，可为空。")
    parser.add_argument("--prod-center-code", default="", help="覆盖 prodCenterCode，默认使用数据集定义。")
    parser.add_argument("--page-size", type=int, default=200)
    parser.add_argument("--max-rows", type=int, default=0, help="每个数据集每一天最多读取行数，0 表示不限制。")
    parser.add_argument("--delay-seconds", type=float, default=0.05)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--save-files", action="store_true", help="同时保存 JSON/CSV 快照到 imes_exports。")
    parser.add_argument("--out-dir", default=str(DEFAULT_EXPORT_DIR))
    parser.add_argument("--continuous", action="store_true", help="持续循环同步；默认只执行一次。")
    parser.add_argument("--poll-seconds", type=int, default=300, help="持续模式轮询间隔。")
    parser.add_argument("--stop-on-error", action="store_true", help="任一数据集失败时立即停止；默认记录错误后继续同步其它接口。")
    return parser


def resolve_date_window(args: argparse.Namespace) -> list[date]:
    if args.start_date or args.end_date:
        start = parse_date(args.start_date or args.date)
        end = parse_date(args.end_date or args.start_date or args.date)
        return iter_dates(start, end)
    return [parse_date(args.date)]


def with_date_overrides(params: dict[str, str], workdate: date, lot: str) -> dict[str, str]:
    values = dict(params)
    day = workdate.isoformat()
    next_day = (workdate + timedelta(days=1)).isoformat()
    if "workdate" in values:
        values["workdate"] = day
    if "workDate1" in values:
        values["workDate1"] = day
    if "ironDate" in values:
        values["ironDate"] = day
    if "lot" in values:
        values["lot"] = lot
    if "startDate" in values and "endDate" in values and (values.get("startDate") or values.get("endDate")):
        has_time = ":" in values.get("startDate", "") or ":" in values.get("endDate", "")
        if has_time:
            values["startDate"] = f"{day} 00:00:00"
            values["endDate"] = f"{next_day} 00:00:00"
        else:
            values["startDate"] = day
            values["endDate"] = next_day
    if "dayStartTime" in values:
        values["dayStartTime"] = f"{day} 00:00:00"
    if "dayEndTime" in values:
        values["dayEndTime"] = f"{next_day} 00:00:00"
    return values


def resolve_sync_datasets(args: argparse.Namespace, client: IMESReadOnlyClient) -> list[DatasetDef]:
    if args.dataset in DYNAMIC_PAGE_GROUPS:
        return client.discover_known_page_datasets()
    return resolve_datasets(args.dataset)


def sync_once(args: argparse.Namespace) -> dict[str, Any]:
    load_env_file(Path(args.env_file))
    dates = resolve_date_window(args)
    preliminary = resolve_datasets(args.dataset) if args.dataset not in DYNAMIC_PAGE_GROUPS else []
    datasets = preliminary
    if not datasets:
        # Dynamic page discovery needs a real IMES login before the final
        # dataset list can be known.
        base_url, username, password = get_credentials(args, require_credentials=True)
        discovery_client = IMESReadOnlyClient(base_url=base_url, username=username, password=password, timeout=args.timeout)
        datasets = resolve_sync_datasets(args, discovery_client)
    requires_web_credentials = any(dataset.key != "bf2_operation_log_report" for dataset in datasets)
    base_url, username, password = get_credentials(args, require_credentials=requires_web_credentials)
    client = IMESReadOnlyClient(base_url=base_url, username=username, password=password, timeout=args.timeout)
    report_base_url = args.report_base_url or os.environ.get("IMES_REPORT_BASE_URL") or "http://127.0.0.1:18084/"
    report_client = RaqsoftReportClient(report_base_url, timeout=args.timeout)
    conn = connect()
    ensure_schema(conn)
    sensor_range = get_sensor_pg_range(conn)
    requested_dates = dates
    dates = apply_sensor_range_to_dates(requested_dates, sensor_range)
    register_datasets(conn, datasets)

    outputs: list[dict[str, Any]] = []
    try:
        if not dates:
            return {
                "ok": True,
                "outputs": [],
                "summary": summary(conn),
                "requested_dates": [item.isoformat() for item in requested_dates],
                "effective_dates": [],
                "sensor_pg_range": {
                    "min_date": str(sensor_range.get("min_date")) if sensor_range.get("min_date") else None,
                    "max_date": str(sensor_range.get("max_date")) if sensor_range.get("max_date") else None,
                    "min_ts": str(sensor_range.get("min_ts")) if sensor_range.get("min_ts") else None,
                    "max_ts": str(sensor_range.get("max_ts")) if sensor_range.get("max_ts") else None,
                    "source": sensor_range.get("source"),
                },
                "note": "请求日期不在 GL02 PostgreSQL 现有时间范围内，已跳过 IMES 读取。",
            }
        for workdate in dates:
            for dataset in datasets:
                params = with_date_overrides(dataset.default_params, workdate, args.lot)
                if args.prod_center_code and "prodCenterCode" in params:
                    params["prodCenterCode"] = args.prod_center_code
                run_id = start_run(conn, dataset, "imes_readonly_web", workdate, params)
                try:
                    if dataset.key == "bf2_operation_log_report":
                        payload = report_client.fetch_operation_log(
                            workdate,
                            prodcentercode=params.get("prodcentercode", "2D012"),
                            max_rows=args.max_rows,
                        )
                    else:
                        payload = client.fetch_bootstrap_table(
                            dataset,
                            params=params,
                            page_size=args.page_size,
                            max_rows=args.max_rows,
                            delay_seconds=args.delay_seconds,
                        )
                    source_rows_read = int(payload.get("rows_count") or 0)
                    payload, skipped_out_of_range = filter_payload_rows_by_sensor_range(payload, workdate, sensor_range)
                    rows_written = upsert_payload(conn, dataset, payload, workdate)
                    finish_run(
                        conn,
                        run_id,
                        rows_read=int(payload.get("rows_count") or 0),
                        rows_written=rows_written,
                        total=payload.get("total"),
                    )
                    saved = {}
                    if args.save_files:
                        saved = output_fetch_result(
                            payload,
                            dataset,
                            Path(args.out_dir),
                            {"json", "csv"},
                            Path(args.out_dir) / "unused.sqlite",
                        )
                    outputs.append(
                        {
                            "date": workdate.isoformat(),
                            "dataset": dataset.key,
                            "source_rows_read": source_rows_read,
                            "rows_read": int(payload.get("rows_count") or 0),
                            "rows_written": rows_written,
                            "total": payload.get("total"),
                            "filtered_out_of_sensor_range": skipped_out_of_range,
                            "saved": saved,
                        }
                    )
                except Exception as exc:
                    finish_run(conn, run_id, rows_read=0, rows_written=0, total=None, error=str(exc))
                    outputs.append(
                        {
                            "date": workdate.isoformat(),
                            "dataset": dataset.key,
                            "rows_read": 0,
                            "rows_written": 0,
                            "total": None,
                            "error": str(exc),
                        }
                    )
                    if args.stop_on_error:
                        raise
        return {
            "ok": True,
            "outputs": outputs,
            "summary": summary(conn),
            "requested_dates": [item.isoformat() for item in requested_dates],
            "effective_dates": [item.isoformat() for item in dates],
            "sensor_pg_range": {
                "min_date": str(sensor_range.get("min_date")) if sensor_range.get("min_date") else None,
                "max_date": str(sensor_range.get("max_date")) if sensor_range.get("max_date") else None,
                "min_ts": str(sensor_range.get("min_ts")) if sensor_range.get("min_ts") else None,
                "max_ts": str(sensor_range.get("max_ts")) if sensor_range.get("max_ts") else None,
                "source": sensor_range.get("source"),
            },
        }
    finally:
        conn.close()


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        while True:
            result = sync_once(args)
            print(json_dumps(result), flush=True)
            if not args.continuous:
                return 0
            time.sleep(max(10, int(args.poll_seconds)))
    except KeyboardInterrupt:
        print(json.dumps({"ok": False, "error": "interrupted"}, ensure_ascii=False), file=sys.stderr)
        return 130
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
