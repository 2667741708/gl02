# -*- coding: utf-8 -*-
"""Sync the 2# blast-furnace Raqsoft operation-log report into bf_imes.

This is a separate read-only source adapter because the report uses a
two-stage HTML POST flow rather than the normal IMES ``*Data.do`` JSON API.
The destination write is an idempotent upsert into ``bf_imes.raw_rows`` plus
the generated ``imes_bf2_operation_log_report`` wide table.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from imes_pg_store import connect, ensure_schema, finish_run, register_datasets, start_run, summary, upsert_payload  # noqa: E402
from imes_report_client import REPORT_DATASET, RaqsoftReportClient  # noqa: E402


def dates_inclusive(start: date, end: date) -> list[date]:
    if end < start:
        raise ValueError("--end-date 不能早于 --start-date")
    result: list[date] = []
    current = start
    while current <= end:
        result.append(current)
        current += timedelta(days=1)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="同步 2# 高炉冀南新区高炉作业日志报表到 bf_imes。")
    parser.add_argument("--date", default="", help="单日日期 YYYY-MM-DD；默认今天。")
    parser.add_argument("--start-date", default="", help="历史起始日期 YYYY-MM-DD。")
    parser.add_argument("--end-date", default="", help="历史结束日期 YYYY-MM-DD。")
    parser.add_argument("--report-base-url", default="", help="报表代理地址，默认 IMES_REPORT_BASE_URL 或 http://127.0.0.1:18084/")
    parser.add_argument("--prodcentercode", default="2D012")
    parser.add_argument("--max-rows", type=int, default=0, help="每天最多保存行数；0 表示不限制。")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--dry-run", action="store_true", help="只查询解析，不写 PostgreSQL。")
    return parser


def resolve_dates(args: argparse.Namespace) -> list[date]:
    today = date.today()
    if args.start_date or args.end_date:
        start = datetime.strptime(args.start_date or args.date or today.isoformat(), "%Y-%m-%d").date()
        end = datetime.strptime(args.end_date or args.start_date or args.date or today.isoformat(), "%Y-%m-%d").date()
        return dates_inclusive(start, end)
    return [datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else today]


def main() -> int:
    args = build_parser().parse_args()
    base_url = args.report_base_url or os.environ.get("IMES_REPORT_BASE_URL") or "http://127.0.0.1:18084/"
    client = RaqsoftReportClient(base_url, timeout=args.timeout)
    dates = resolve_dates(args)
    if args.dry_run:
        outputs = []
        for workdate in dates:
            payload = client.fetch_operation_log(workdate, prodcentercode=args.prodcentercode, max_rows=args.max_rows)
            outputs.append({"date": workdate.isoformat(), "rows_count": payload["rows_count"], "sample": payload["rows"][:1]})
        print(json.dumps({"ok": True, "dry_run": True, "base_url": base_url, "outputs": outputs}, ensure_ascii=False, default=str))
        return 0

    conn = connect()
    try:
        ensure_schema(conn)
        register_datasets(conn, [REPORT_DATASET])
        outputs = []
        for workdate in dates:
            run_id = start_run(conn, REPORT_DATASET, "imes_report_readonly_web", workdate, {"prodcentercode": args.prodcentercode})
            try:
                payload = client.fetch_operation_log(workdate, prodcentercode=args.prodcentercode, max_rows=args.max_rows)
                written = upsert_payload(conn, REPORT_DATASET, payload, workdate)
                finish_run(conn, run_id, payload["rows_count"], written, payload.get("total"))
                outputs.append({"date": workdate.isoformat(), "rows_read": payload["rows_count"], "rows_written": written})
            except Exception as exc:  # noqa: BLE001
                conn.rollback()
                finish_run(conn, run_id, 0, 0, None, str(exc))
                outputs.append({"date": workdate.isoformat(), "rows_read": 0, "rows_written": 0, "error": str(exc)})
        print(json.dumps({"ok": True, "outputs": outputs, "summary": summary(conn)}, ensure_ascii=False, default=str))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
