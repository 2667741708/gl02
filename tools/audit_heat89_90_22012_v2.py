from pathlib import Path
import sys
import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_hot_metal_si_dataset as b

ns = type("N", (), dict(
    ssh_host="10.30.220.12", ssh_user="administrator", remote_pg_host="127.0.0.1",
    remote_pg_port=5432, local_tunnel_port=15441, remote_pg_user="gl02_sync",
    remote_pg_db="bf_trend", connect_timeout=20,
))()

with b.sensor_ssh_tunnel(ns) as (port, client):
    params = b.remote_sensor_params(ns, port, client)
    params["options"] = "-c default_transaction_read_only=on -c statement_timeout=60000"
    with psycopg.connect(**params, row_factory=dict_row) as conn:
        print("IMES_OUTPUT_20260807")
        rows = conn.execute('''
            SELECT "meltNo" AS meltno,"workDate" AS work_date,
                   "openTime" AS open_ts,"closeTime" AS close_ts,
                   "tappingTime" AS tapping_ts,"takesampletime" AS sample_ts,
                   "judgetime" AS judge_ts,"value_01" AS value_01,
                   "value_02" AS value_02,"value_03" AS value_03,
                   "value_04" AS value_04,"value_05" AS value_05,
                   "batchno" AS batchno,"id" AS id
            FROM bf_imes.imes_bf2_output_list_cond_data
            WHERE "meltNo" LIKE '2#20260807-%'
              AND ("meltNo" LIKE '%-089' OR "meltNo" LIKE '%-090')
            ORDER BY "openTime" DESC NULLS LAST
        ''').fetchall()
        for row in rows:
            print(dict(row))
        print("IMES_HEAT_LAB_20260807")
        rows = conn.execute('''
            SELECT "meltNo" AS meltno,"workDate" AS work_date,
                   "sumBatch" AS sum_batch,"inspElemName" AS element,
                   "receivesampletime" AS receive_ts,"publishtime" AS publish_ts,
                   "value_01" AS value_01,"value_02" AS value_02,
                   "value_03" AS value_03,"value_04" AS value_04,
                   "value_05" AS value_05,"batchno" AS batchno,"id" AS id
            FROM bf_imes.imes_bf2_heat_lab_list_cond_data_avg2
            WHERE "meltNo" LIKE '2#20260807-%'
              AND ("meltNo" LIKE '%-089' OR "meltNo" LIKE '%-090')
            ORDER BY "publishtime" DESC NULLS LAST
        ''').fetchall()
        for row in rows:
            print(dict(row))
