"""Verify that the QA short-window list is backed by latest PostgreSQL queues.

REQ-20260517-QA-SHORT-WINDOW-REALTIME

The check compares the newest row in bf_sensor.diagnosis_queues with the first
item returned by the 8092 /api/short-window/conversations endpoint.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import Any
from urllib.request import urlopen

import psycopg
from psycopg.rows import dict_row


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="PostgreSQL host")
    parser.add_argument("--port", type=int, default=15432, help="PostgreSQL port")
    parser.add_argument("--database", default="bf_trend", help="PostgreSQL database")
    parser.add_argument("--user", default="gl02_sync", help="PostgreSQL user")
    parser.add_argument("--password", default="gl02_local_sync", help="PostgreSQL password")
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8092", help="8092 API base URL")
    parser.add_argument("--limit", type=int, default=5, help="API list size")
    return parser.parse_args()


def iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    return str(value)


def latest_db_queue(args: argparse.Namespace) -> dict[str, Any]:
    conninfo = (
        f"host={args.host} port={args.port} dbname={args.database} "
        f"user={args.user} password={args.password}"
    )
    with psycopg.connect(conninfo, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT q.queue_id,
                       q.queue_hash,
                       q.queue_start_ts,
                       q.queue_end_ts,
                       q.diagnosis_count,
                       q.expected_count,
                       q.status AS queue_status,
                       s.status AS summary_status,
                       s.updated_at AS summary_updated_at
                FROM bf_sensor.diagnosis_queues q
                LEFT JOIN LATERAL (
                    SELECT status, updated_at
                    FROM bf_sensor.short_window_summaries s
                    WHERE s.queue_id = q.queue_id
                    ORDER BY s.updated_at DESC NULLS LAST, s.created_at DESC NULLS LAST, s.summary_id DESC
                    LIMIT 1
                ) s ON true
                ORDER BY q.queue_end_ts DESC NULLS LAST, q.queue_id DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
    if not row:
        raise RuntimeError("No rows found in bf_sensor.diagnosis_queues")
    return dict(row)


def api_items(args: argparse.Namespace) -> list[dict[str, Any]]:
    url = f"{args.api_base_url.rstrip('/')}/api/short-window/conversations?limit={args.limit}"
    with urlopen(url, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload.get("ok"):
        raise RuntimeError(f"API returned not ok: {payload}")
    items = payload.get("items") or []
    if not items:
        raise RuntimeError("API returned no short-window items")
    return items


def main() -> int:
    args = parse_args()
    db_latest = latest_db_queue(args)
    items = api_items(args)
    first = items[0]
    db_queue_id = str(db_latest["queue_id"])
    api_queue_id = str(first.get("queue_id"))
    ok = db_queue_id == api_queue_id
    result = {
        "ok": ok,
        "db_latest": {
            "queue_id": db_queue_id,
            "queue_end_ts": iso(db_latest.get("queue_end_ts")),
            "diagnosis_count": db_latest.get("diagnosis_count"),
            "expected_count": db_latest.get("expected_count"),
            "queue_status": db_latest.get("queue_status"),
            "summary_status": db_latest.get("summary_status"),
        },
        "api_first": {
            "queue_id": api_queue_id,
            "queue_end": first.get("queue_end"),
            "diagnosis_count": first.get("diagnosis_count"),
            "expected_count": first.get("expected_count"),
            "queue_status": first.get("queue_status"),
            "summary_status": first.get("summary_status"),
            "source_type": first.get("source_type"),
            "message_count": first.get("message_count"),
        },
        "api_count": len(items),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
