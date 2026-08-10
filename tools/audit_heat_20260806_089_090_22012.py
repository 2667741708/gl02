from pathlib import Path
import sys

import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_hot_metal_si_dataset as b  # noqa: E402


TARGETS = ("2#20260806-089", "2#20260806-090")


def main() -> None:
    ns = type(
        "N",
        (),
        dict(
            ssh_host="10.30.220.12",
            ssh_user="administrator",
            remote_pg_host="127.0.0.1",
            remote_pg_port=5432,
            local_tunnel_port=15444,
            remote_pg_user="gl02_sync",
            remote_pg_db="bf_trend",
            connect_timeout=20,
        ),
    )()
    with b.sensor_ssh_tunnel(ns) as (port, client):
        params = b.remote_sensor_params(ns, port, client)
        params["options"] = "-c default_transaction_read_only=on -c statement_timeout=60000"
        with psycopg.connect(**params, row_factory=dict_row) as conn:
            sections = {
                "summary": """
                    SELECT * FROM bf_assistant.heat_performance_quality_summary
                    WHERE meltno = ANY(%s)
                    ORDER BY meltno
                """,
                "imes_output": """
                    SELECT "meltNo" AS meltno, "workDate" AS work_date,
                           "openTime" AS open_ts, "closeTime" AS close_ts,
                           "ironQuan" AS iron_qty, "takesampletime" AS sample_ts,
                           "judgetime" AS judge_ts, "batchno" AS batchno, "id" AS id
                    FROM bf_imes.imes_bf2_output_list_cond_data
                    WHERE "meltNo" = ANY(%s)
                    ORDER BY "meltNo", "openTime" NULLS LAST, id
                """,
                "imes_heat_lab": """
                    SELECT "meltNo" AS meltno, "workDate" AS work_date,
                           "inspElemName" AS element, "receivesampletime" AS receive_ts,
                           "publishtime" AS publish_ts, "value_01" AS c,
                           "value_02" AS si, "value_03" AS mn, "value_04" AS p,
                           "value_05" AS s, "batchno" AS batchno, "id" AS id
                    FROM bf_imes.imes_bf2_heat_lab_list_cond_data_avg2
                    WHERE "meltNo" = ANY(%s)
                    ORDER BY "meltNo", "publishtime" NULLS LAST, id
                """,
                "raw_rows": """
                    SELECT dataset_key, row_key, workdate, lot, charge, fetched_at,
                           row_json->>'meltNo' AS meltno,
                           row_json->>'openTime' AS open_time,
                           row_json->>'value_02' AS si
                    FROM bf_imes.raw_rows
                    WHERE row_json->>'meltNo' = ANY(%s)
                    ORDER BY dataset_key, row_key
                """,
            }
            for name, sql in sections.items():
                rows = conn.execute(sql, (list(TARGETS),)).fetchall()
                print(name, len(rows))
                for row in rows:
                    print(dict(row))


if __name__ == "__main__":
    main()

