"""Read-only IMES audit for burden speed and fuel-ratio fields.

The probe is deliberately restricted to the two production-result objects
already approved by this project.  It records column metadata and a small
latest-row sample without printing or persisting database credentials.

Requirement: Q-IMES-MATERIAL-SPEED-FUEL-RATIO-20260806
Documentation: docs/IMES料速与燃料比只读核验_20260806.md
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

import psycopg
from psycopg import sql


ALLOWED_OBJECTS = (
    ("public", "t_ipes_out_put"),
    ("public", "t_ipes_cond"),
)

SEMANTIC_TERMS = {
    "material_speed": (
        "料速",
        "下料速度",
        "burden_speed",
        "material_speed",
        "feed_speed",
        "charging_speed",
        "liaosu",
    ),
    "fuel_ratio": (
        "燃料比",
        "综合燃料比",
        "fuel_ratio",
        "fuelrate",
        "fuel_rate",
        "ranliaobi",
    ),
    "coke_ratio": ("焦比", "coke_ratio", "cokeratio", "jiaobi"),
    "coal_ratio": ("煤比", "coal_ratio", "coalratio", "meibi"),
}


def normalized(value: Any) -> str:
    """Normalize a field name or comment for conservative alias matching."""

    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(value or "").lower())


def classify_column(column_name: str, comment: str | None) -> list[str]:
    """Return metric classes explicitly matched by a name or database comment."""

    haystacks = (normalized(column_name), normalized(comment))
    matched: list[str] = []
    for metric, terms in SEMANTIC_TERMS.items():
        if any(normalized(term) in text for term in terms for text in haystacks):
            matched.append(metric)
    return matched


def connection_info(args: argparse.Namespace) -> dict[str, Any]:
    """Build a read-only connection configuration from process environment."""

    user = os.environ.get("IMES_DB_USER")
    password = os.environ.get("IMES_DB_PASSWORD")
    if args.credential_profile == "approved-historical-operations":
        from export_vastbase_local import (
            HISTORICAL_DB_PASSWORD,
            HISTORICAL_DB_USER,
        )

        user = HISTORICAL_DB_USER
        password = HISTORICAL_DB_PASSWORD
    if not user or not password:
        raise RuntimeError("IMES_DB_USER/IMES_DB_PASSWORD are required")
    return {
        "host": args.host,
        "port": args.port,
        "dbname": args.database,
        "user": user,
        "password": password,
        "connect_timeout": args.connect_timeout,
        "options": (
            f"-c default_transaction_read_only=on "
            f"-c statement_timeout={args.statement_timeout_ms}"
        ),
    }


def column_metadata(cur: Any, schema_name: str, table_name: str) -> list[dict[str, Any]]:
    """Read names, types and comments for one allow-listed object."""

    cur.execute(
        """
        SELECT c.column_name,
               c.data_type,
               c.ordinal_position,
               pg_catalog.col_description(cls.oid, c.ordinal_position) AS comment
        FROM information_schema.columns c
        JOIN pg_catalog.pg_class cls ON cls.relname = c.table_name
        JOIN pg_catalog.pg_namespace ns
          ON ns.oid = cls.relnamespace AND ns.nspname = c.table_schema
        WHERE c.table_schema = %s AND c.table_name = %s
        ORDER BY c.ordinal_position
        """,
        (schema_name, table_name),
    )
    rows = []
    for name, data_type, ordinal, comment in cur.fetchall():
        rows.append(
            {
                "column": name,
                "data_type": data_type,
                "ordinal": ordinal,
                "comment": comment,
                "metric_classes": classify_column(name, comment),
            }
        )
    return rows


def global_semantic_columns(cur: Any) -> list[dict[str, Any]]:
    """Search public-schema metadata for explicit metric names or comments."""

    cur.execute(
        """
        SELECT c.table_schema,
               c.table_name,
               c.column_name,
               c.data_type,
               pg_catalog.col_description(cls.oid, c.ordinal_position) AS comment,
               has_table_privilege(
                   current_user,
                   quote_ident(c.table_schema) || '.' || quote_ident(c.table_name),
                   'SELECT'
               ) AS selectable
        FROM information_schema.columns c
        JOIN pg_catalog.pg_class cls ON cls.relname = c.table_name
        JOIN pg_catalog.pg_namespace ns
          ON ns.oid = cls.relnamespace AND ns.nspname = c.table_schema
        WHERE c.table_schema = 'public'
        ORDER BY c.table_name, c.ordinal_position
        """
    )
    matches = []
    for schema_name, table_name, column_name, data_type, comment, selectable in cur.fetchall():
        metric_classes = classify_column(column_name, comment)
        if not metric_classes:
            continue
        matches.append(
            {
                "object": f"{schema_name}.{table_name}",
                "column": column_name,
                "data_type": data_type,
                "comment": comment,
                "metric_classes": metric_classes,
                "selectable": bool(selectable),
            }
        )
    return matches


def latest_rows(
    cur: Any,
    schema_name: str,
    table_name: str,
    columns: Iterable[str],
    limit: int,
) -> list[dict[str, Any]]:
    """Return a bounded latest-row sample from one approved object."""

    names = list(columns)
    lower = {name.lower(): name for name in names}
    order_columns = [
        lower[name]
        for name in ("workdate", "opentime", "meltno")
        if name in lower
    ]
    query = sql.SQL("SELECT * FROM {}.{} WHERE prodcentercode = %s").format(
        sql.Identifier(schema_name),
        sql.Identifier(table_name),
    )
    if "prodcentercode" not in lower:
        query = sql.SQL("SELECT * FROM {}.{}").format(
            sql.Identifier(schema_name),
            sql.Identifier(table_name),
        )
        params: tuple[Any, ...] = ()
    else:
        params = ("2D012",)
    if order_columns:
        query += sql.SQL(" ORDER BY {} DESC").format(
            sql.SQL(", ").join(sql.Identifier(name) for name in order_columns)
        )
    query += sql.SQL(" LIMIT %s")
    params += (limit,)
    cur.execute(query, params)
    result_columns = [item.name for item in cur.description]
    return [
        {name: value for name, value in zip(result_columns, row)}
        for row in cur.fetchall()
    ]


def plain(value: Any) -> Any:
    """Convert database values into JSON-safe values."""

    if isinstance(value, (datetime,)):
        return value.isoformat(sep=" ")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<{len(value)} bytes>"
    if isinstance(value, Decimal):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only IMES audit for burden speed and fuel-ratio fields."
    )
    parser.add_argument("--host", default=os.environ.get("IMES_DB_HOST", "10.30.220.12"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("IMES_DB_PORT", "15433")))
    parser.add_argument("--database", default=os.environ.get("IMES_DB_NAME", "vastbase"))
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--connect-timeout", type=int, default=15)
    parser.add_argument("--statement-timeout-ms", type=int, default=30000)
    parser.add_argument(
        "--credential-profile",
        choices=("environment", "approved-historical-operations"),
        default="environment",
        help=(
            "Credential source. The historical operations profile reuses the "
            "existing project-approved fallback without copying its secret."
        ),
    )
    parser.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not 1 <= args.limit <= 20:
        raise SystemExit("--limit must be between 1 and 20")
    payload: dict[str, Any] = {
        "schema": "imes.material-speed-fuel-ratio.audit.v1",
        "audited_at": datetime.now().astimezone().isoformat(),
        "read_policy": "read_only",
        "source": f"{args.host}:{args.port}/{args.database}",
        "objects": [],
    }
    with psycopg.connect(**connection_info(args)) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT current_user, current_database(), "
                "current_setting('transaction_read_only')"
            )
            current_user, database, read_only = cur.fetchone()
            payload["connection"] = {
                "current_user": current_user,
                "database": database,
                "transaction_read_only": read_only,
            }
            payload["global_semantic_columns"] = global_semantic_columns(cur)
            for schema_name, table_name in ALLOWED_OBJECTS:
                metadata = column_metadata(cur, schema_name, table_name)
                samples = latest_rows(
                    cur,
                    schema_name,
                    table_name,
                    (item["column"] for item in metadata),
                    args.limit,
                )
                candidates = [item for item in metadata if item["metric_classes"]]
                payload["objects"].append(
                    {
                        "object": f"{schema_name}.{table_name}",
                        "column_count": len(metadata),
                        "columns": metadata,
                        "candidates": candidates,
                        "latest_rows": [
                            {key: plain(value) for key, value in row.items()}
                            for row in samples
                        ],
                    }
                )
    payload["candidate_count"] = sum(
        len(item["candidates"]) for item in payload["objects"]
    ) + len(payload["global_semantic_columns"])
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, default=plain)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    summary = {
        "ok": True,
        "read_policy": payload["read_policy"],
        "source": payload["source"],
        "connection": payload["connection"],
        "candidate_count": payload["candidate_count"],
        "candidates": {
            item["object"]: item["candidates"] for item in payload["objects"]
        },
        "global_semantic_columns": payload["global_semantic_columns"],
        "output": str(args.output.resolve()) if args.output else None,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
