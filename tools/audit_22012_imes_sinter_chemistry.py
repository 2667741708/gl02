"""Read-only snapshot of the IMES sinter-feed chemistry view via 220.12."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV = ROOT / "PT" / "imes_vastbase.local.env"


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="只读核对220.12转发的IMES烧结矿化学成分。")
    parser.add_argument("--host", default="10.30.220.12")
    parser.add_argument("--port", type=int, default=15433)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--days", type=int, default=15)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    local_env = read_env(args.env_file.resolve())
    user = local_env.get("IMES_DB_USER", "")
    password = local_env.get("IMES_DB_PASSWORD", "")
    database = local_env.get("IMES_DB_NAME", "vastbase")
    if not user or not password:
        raise RuntimeError("IMES read-only credentials are not configured")

    end_date = date.today()
    start_date = end_date - timedelta(days=max(1, args.days))
    view_name = "public.v_qpes_sinter_machine_sample_insp_final"
    with psycopg.connect(
        host=args.host,
        port=args.port,
        dbname=database,
        user=user,
        password=password,
        connect_timeout=15,
        options="-c statement_timeout=30000",
        row_factory=dict_row,
    ) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        identity = connection.execute(
            "SELECT current_database() AS database, current_user AS current_user, "
            "current_setting('transaction_read_only') AS read_only"
        ).fetchone()
        permission = connection.execute(
            "SELECT has_table_privilege(current_user, %s, 'SELECT') AS can_select",
            (view_name,),
        ).fetchone()
        summary = connection.execute(
            """
            SELECT count(*) AS row_count,
                   count(DISTINCT "试样单号") AS sample_count,
                   min("业务日期") AS min_business_date,
                   max("业务日期") AS max_business_date,
                   max("发布时间") AS max_publish_time,
                   sum(CASE WHEN nullif(trim(tfevalue), '') IS NOT NULL THEN 1 ELSE 0 END) AS tfe_rows,
                   sum(CASE WHEN nullif(trim(sio2value), '') IS NOT NULL THEN 1 ELSE 0 END) AS sio2_rows,
                   sum(CASE WHEN nullif(trim(al2o3value), '') IS NOT NULL THEN 1 ELSE 0 END) AS al2o3_rows,
                   sum(CASE WHEN nullif(trim(caovalue), '') IS NOT NULL THEN 1 ELSE 0 END) AS cao_rows,
                   sum(CASE WHEN nullif(trim(mgovalue), '') IS NOT NULL THEN 1 ELSE 0 END) AS mgo_rows
            FROM public.v_qpes_sinter_machine_sample_insp_final
            WHERE "业务日期" >= %s AND "业务日期" < %s
            """,
            (start_date, end_date + timedelta(days=1)),
        ).fetchone()
        rows = connection.execute(
            """
            SELECT "试样单号", "业务日期", "检验批号", "加工中心编码", "加工中心名称",
                   "发布时间", tfevalue, caovalue, mgovalue, sio2value, al2o3value,
                   pvalue, tio2value, mnovalue, znvalue, crvalue, r2value,
                   feovalue, svalue, mgalvalue, alsivalue, qdvalue
            FROM public.v_qpes_sinter_machine_sample_insp_final
            WHERE "业务日期" >= %s AND "业务日期" < %s
            ORDER BY "发布时间" DESC NULLS LAST, "试样单号" DESC
            LIMIT %s
            """,
            (start_date, end_date + timedelta(days=1), max(1, min(args.limit, 100))),
        ).fetchall()

    payload = {
        "schema": "bf.imes_sinter_chemistry_audit.v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "read_policy": "readonly",
        "source": view_name,
        "identity": identity,
        "select_permission": permission,
        "window": {"start_date": start_date, "end_date": end_date},
        "summary": summary,
        "rows": rows,
        "boundary": (
            "This view is sinter-feed chemistry by sample/machine. It is not yet a "
            "whole-heat burden chemistry feature without a verified batch-to-heat lineage."
        ),
    }
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=json_default),
        encoding="utf-8",
    )
    print(json.dumps({"ok": True, "output": str(output), "summary": summary}, ensure_ascii=False, default=json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
