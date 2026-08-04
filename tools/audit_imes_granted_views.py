# -*- coding: utf-8 -*-
"""Audit the five IMES Vastbase views granted to the dedicated read account.

The connection is forced to read-only mode. The report never records the
password and only stores bounded sample summaries instead of full row dumps.

Traceability:
- OPS-IMES-GRANTED-VIEWS-20260716
- docs/question_traceability.md
- PT/imes.md
"""
from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Sequence

import psycopg


DEFAULT_VIEWS = (
    "v_qpes_steel_final",
    "v_qpes_mat_final",
    "v_qpes_inner_batch_insp_final_sample",
    "v_qpes_sinter_machine_sample_insp_final",
    "v_qpes_slag_insoection_final",
)
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")
TEMPORAL_TYPES = {
    "date",
    "timestamp without time zone",
    "timestamp with time zone",
}
TEMPORAL_NAME_TOKENS = ("time", "date", "时间", "日期")
LATEST_COLUMN_PRIORITY = (
    "publishtime",
    "发布时间",
    "businessdate",
    "业务日期",
    "insptime",
    "制样时间",
    "接样时间",
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="只读核查一期 MES Vastbase 已授权视图的权限、字段和数据概况。"
    )
    parser.add_argument(
        "--view",
        action="append",
        dest="views",
        help="待核查视图名，可重复；默认核查截图中的五个视图。",
    )
    parser.add_argument("--sample-limit", type=int, default=50)
    parser.add_argument("--example-limit", type=int, default=5)
    parser.add_argument("--statement-timeout-ms", type=int, default=30000)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("logs/imes_granted_views_audit_20260716.json"),
    )
    return parser.parse_args(argv)


def validate_args(args: argparse.Namespace) -> None:
    if not 1 <= args.sample_limit <= 500:
        raise ValueError("--sample-limit must be between 1 and 500")
    if not 1 <= args.example_limit <= 10:
        raise ValueError("--example-limit must be between 1 and 10")
    if not 1000 <= args.statement_timeout_ms <= 120000:
        raise ValueError("--statement-timeout-ms must be between 1000 and 120000")
    for view in args.views or DEFAULT_VIEWS:
        if not IDENTIFIER_RE.fullmatch(view):
            raise ValueError(f"unsafe view identifier: {view!r}")


def connection_info(args: argparse.Namespace) -> dict[str, Any]:
    required = {
        "IMES_DB_HOST": os.environ.get("IMES_DB_HOST"),
        "IMES_DB_PORT": os.environ.get("IMES_DB_PORT"),
        "IMES_DB_NAME": os.environ.get("IMES_DB_NAME"),
        "IMES_DB_USER": os.environ.get("IMES_DB_USER"),
        "IMES_DB_PASSWORD": os.environ.get("IMES_DB_PASSWORD"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(f"missing environment variables: {', '.join(missing)}")
    return {
        "host": required["IMES_DB_HOST"],
        "port": int(required["IMES_DB_PORT"]),
        "dbname": required["IMES_DB_NAME"],
        "user": required["IMES_DB_USER"],
        "password": required["IMES_DB_PASSWORD"],
        "connect_timeout": 15,
        "options": (
            "-c default_transaction_read_only=on "
            f"-c statement_timeout={args.statement_timeout_ms}"
        ),
    }


def quote_ident(value: str) -> str:
    if not value or "\x00" in value:
        raise ValueError(f"unsafe SQL identifier: {value!r}")
    return '"' + value.replace('"', '""') + '"'


def json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime, time)):
        return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
    if isinstance(value, bytes):
        return f"<bytes:{len(value)}>"
    return str(value)


def bounded_text(value: Any, limit: int = 160) -> Any:
    converted = json_value(value)
    if isinstance(converted, str) and len(converted) > limit:
        return converted[:limit] + "…"
    return converted


def discover_views(cur: Any, requested: Sequence[str]) -> tuple[list[dict[str, Any]], list[str]]:
    cur.execute(
        """
        SELECT table_schema, table_name, table_type
        FROM information_schema.tables
        WHERE lower(table_name) = ANY(%s)
        ORDER BY table_schema, table_name
        """,
        ([name.lower() for name in requested],),
    )
    found = [
        {"schema": row[0], "name": row[1], "table_type": row[2]}
        for row in cur.fetchall()
    ]
    found_names = {item["name"].lower() for item in found}
    missing = [name for name in requested if name.lower() not in found_names]
    return found, missing


