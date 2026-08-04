"""Read-only IMES evidence audit for abnormal heat 2#20260726-332."""

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


HEAT = "2#20260726-332"
HEAT_TAIL = "332"
OPEN_DAY = datetime(2026, 7, 26)


def json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    return str(value)


def connect(params: dict[str, Any]):
    return psycopg.connect(**params, row_factory=dict_row)


def rows(conn: Any, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(query, params).fetchall()]


def accessible_relations(conn: Any) -> list[dict[str, Any]]:
    return rows(
        conn,
        """
        SELECT c.table_schema, c.table_name, c.column_name, c.data_type
        FROM information_schema.columns c
        JOIN information_schema.tables t
          ON t.table_schema = c.table_schema AND t.table_name = c.table_name
        WHERE c.table_schema = 'public'
          AND has_table_privilege(
                quote_ident(c.table_schema) || '.' || quote_ident(c.table_name),
                'SELECT'
              )
          AND (
                lower(c.column_name) LIKE '%%melt%%'
             OR lower(c.column_name) LIKE '%%heat%%'
             OR lower(c.column_name) LIKE '%%tap%%'
             OR lower(c.column_name) LIKE '%%sample%%'
             OR c.column_name IN ('炉次', '炉号', '试样号')
          )
        ORDER BY c.table_schema, c.table_name, c.ordinal_position
        """,
    )


def search_candidate_columns(
    conn: Any, candidates: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for item in candidates:
        if item["data_type"] not in {
            "character varying",
            "character",
            "text",
            "name",
            "varchar",
        }:
            continue
        relation = sql.Identifier(item["table_schema"], item["table_name"])
        column = sql.Identifier(item["column_name"])
        query = sql.SQL(
            """
            SELECT *, {column}::text AS __matched_value
            FROM {relation}
            WHERE {column}::text = %s
               OR {column}::text LIKE %s
            LIMIT 200
            """
        ).format(column=column, relation=relation)
        try:
            found = conn.execute(query, (HEAT, f"%{HEAT_TAIL}%")).fetchall()
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            matches.append(
                {
                    "relation": f"{item['table_schema']}.{item['table_name']}",
                    "column": item["column_name"],
                    "error": type(exc).__name__,
                }
            )
            continue
        if found:
            matches.append(
                {
                    "relation": f"{item['table_schema']}.{item['table_name']}",
                    "column": item["column_name"],
                    "row_count_capped": len(found),
                    "rows": [dict(row) for row in found],
                }
            )
    return matches


def main() -> None:
    report: dict[str, Any] = {
        "audit_id": "Q-IMES-ABNORMAL-HEAT-332-20260726",
        "heat": HEAT,
        "checked_at": datetime.now(),
        "policy": "read_only",
    }
    with connect(heat_service.imes_ops_params()) as ops:
        report["server"] = dict(
            ops.execute(
                "SELECT current_database() database, current_user db_user, "
                "current_timestamp server_time, current_setting('TimeZone') timezone"
            ).fetchone()
        )
        report["heat_master"] = rows(
            ops,
            """
            SELECT *
            FROM public.t_ipes_cond
            WHERE meltno = %s
            ORDER BY opentime, closetime
            """,
            (HEAT,),
        )
        report["output_records"] = rows(
            ops,
            """
            SELECT *
            FROM public.t_ipes_out_put
            WHERE meltno = %s
            ORDER BY workdate, id
            """,
            (HEAT,),
        )
        ops_candidates = accessible_relations(ops)
        report["ops_candidate_columns"] = ops_candidates
        report["ops_cross_database_matches"] = search_candidate_columns(
            ops, ops_candidates
        )

    with connect(heat_service.imes_lab_params()) as lab:
        lab_candidates = accessible_relations(lab)
        report["lab_candidate_columns"] = lab_candidates
        report["lab_cross_database_matches"] = search_candidate_columns(
            lab, lab_candidates
        )
        report["hot_metal_candidates"] = rows(
            lab,
            f"""
            SELECT *
            FROM {heat_service.HOT_METAL_VIEW}
            WHERE "试样号" LIKE %s
              AND "发布时间" >= %s
              AND "发布时间" < %s
            ORDER BY "发布时间", "试样号"
            """,
            ("%332%", OPEN_DAY - timedelta(days=1), OPEN_DAY + timedelta(days=2)),
        )
        report["slag_exact"] = rows(
            lab,
            f"""
            SELECT *
            FROM {heat_service.SLAG_VIEW}
            WHERE meltno = %s
            ORDER BY publishtime, sampleno
            """,
            (HEAT,),
        )
        report["sinter_day_context"] = rows(
            lab,
            f"""
            SELECT *
            FROM {heat_service.SINTER_VIEW}
            WHERE "制样时间" >= %s AND "制样时间" < %s
            ORDER BY "制样时间", "试样单号"
            """,
            (OPEN_DAY, OPEN_DAY + timedelta(days=1)),
        )

    output = ROOT / "logs" / "imes_abnormal_heat_2_20260726_332.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=json_default),
        encoding="utf-8",
    )
    summary = {
        "output": str(output),
        "heat_master_rows": len(report["heat_master"]),
        "output_rows": len(report["output_records"]),
        "hot_metal_candidates": len(report["hot_metal_candidates"]),
        "slag_exact": len(report["slag_exact"]),
        "ops_relation_matches": len(report["ops_cross_database_matches"]),
        "lab_relation_matches": len(report["lab_cross_database_matches"]),
    }
    print(json.dumps(summary, ensure_ascii=False, default=json_default))


if __name__ == "__main__":
    main()
