from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

from assistant_pg import ensure_assistant_schema, raw_pg_connect, schema_name


BASE_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BASE_DIR.parent
DEFAULT_QA_SQLITE = BASE_DIR / "data" / "bf_qa.sqlite3"
DEFAULT_RAG_SQLITE = BASE_DIR / "data" / "bf_unified_vectors.sqlite3"


QA_TABLES = [
    "furnace_snapshots",
    "qa_conversations",
    "qa_messages",
    "period_reports",
    "report_template",
    "report_instance",
    "qa_projects",
    "project_assets",
    "qa_message_context_refs",
]

RAG_TABLE_MAP = {
    "document": "rag_document",
    "chunk": "rag_chunk",
}


def sqlite_table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return bool(row)


def sqlite_rows(conn: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    if not sqlite_table_exists(conn, table):
        return []
    return [dict(row) for row in conn.execute(f"SELECT * FROM {table}").fetchall()]


def pg_columns(pg_conn, table: str) -> set[str]:
    rows = pg_conn.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema=%s AND table_name=%s
        """,
        (schema_name(), table),
    ).fetchall()
    return {row["column_name"] for row in rows}


def upsert_rows(pg_conn, table: str, rows: list[dict[str, Any]], conflict_key: str | None = None) -> int:
    if not rows:
        return 0
    cols = pg_columns(pg_conn, table)
    writable = [
        col
        for col in rows[0].keys()
        if col in cols and col != "search_text"
    ]
    if not writable:
        return 0
    placeholders = ", ".join(["%s"] * len(writable))
    columns_sql = ", ".join(writable)
    if conflict_key and conflict_key in writable:
        updates = ", ".join(f"{col}=excluded.{col}" for col in writable if col != conflict_key)
        conflict_sql = f"ON CONFLICT ({conflict_key}) DO UPDATE SET {updates}" if updates else f"ON CONFLICT ({conflict_key}) DO NOTHING"
    else:
        conflict_sql = "ON CONFLICT DO NOTHING"
    sql = f"INSERT INTO {schema_name()}.{table} ({columns_sql}) VALUES ({placeholders}) {conflict_sql}"
    for row in rows:
        pg_conn.execute(sql, tuple(row.get(col) for col in writable))
    return len(rows)


def reset_sequence(pg_conn, table: str, column: str = "id") -> None:
    row = pg_conn.execute(
        "SELECT pg_get_serial_sequence(%s, %s) AS seq",
        (f"{schema_name()}.{table}", column),
    ).fetchone()
    if not row or not row.get("seq"):
        return
    max_row = pg_conn.execute(f"SELECT COALESCE(MAX({column}), 0) AS max_id FROM {schema_name()}.{table}").fetchone()
    max_id = int(max_row["max_id"] or 0)
    if max_id > 0:
        pg_conn.execute("SELECT setval(%s, %s, true)", (row["seq"], max_id))


def migrate_qa(sqlite_path: Path, pg_conn) -> dict[str, int]:
    if not sqlite_path.exists():
        return {"missing": 1}
    result: dict[str, int] = {}
    with sqlite3.connect(sqlite_path) as src:
        for table in QA_TABLES:
            rows = sqlite_rows(src, table)
            if table == "project_assets":
                for row in rows:
                    row["asset_ref_id"] = row.get("asset_ref_id") or ""
                    row["file_path"] = row.get("file_path") or ""
            conflict_key = "id" if table in {"furnace_snapshots", "qa_conversations", "qa_messages", "period_reports", "report_template", "report_instance", "qa_projects", "project_assets", "qa_message_context_refs"} else None
            result[table] = upsert_rows(pg_conn, table, rows, conflict_key=conflict_key)
    for table in QA_TABLES:
        if table != "qa_conversations":
            reset_sequence(pg_conn, table)
    return result


def migrate_rag(sqlite_path: Path, pg_conn) -> dict[str, int]:
    if not sqlite_path.exists():
        return {"missing": 1}
    result: dict[str, int] = {}
    with sqlite3.connect(sqlite_path) as src:
        for source_table, target_table in RAG_TABLE_MAP.items():
            rows = sqlite_rows(src, source_table)
            conflict_key = "doc_id" if target_table == "rag_document" else "chunk_id"
            result[target_table] = upsert_rows(pg_conn, target_table, rows, conflict_key=conflict_key)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate legacy assistant SQLite data into PostgreSQL bf_assistant schema.")
    parser.add_argument("--qa-sqlite", default=str(DEFAULT_QA_SQLITE))
    parser.add_argument("--rag-sqlite", default=str(DEFAULT_RAG_SQLITE))
    parser.add_argument("--skip-qa", action="store_true")
    parser.add_argument("--skip-rag", action="store_true")
    args = parser.parse_args()

    result: dict[str, Any] = {"schema": schema_name()}
    try:
        with raw_pg_connect() as pg_conn:
            ensure_assistant_schema(pg_conn)
            if not args.skip_qa:
                result["qa"] = migrate_qa(Path(args.qa_sqlite), pg_conn)
            if not args.skip_rag:
                result["rag"] = migrate_rag(Path(args.rag_sqlite), pg_conn)
            pg_conn.commit()
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        raise SystemExit(2) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
