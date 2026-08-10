from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from imes_readonly_client import DatasetDef, all_fieldnames
from pg_store import connect


MODULE_DIR = Path(__file__).resolve().parent
ROOT_DIR = MODULE_DIR.parents[0]
DEFAULT_SCHEMA = ROOT_DIR / "schema" / "postgresql_imes.sql"

IDENT_RE = re.compile(r"[^A-Za-z0-9_]")


def now_dt() -> datetime:
    return datetime.now().replace(microsecond=0)


def ensure_schema(conn: psycopg.Connection, schema_path: str | Path = DEFAULT_SCHEMA) -> None:
    conn.execute(Path(schema_path).read_text(encoding="utf-8"))
    conn.commit()


def safe_identifier(value: str) -> str:
    cleaned = IDENT_RE.sub("_", value.strip())
    if not cleaned:
        cleaned = "col"
    if cleaned[0].isdigit():
        cleaned = "_" + cleaned
    return cleaned[:60]


def canonical_json(row: dict[str, Any]) -> str:
    return json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def make_row_key(dataset: DatasetDef, row: dict[str, Any]) -> str:
    stable_fields = [
        "id",
        "inputNo",
        "outPutNo",
        "outputNo",
        "schemeNo",
        "monthPlanCode",
        "dayPlanCode",
        "planCode",
        "meltNo",
        "mHeatCode",
        "heatCode",
        "batchno",
        "sampleno",
        "binCode",
        "mateCode",
        "materialCode",
        "workdate2",
        "workdate",
        "workDate",
        "businessDate",
        "lot",
        "charge",
        "prodcentercode",
        "prodCenterCode",
    ]
    parts = [str(row.get(field) or "").strip() for field in stable_fields if str(row.get(field) or "").strip()]
    if any(parts):
        return "|".join([dataset.key] + parts)
    digest = hashlib.sha256(canonical_json(row).encode("utf-8")).hexdigest()
    return f"{dataset.key}|sha256:{digest}"


def parse_workdate(value: str | None) -> date | None:
    if not value:
        return None
    text = value.strip()
    for fmt, length in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d %H:%M", 16), ("%Y-%m-%d", 10), ("%Y-%m", 7)):
        try:
            return datetime.strptime(text[:length], fmt).date()
        except ValueError:
            continue
    return None


def extract_row_workdate(row: dict[str, Any], fallback: date | None = None) -> date | None:
    """Extract the business date used for retention and range alignment.

    Do not use create/update timestamps here. Some IMES dimension rows were
    created in 2024 but are still the current valid configuration.
    """
    for field in (
        "workdate",
        "workdate2",
        "workDate",
        "businessDate",
        "remark3",
        "remark4",
        "publishtime",
        "receivesampletime",
        "judgetime",
        "designDate",
        "planMonth",
    ):
        parsed = parse_workdate(str(row.get(field) or ""))
        if parsed:
            return parsed
    return fallback