def find_similar_views(cur: Any) -> list[str]:
    cur.execute(
        """
        SELECT table_schema || '.' || table_name
        FROM information_schema.tables
        WHERE lower(table_name) LIKE 'v_qpes_%'
        ORDER BY table_schema, table_name
        """
    )
    return [row[0] for row in cur.fetchall()]


def fetch_columns(cur: Any, schema: str, view: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT
            c.ordinal_position,
            c.column_name,
            c.data_type,
            c.udt_name,
            c.is_nullable,
            c.character_maximum_length,
            c.numeric_precision,
            c.numeric_scale,
            pg_catalog.col_description(pc.oid, c.ordinal_position)
        FROM information_schema.columns AS c
        LEFT JOIN pg_catalog.pg_namespace AS pn
          ON pn.nspname = c.table_schema
        LEFT JOIN pg_catalog.pg_class AS pc
          ON pc.relnamespace = pn.oid AND pc.relname = c.table_name
        WHERE c.table_schema = %s AND c.table_name = %s
        ORDER BY c.ordinal_position
        """,
        (schema, view),
    )
    keys = (
        "ordinal_position",
        "name",
        "data_type",
        "udt_name",
        "nullable",
        "character_maximum_length",
        "numeric_precision",
        "numeric_scale",
        "comment",
    )
    return [dict(zip(keys, row)) for row in cur.fetchall()]


def sample_rows(cur: Any, schema: str, view: str, limit: int) -> tuple[list[str], list[tuple[Any, ...]]]:
    qualified = f"{quote_ident(schema)}.{quote_ident(view)}"
    cur.execute(f"SELECT * FROM {qualified} LIMIT %s", (limit,))
    columns = [item.name for item in cur.description]
    return columns, cur.fetchall()


def summarize_samples(
    columns: Sequence[str],
    rows: Iterable[Sequence[Any]],
    example_limit: int,
) -> dict[str, dict[str, Any]]:
    materialized = list(rows)
    result: dict[str, dict[str, Any]] = {}
    for index, column in enumerate(columns):
        values = [row[index] for row in materialized]
        non_null = [value for value in values if value is not None]
        counts = Counter(str(json_value(value)) for value in non_null)
        examples = []
        seen: set[str] = set()
        for value in non_null:
            key = str(json_value(value))
            if key in seen:
                continue
            seen.add(key)
            examples.append(bounded_text(value))
            if len(examples) >= example_limit:
                break
        result[column] = {
            "sample_rows": len(materialized),
            "non_null": len(non_null),
            "nulls": len(values) - len(non_null),
            "distinct_in_sample": len(counts),
            "examples": examples,
        }
    return result


def fetch_row_count(cur: Any, schema: str, view: str) -> dict[str, Any]:
    qualified = f"{quote_ident(schema)}.{quote_ident(view)}"
    try:
        cur.execute(f"SELECT count(*) FROM {qualified}")
        return {"status": "ok", "value": cur.fetchone()[0]}
    except psycopg.Error as exc:
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}


def fetch_population_counts(
    cur: Any,
    schema: str,
    view: str,
    columns: Sequence[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    qualified = f"{quote_ident(schema)}.{quote_ident(view)}"
    expressions = [f"count({quote_ident(column['name'])})" for column in columns]
    try:
        cur.execute(f"SELECT count(*), {', '.join(expressions)} FROM {qualified}")
        values = cur.fetchone()
        total = values[0]
        return {
            column["name"]: {
                "status": "ok",
                "non_null": values[index + 1],
                "nulls": total - values[index + 1],
            }
            for index, column in enumerate(columns)
        }
    except psycopg.Error as exc:
        return {
            column["name"]: {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
            for column in columns
        }


def fetch_temporal_ranges(
    cur: Any,
    schema: str,
    view: str,
    columns: Sequence[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    qualified = f"{quote_ident(schema)}.{quote_ident(view)}"
    result: dict[str, dict[str, Any]] = {}
    candidates = [
        column
        for column in columns
        if column["data_type"] in TEMPORAL_TYPES
        or any(token in column["name"].lower() for token in TEMPORAL_NAME_TOKENS)
    ]
    for column in candidates:
        name = column["name"]
        try:
            cur.execute(
                f"SELECT min({quote_ident(name)}), max({quote_ident(name)}) FROM {qualified}"
            )
            minimum, maximum = cur.fetchone()
            result[name] = {
                "status": "ok",
                "min": json_value(minimum),
                "max": json_value(maximum),
            }
        except psycopg.Error as exc:
            result[name] = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    return result


def fetch_view_definition(cur: Any, schema: str, view: str) -> dict[str, Any]:
    try:
        cur.execute("SELECT pg_get_viewdef(%s::regclass, true)", (f"{schema}.{view}",))
        return {"status": "ok", "sql": cur.fetchone()[0]}
    except psycopg.Error as exc:
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}


def choose_latest_column(columns: Sequence[dict[str, Any]]) -> str | None:
    available = {column["name"].lower(): column["name"] for column in columns}
    for preferred in LATEST_COLUMN_PRIORITY:
        match = available.get(preferred.lower())
        if match:
            return match
    for column in columns:
        if any(token in column["name"].lower() for token in TEMPORAL_NAME_TOKENS):
            return column["name"]
    return None


def fetch_latest_sample_profile(
    cur: Any,
    schema: str,
    view: str,
    columns: Sequence[dict[str, Any]],
    limit: int,
    example_limit: int,
) -> dict[str, Any]:
    order_column = choose_latest_column(columns)
    if not order_column:
        return {"status": "no_temporal_column"}
    qualified = f"{quote_ident(schema)}.{quote_ident(view)}"
    try:
        cur.execute(
            f"SELECT * FROM {qualified} "
            f"ORDER BY {quote_ident(order_column)} DESC NULLS LAST LIMIT %s",
            (limit,),
        )
        names = [item.name for item in cur.description]
        rows = cur.fetchall()
        return {
            "status": "ok",
            "order_column": order_column,
            "sample_row_count": len(rows),
            "profile": summarize_samples(names, rows, example_limit),
        }
    except psycopg.Error as exc:
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}


def audit_view(cur: Any, item: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    schema = item["schema"]
    view = item["name"]
    qualified_text = f"{schema}.{view}"
    cur.execute("SELECT has_table_privilege(current_user, %s, 'SELECT')", (qualified_text,))
    can_select = bool(cur.fetchone()[0])
    result = dict(item)
    result["qualified_name"] = qualified_text
    result["has_select"] = can_select
    result["columns"] = fetch_columns(cur, schema, view)
    if not can_select:
        result["sample_status"] = "not_authorized"
        return result

    sample_columns, rows = sample_rows(cur, schema, view, args.sample_limit)
    result["sample_status"] = "ok"
    result["sample_row_count"] = len(rows)
    result["sample_profile"] = summarize_samples(sample_columns, rows, args.example_limit)
    result["row_count"] = fetch_row_count(cur, schema, view)
    result["population_profile"] = fetch_population_counts(
        cur, schema, view, result["columns"]
    )
    result["temporal_ranges"] = fetch_temporal_ranges(
        cur, schema, view, result["columns"]
    )
    result["latest_sample"] = fetch_latest_sample_profile(
        cur,
        schema,
        view,
        result["columns"],
        args.sample_limit,
        args.example_limit,
    )
    result["view_definition"] = fetch_view_definition(cur, schema, view)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    args.views = args.views or list(DEFAULT_VIEWS)
    validate_args(args)
    info = connection_info(args)
    safe_source = f"{info['host']}:{info['port']}/{info['dbname']}"

    report: dict[str, Any] = {
        "audit_id": "OPS-IMES-GRANTED-VIEWS-20260716",
        "generated_at": datetime.now().astimezone().isoformat(),
        "source": safe_source,
        "requested_views": args.views,
        "read_only": True,
        "sample_limit": args.sample_limit,
        "statement_timeout_ms": args.statement_timeout_ms,
        "password_recorded": False,
    }

    with psycopg.connect(**info) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "SELECT current_user, current_database(), version(), current_setting('transaction_read_only')"
            )
            user, database, version, read_only = cur.fetchone()
            report["session"] = {
                "current_user": user,
                "current_database": database,
                "server_version": str(version).splitlines()[0],
                "transaction_read_only": read_only,
            }
            found, missing = discover_views(cur, args.views)
            report["missing_views"] = missing
            report["similar_qpes_views"] = find_similar_views(cur) if missing else []
            report["views"] = [audit_view(cur, item, args) for item in found]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=json_value),
        encoding="utf-8",
    )
    print(f"Audit report: {args.output}")
    print(
        "Session: "
        f"user={report['session']['current_user']}; "
        f"database={report['session']['current_database']}; "
        f"read_only={report['session']['transaction_read_only']}"
    )
    print(f"Found views: {len(report['views'])}; missing: {len(report['missing_views'])}")
    for view in report["views"]:
        count = view.get("row_count", {})
        print(
            f"- {view['qualified_name']}: select={view['has_select']}; "
            f"columns={len(view['columns'])}; rows={count.get('value', count.get('status', 'n/a'))}"
        )
    return 0 if not report["missing_views"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
