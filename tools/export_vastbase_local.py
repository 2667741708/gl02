# -*- coding: utf-8 -*-
"""Discover and safely export every IMES Vastbase object visible to the account.

This file retains the project-approved historical credential fallback.  New
deployments should override it with IMES_DB_USER / IMES_DB_PASSWORD.

Requirement: REQ-IMES-VASTBASE-DISCOVERY-20260716
Documentation: docs/imes.md
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import socket
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Sequence

import psycopg


DEFAULT_OUTPUT_DIR = Path(
    os.environ.get(
        "IMES_EXPORT_DIR",
        r"D:\文件\服务器实际运行版\导出数据包\IMES_Vastbase_discovery",
    )
)
DEFAULT_HOST = os.environ.get("IMES_DB_HOST", "10.10.181.195")
DEFAULT_PORT = int(os.environ.get("IMES_DB_PORT", "5432"))
DEFAULT_DATABASE = os.environ.get("IMES_DB_NAME", "vastbase")

# Historical local exception explicitly approved by the user.  Environment
# variables take precedence and are the recommended configuration path.
HISTORICAL_DB_USER = "gl2#dmx"
HISTORICAL_DB_PASSWORD = "gl2#dmx!"

SYSTEM_SCHEMAS = {"information_schema", "pg_catalog", "pg_toast"}
DATE_COLUMNS = (
    "workdate",
    "work_date",
    "businessdate",
    "business_date",
    "judgetime",
    "publishtime",
    "createtime",
    "create_time",
    "plandate",
    "plan_date",
)

CATEGORY_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("生产实绩", ("out_put", "output", "production_result")),
    ("批次投料", ("batch_input", "batchinput", "batch_feed")),
    ("炉次化验", ("inner_batch", "heat_lab", "insp_bb", "ipes_cond")),
    ("炉渣检验", ("slag",)),
    ("原料投入", ("ipes_input", "raw_input", "material_input")),
    ("配料方案", ("dosing", "scheme", "burden")),
    ("料仓", ("pes_bin", "ipes_bin", "bin_material", "bunker")),
    ("生产计划", ("production_plan", "plan_month", "plan_day", "cpes_plan")),
)

# Objects already proven by historical exports.  Discovery can add more.
CONFIRMED_OBJECTS = {
    "public.t_ipes_out_put": "生产实绩",
    "public.t_ipes_cond": "炉次化验",
    "public.t_qpes_inner_batch": "炉次化验",
    "public.inner_batch_insp_bb": "炉次化验",
    "public.slag_inspection": "炉渣检验",
    "public.batch_input": "批次投料",
}


@dataclass(frozen=True)
class DbObject:
    """One visible Vastbase table or view and its discovered columns."""

    schema: str
    name: str
    object_type: str
    category: str
    columns: tuple[str, ...]
    date_column: str | None
    selectable: bool
    error: str | None = None

    @property
    def qualified_name(self) -> str:
        return f"{self.schema}.{self.name}"


def parse_iso_date(value: str) -> str:
    """Validate and normalize an ISO business date."""

    return date.fromisoformat(value).isoformat()


def quote_identifier(value: str) -> str:
    """Quote a catalog identifier, including non-ASCII schema/table names."""

    if not value or "\x00" in value:
        raise ValueError(f"unsupported SQL identifier: {value!r}")
    return '"' + value.replace('"', '""') + '"'


def qualified_sql(schema: str, name: str) -> str:
    """Return a safely quoted schema-qualified object name."""

    return f"{quote_identifier(schema)}.{quote_identifier(name)}"


def classify_object(schema: str, name: str, columns: Sequence[str]) -> str:
    """Classify an object by confirmed name, then conservative name patterns."""

    qualified = f"{schema}.{name}".lower()
    if qualified in CONFIRMED_OBJECTS:
        return CONFIRMED_OBJECTS[qualified]
    lowered = name.lower()
    for category, patterns in CATEGORY_PATTERNS:
        if any(pattern in lowered for pattern in patterns):
            return category
    column_set = {column.lower() for column in columns}
    if {"meltno", "value_02"}.issubset(column_set):
        return "检验/炉次候选"
    if {"materialcode", "materialname"} & column_set and {
        "inputscquan",
        "dryquan",
    } & column_set:
        return "原料投入候选"
    return "其他"


def choose_date_column(columns: Sequence[str]) -> str | None:
    """Choose the first known business-time column present on an object."""

    by_lower = {column.lower(): column for column in columns}
    for candidate in DATE_COLUMNS:
        if candidate in by_lower:
            return by_lower[candidate]
    return None


def connection_info(args: argparse.Namespace) -> dict[str, Any]:
    """Build a connection dictionary without printing credentials."""

    return {
        "host": args.host,
        "port": args.port,
        "dbname": args.database,
        "user": os.environ.get("IMES_DB_USER", HISTORICAL_DB_USER),
        "password": os.environ.get("IMES_DB_PASSWORD", HISTORICAL_DB_PASSWORD),
        "connect_timeout": args.connect_timeout,
        "options": f"-c statement_timeout={args.statement_timeout_ms}",
    }


def tcp_probe(host: str, port: int, timeout: int) -> dict[str, Any]:
    """Probe TCP reachability without authenticating to Vastbase."""

    started = datetime.now()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            ok, error = True, None
    except OSError as exc:
        ok, error = False, f"{type(exc).__name__}: {exc}"
    return {
        "host": host,
        "port": port,
        "ok": ok,
        "elapsed_ms": int((datetime.now() - started).total_seconds() * 1000),
        "error": error,
    }


def load_catalog_rows(cur: Any) -> list[tuple[str, str, str, str, int]]:
    """Load non-system table/view columns visible through information_schema."""

    cur.execute(
        """SELECT t.table_schema, t.table_name, t.table_type,
                  c.column_name, c.ordinal_position
           FROM information_schema.tables t
           JOIN information_schema.columns c
             ON c.table_schema = t.table_schema
            AND c.table_name = t.table_name
           WHERE t.table_schema NOT IN ('information_schema', 'pg_catalog')
           ORDER BY t.table_schema, t.table_name, c.ordinal_position"""
    )
    return list(cur.fetchall())


def group_catalog_rows(
    rows: Iterable[tuple[str, str, str, str, int]],
) -> list[tuple[str, str, str, tuple[str, ...]]]:
    """Group one information_schema row per column into one object record."""

    grouped: dict[tuple[str, str, str], list[tuple[int, str]]] = {}
    for schema, name, object_type, column, ordinal in rows:
        if schema in SYSTEM_SCHEMAS:
            continue
        grouped.setdefault((schema, name, object_type), []).append((ordinal, column))
    return [
        (schema, name, object_type, tuple(column for _, column in sorted(items)))
        for (schema, name, object_type), items in sorted(grouped.items())
    ]


def probe_selectable(cur: Any, schema: str, name: str) -> tuple[bool, str | None]:
    """Verify SELECT permission with a zero-row statement and rollback on error."""

    statement = f"SELECT * FROM {qualified_sql(schema, name)} WHERE 1=0"
    try:
        cur.execute("SAVEPOINT imes_probe")
        cur.execute(statement)
        cur.execute("RELEASE SAVEPOINT imes_probe")
        return True, None
    except Exception as exc:  # database driver exceptions vary by Vastbase build
        try:
            cur.execute("ROLLBACK TO SAVEPOINT imes_probe")
            cur.execute("RELEASE SAVEPOINT imes_probe")
        except Exception:
            pass
        return False, f"{type(exc).__name__}: {exc}"


def discover_objects(cur: Any) -> list[DbObject]:
    """Enumerate every catalog-visible object and verify real SELECT access."""

    discovered: list[DbObject] = []
    for schema, name, object_type, columns in group_catalog_rows(load_catalog_rows(cur)):
        selectable, error = probe_selectable(cur, schema, name)
        discovered.append(
            DbObject(
                schema=schema,
                name=name,
                object_type=object_type,
                category=classify_object(schema, name, columns),
                columns=columns,
                date_column=choose_date_column(columns),
                selectable=selectable,
                error=error,
            )
        )
    return discovered


def filter_objects(
    objects: Sequence[DbObject],
    categories: Sequence[str],
    explicit_objects: Sequence[str],
    include_other: bool,
) -> list[DbObject]:
    """Select export targets from the discovered catalog."""

    explicit = {value.lower() for value in explicit_objects}
    requested_categories = set(categories)
    selected: list[DbObject] = []
    for item in objects:
        if not item.selectable:
            continue
        if explicit and item.qualified_name.lower() in explicit:
            selected.append(item)
        elif requested_categories and item.category in requested_categories:
            selected.append(item)
        elif not explicit and not requested_categories and (
            include_other or item.category != "其他"
        ):
            selected.append(item)
    unknown = explicit - {item.qualified_name.lower() for item in objects}
    if unknown:
        raise ValueError("objects not found in accessible catalog: " + ", ".join(sorted(unknown)))
    return selected


def build_export_query(
    item: DbObject,
    start_date: str,
    end_date: str,
    max_rows: int,
) -> tuple[str, tuple[Any, ...]]:
    """Build a bounded SELECT for one discovered table or view."""

    sql_text = f"SELECT * FROM {qualified_sql(item.schema, item.name)}"
    params: list[Any] = []
    if item.date_column:
        end_exclusive = (date.fromisoformat(end_date) + timedelta(days=1)).isoformat()
        sql_text += f" WHERE {quote_identifier(item.date_column)} >= %s"
        sql_text += f" AND {quote_identifier(item.date_column)} < %s"
        params.extend((start_date, end_exclusive))
        sql_text += f" ORDER BY {quote_identifier(item.date_column)}"
    if max_rows > 0:
        sql_text += " LIMIT %s"
        params.append(max_rows)
    return sql_text, tuple(params)


def safe_filename(item: DbObject) -> str:
    """Create a deterministic filesystem-safe name for an object export."""

    raw = f"{item.category}_{item.schema}_{item.name}"
    return re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", raw).strip("_")[:160]


def export_object(
    cur: Any,
    item: DbObject,
    output_dir: Path,
    start_date: str,
    end_date: str,
    max_rows: int,
) -> dict[str, Any]:
    """Stream one bounded object query to UTF-8-SIG CSV."""

    query, params = build_export_query(item, start_date, end_date, max_rows)
    cur.execute(query, params)
    columns = [description[0] for description in cur.description]
    target = output_dir / f"{safe_filename(item)}.csv"
    row_count = 0
    with target.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        while True:
            rows = cur.fetchmany(1000)
            if not rows:
                break
            for row in rows:
                writer.writerow(
                    value
                    if value is None or isinstance(value, (str, int, float, bool))
                    else str(value)
                    for value in row
                )
            row_count += len(rows)
    return {
        "object": item.qualified_name,
        "category": item.category,
        "date_column": item.date_column,
        "rows": row_count,
        "columns": columns,
        "file": target.name,
        "bounded": max_rows > 0,
    }


def catalog_payload(objects: Sequence[DbObject]) -> list[dict[str, Any]]:
    """Serialize discovered objects without credentials or row data."""

    return [asdict(item) | {"qualified_name": item.qualified_name} for item in objects]


def write_json(path: Path, payload: Any) -> None:
    """Write stable UTF-8 JSON."""

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    """Build the safe discovery/export command line interface."""

    today = date.today()
    parser = argparse.ArgumentParser(
        description="只读发现 IMES Vastbase 账号可访问对象，并按日期和行数安全导出。"
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--database", default=DEFAULT_DATABASE)
    parser.add_argument("--connect-timeout", type=int, default=8)
    parser.add_argument("--statement-timeout-ms", type=int, default=60000)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--start-date", type=parse_iso_date, default=(today - timedelta(days=1)).isoformat())
    parser.add_argument("--end-date", type=parse_iso_date, default=today.isoformat())
    parser.add_argument("--tcp-check", action="store_true", help="只检查 TCP，不登录数据库。")
    parser.add_argument("--discover", action="store_true", help="发现并验证全部可见表/视图。")
    parser.add_argument("--export", action="store_true", help="导出发现到的 MES 候选对象。")
    parser.add_argument("--category", action="append", default=[], help="只导出指定业务分类，可重复。")
    parser.add_argument("--object", action="append", default=[], help="只导出 schema.table，可重复。")
    parser.add_argument("--include-other", action="store_true", help="导出未分类对象；风险较高。")
    parser.add_argument("--max-rows-per-object", type=int, default=1000)
    parser.add_argument("--allow-unlimited", action="store_true", help="允许 max-rows=0 全量导出。")
    return parser


def validate_args(args: argparse.Namespace) -> None:
    """Reject unsafe or contradictory argument combinations."""

    if date.fromisoformat(args.start_date) > date.fromisoformat(args.end_date):
        raise ValueError("--start-date must not be after --end-date")
    if args.max_rows_per_object < 0:
        raise ValueError("--max-rows-per-object must be >= 0")
    if args.max_rows_per_object == 0 and not args.allow_unlimited:
        raise ValueError("max-rows=0 requires --allow-unlimited")
    if args.export and args.include_other and not args.object and args.max_rows_per_object == 0:
        raise ValueError("unlimited export of every unclassified object is not allowed")


def main(argv: Sequence[str] | None = None) -> int:
    """Run TCP diagnosis, discovery, and optional bounded exports."""

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        validate_args(args)
    except ValueError as exc:
        parser.error(str(exc))

    if args.tcp_check:
        probe = tcp_probe(args.host, args.port, args.connect_timeout)
        print(json.dumps(probe, ensure_ascii=False, indent=2))
        return 0 if probe["ok"] else 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    try:
        with psycopg.connect(**connection_info(args)) as conn:
            with conn.cursor() as cur:
                objects = discover_objects(cur)
                catalog_path = args.output_dir / "vastbase_accessible_catalog.json"
                write_json(catalog_path, catalog_payload(objects))
                selectable = [item for item in objects if item.selectable]
                candidates = [item for item in selectable if item.category != "其他"]
                print(
                    f"Discovered {len(objects)} objects; SELECT works on {len(selectable)}; "
                    f"MES candidates: {len(candidates)}"
                )
                print(f"Catalog: {catalog_path}")

                exports: list[dict[str, Any]] = []
                if args.export:
                    targets = filter_objects(
                        objects,
                        args.category,
                        args.object,
                        args.include_other,
                    )
                    for index, item in enumerate(targets, 1):
                        print(f"[{index}/{len(targets)}] {item.category}: {item.qualified_name}")
                        try:
                            exports.append(
                                export_object(
                                    cur,
                                    item,
                                    args.output_dir,
                                    args.start_date,
                                    args.end_date,
                                    args.max_rows_per_object,
                                )
                            )
                        except Exception as exc:
                            conn.rollback()
                            exports.append(
                                {
                                    "object": item.qualified_name,
                                    "category": item.category,
                                    "error": f"{type(exc).__name__}: {exc}",
                                }
                            )
                manifest = {
                    "generated_at": datetime.now().isoformat(),
                    "source": f"{args.host}:{args.port}/{args.database}",
                    "date_range": [args.start_date, args.end_date],
                    "max_rows_per_object": args.max_rows_per_object,
                    "catalog_objects": len(objects),
                    "selectable_objects": len(selectable),
                    "mes_candidates": len(candidates),
                    "exports": exports,
                }
                manifest_path = args.output_dir / "vastbase_discovery_manifest.json"
                write_json(manifest_path, manifest)
                print(f"Manifest: {manifest_path}")
        return 0
    except psycopg.Error as exc:
        print(f"Vastbase error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"Network/file error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