def register_datasets(conn: psycopg.Connection, datasets: list[DatasetDef]) -> None:
    rows = [
        (
            dataset.key,
            dataset.label,
            dataset.endpoint,
            dataset.table_name,
            Jsonb([{"field": field, "title": title} for field, title in dataset.columns]),
            dataset.notes,
            now_dt(),
        )
        for dataset in datasets
    ]
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO bf_imes.dataset_catalog (
                dataset_key, dataset_label, endpoint, table_name, columns_json, notes, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(dataset_key) DO UPDATE SET
                dataset_label=excluded.dataset_label,
                endpoint=excluded.endpoint,
                table_name=excluded.table_name,
                columns_json=excluded.columns_json,
                notes=excluded.notes,
                updated_at=excluded.updated_at
            """,
            rows,
        )
    conn.commit()


def start_run(
    conn: psycopg.Connection,
    dataset: DatasetDef,
    sync_mode: str,
    workdate: date | None,
    params: dict[str, Any],
) -> int:
    row = conn.execute(
        """
        INSERT INTO bf_imes.fetch_runs (
            sync_mode, dataset_key, dataset_label, workdate, endpoint, params_json
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (sync_mode, dataset.key, dataset.label, workdate, dataset.endpoint, Jsonb(params)),
    ).fetchone()
    conn.commit()
    return int(row["id"] if isinstance(row, dict) else row[0])


def finish_run(
    conn: psycopg.Connection,
    run_id: int,
    rows_read: int,
    rows_written: int,
    total: int | None,
    error: str = "",
) -> None:
    conn.execute(
        """
        UPDATE bf_imes.fetch_runs
        SET finished_at=%s, rows_read=%s, rows_written=%s, total=%s, error=%s
        WHERE id=%s
        """,
        (now_dt(), rows_read, rows_written, total, error, run_id),
    )
    conn.commit()


def ensure_wide_table(conn: psycopg.Connection, dataset: DatasetDef, fields: list[str]) -> list[str]:
    table_name = safe_identifier(dataset.table_name)
    conn.execute(
        sql.SQL("CREATE TABLE IF NOT EXISTS bf_imes.{} (_row_key text PRIMARY KEY)").format(sql.Identifier(table_name))
    )
    existing = {
        row["column_name"] if isinstance(row, dict) else row[0]
        for row in conn.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema='bf_imes' AND table_name=%s
            """,
            (table_name,),
        ).fetchall()
    }
    safe_fields: list[str] = []
    for field in fields:
        if field == "_row_key":
            continue
        safe = safe_identifier(field)
        if safe in safe_fields:
            continue
        if safe not in existing:
            conn.execute(
                sql.SQL("ALTER TABLE bf_imes.{} ADD COLUMN {} text").format(
                    sql.Identifier(table_name),
                    sql.Identifier(safe),
                )
            )
            existing.add(safe)
        safe_fields.append(safe)
    conn.commit()
    return safe_fields


def upsert_wide_table(
    conn: psycopg.Connection,
    dataset: DatasetDef,
    rows: list[dict[str, Any]],
    fields: list[str],
) -> int:
    if not rows:
        return 0
    table_name = safe_identifier(dataset.table_name)
    safe_fields = ensure_wide_table(conn, dataset, fields)
    columns = ["_row_key"] + safe_fields
    insert_sql = sql.SQL("INSERT INTO bf_imes.{} ({}) VALUES ({}) ON CONFLICT (_row_key) DO UPDATE SET {}").format(
        sql.Identifier(table_name),
        sql.SQL(", ").join(sql.Identifier(col) for col in columns),
        sql.SQL(", ").join(sql.Placeholder() for _ in columns),
        sql.SQL(", ").join(
            sql.SQL("{} = excluded.{}").format(sql.Identifier(col), sql.Identifier(col)) for col in safe_fields
        ),
    )
    values: list[tuple[Any, ...]] = []
    for row in rows:
        values.append(tuple(None if row.get(col) is None else str(row.get(col)) for col in columns))
    with conn.cursor() as cur:
        cur.executemany(insert_sql, values)
    conn.commit()
    return len(values)


def upsert_raw_rows(conn: psycopg.Connection, dataset: DatasetDef, rows: list[dict[str, Any]], workdate: date | None) -> int:
    if not rows:
        return 0
    prepared: list[tuple[Any, ...]] = []
    for row in rows:
        row_key = str(row["_row_key"])
        row_date = extract_row_workdate(row, workdate)
        fetched_at = row.get("_fetched_at")
        fetched_dt = None
        if fetched_at:
            try:
                fetched_dt = datetime.strptime(str(fetched_at), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                fetched_dt = now_dt()
        prepared.append(
            (
                dataset.key,
                row_key,
                dataset.label,
                dataset.endpoint,
                row_date,
                row.get("workdate2"),
                row.get("lot"),
                row.get("charge"),
                row.get("prodcentercode") or row.get("prodCenterCode"),
                Jsonb(row),
                fetched_dt or now_dt(),
                now_dt(),
            )
        )
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO bf_imes.raw_rows (
                dataset_key, row_key, dataset_label, endpoint, workdate, workdate2,
                lot, charge, prodcentercode, row_json, fetched_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(dataset_key, row_key) DO UPDATE SET
                dataset_label=excluded.dataset_label,
                endpoint=excluded.endpoint,
                workdate=excluded.workdate,
                workdate2=excluded.workdate2,
                lot=excluded.lot,
                charge=excluded.charge,
                prodcentercode=excluded.prodcentercode,
                row_json=excluded.row_json,
                fetched_at=excluded.fetched_at,
                updated_at=excluded.updated_at
            """,
            prepared,
        )
    conn.commit()
    return len(prepared)


def upsert_payload(conn: psycopg.Connection, dataset: DatasetDef, payload: dict[str, Any], workdate: date | None) -> int:
    rows: list[dict[str, Any]] = []
    for raw in payload.get("rows", []):
        row = dict(raw)
        row_date = extract_row_workdate(row, workdate)
        if row_date:
            row["_row_workdate"] = row_date.isoformat()
        row["_row_key"] = str(row.get("_row_key") or make_row_key(dataset, row))
        rows.append(row)
    fields = all_fieldnames(rows, preferred=[field for field, _ in dataset.columns])
    written_raw = upsert_raw_rows(conn, dataset, rows, workdate)
    upsert_wide_table(conn, dataset, rows, fields)
    return written_raw


def summary(conn: psycopg.Connection) -> dict[str, Any]:
    raw = conn.execute(
        """
        SELECT COUNT(*) AS rows_count,
               COUNT(DISTINCT dataset_key) AS dataset_count,
               MIN(workdate) AS min_workdate,
               MAX(workdate) AS max_workdate
        FROM bf_imes.raw_rows
        """
    ).fetchone()
    runs = conn.execute("SELECT COUNT(*) AS n FROM bf_imes.fetch_runs").fetchone()
    return {
        "raw_rows": int(raw["rows_count"] or 0),
        "datasets": int(raw["dataset_count"] or 0),
        "min_workdate": str(raw["min_workdate"]) if raw["min_workdate"] else None,
        "max_workdate": str(raw["max_workdate"]) if raw["max_workdate"] else None,
        "fetch_runs": int(runs["n"] or 0),
    }
