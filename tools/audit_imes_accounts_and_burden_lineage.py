"""Read-only IMES account privilege and burden-lineage discovery."""

from __future__ import annotations

from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "db_dashboard"))
import heat_service  # noqa: E402


def default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    return str(value)


def connect(params: dict[str, Any]):
    return psycopg.connect(**params, row_factory=dict_row)


def fetch(conn: Any, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(query, params).fetchall()]


def account_audit(params: dict[str, Any]) -> dict[str, Any]:
    with connect(params) as conn:
        identity = dict(
            conn.execute(
                """
                SELECT current_database() database, current_user db_user,
                       session_user, current_timestamp server_time,
                       current_setting('transaction_read_only') read_only,
                       current_setting('TimeZone') timezone
                """
            ).fetchone()
        )
        relations = fetch(
            conn,
            """
            SELECT t.table_schema, t.table_name, t.table_type,
                   has_table_privilege(
                     quote_ident(t.table_schema)||'.'||quote_ident(t.table_name),
                     'SELECT'
                   ) can_select,
                   has_table_privilege(
                     quote_ident(t.table_schema)||'.'||quote_ident(t.table_name),
                     'INSERT'
                   ) can_insert,
                   has_table_privilege(
                     quote_ident(t.table_schema)||'.'||quote_ident(t.table_name),
                     'UPDATE'
                   ) can_update,
                   has_table_privilege(
                     quote_ident(t.table_schema)||'.'||quote_ident(t.table_name),
                     'DELETE'
                   ) can_delete
            FROM information_schema.tables t
            WHERE t.table_schema = 'public'
            ORDER BY t.table_name
            """,
        )
        readable = [row for row in relations if row["can_select"]]
        readable_names = [row["table_name"] for row in readable]
        columns = (
            fetch(
                conn,
                """
                SELECT table_name, ordinal_position, column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = ANY(%s)
                ORDER BY table_name, ordinal_position
                """,
                (readable_names,),
            )
            if readable_names
            else []
        )
        candidate_columns = [
            row
            for row in columns
            if any(
                token in str(row["column_name"]).lower()
                for token in (
                    "batch",
                    "charge",
                    "lot",
                    "material",
                    "stock",
                    "bin",
                    "bunker",
                    "warehouse",
                    "silo",
                    "tank",
                    "melt",
                    "heat",
                    "sample",
                    "workdate",
                )
            )
            or any(
                token in str(row["column_name"])
                for token in ("批", "料", "仓", "槽", "罐", "炉", "样")
            )
        ]
        return {
            "identity": identity,
            "relation_count": len(relations),
            "readable_count": len(readable),
            "writable_relations": [
                row
                for row in relations
                if row["can_insert"] or row["can_update"] or row["can_delete"]
            ],
            "readable_relations": readable,
            "readable_columns": columns,
            "lineage_candidate_columns": candidate_columns,
        }


def relation_rows(
    conn: Any, relation_name: str, where: sql.Composed | None = None
) -> list[dict[str, Any]]:
    query = sql.SQL("SELECT * FROM {}").format(sql.Identifier("public", relation_name))
    if where is not None:
        query += sql.SQL(" WHERE ") + where
    query += sql.SQL(" LIMIT 200")
    return [dict(row) for row in conn.execute(query).fetchall()]


def lineage_audit(params: dict[str, Any]) -> dict[str, Any]:
    with connect(params) as conn:
        result: dict[str, Any] = {}
        result["batch_input_columns"] = fetch(
            conn,
            """
            SELECT ordinal_position, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name='batch_input'
            ORDER BY ordinal_position
            """,
        )
        result["batch_input_recent"] = fetch(
            conn,
            """
            SELECT *
            FROM public.batch_input
            WHERE (
                    workdate >= %s AND workdate < %s
                  )
               OR (
                    workdate2 >= %s AND workdate2 < %s
                  )
            ORDER BY COALESCE(workdate2, workdate), id
            LIMIT 500
            """,
            (
                datetime(2026, 7, 25, 18),
                datetime(2026, 7, 26, 6),
                datetime(2026, 7, 25, 18),
                datetime(2026, 7, 26, 6),
            ),
        )
        result["heat_332"] = fetch(
            conn,
            """
            SELECT *
            FROM public.t_ipes_cond
            WHERE meltno=%s
            """,
            ("2#20260726-332",),
        )
        result["nearby_heats"] = fetch(
            conn,
            """
            SELECT meltno, workdate, sumbatchstart, sumbatchend, sumbatch,
                   opentime, closetime, tappingtime
            FROM public.t_ipes_cond
            WHERE prodcentercode='2D012'
              AND workdate BETWEEN %s AND %s
            ORDER BY opentime
            LIMIT 100
            """,
            (datetime(2026, 7, 25), datetime(2026, 7, 27)),
        )
        return result


def main() -> None:
    report = {
        "audit_id": "Q-IMES-ACCOUNT-PERMISSION-BURDEN-LINEAGE-20260726",
        "checked_at": datetime.now(),
        "policy": "read_only",
        "accounts": {
            "operations": account_audit(heat_service.imes_ops_params()),
            "laboratory": account_audit(heat_service.imes_lab_params()),
        },
        "lineage": lineage_audit(heat_service.imes_ops_params()),
    }
    output = ROOT / "logs" / "imes_accounts_burden_lineage_audit_20260726.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=default),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(output),
                "accounts": {
                    key: {
                        "db_user": value["identity"]["db_user"],
                        "read_only": value["identity"]["read_only"],
                        "readable_count": value["readable_count"],
                        "writable_count": len(value["writable_relations"]),
                    }
                    for key, value in report["accounts"].items()
                },
                "batch_rows": len(report["lineage"]["batch_input_recent"]),
                "nearby_heats": len(report["lineage"]["nearby_heats"]),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
