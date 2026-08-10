from __future__ import annotations

from pathlib import Path
import sys
import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_hot_metal_si_dataset as b

ns = type("N", (), dict(
    ssh_host="10.30.220.12", ssh_user="administrator", remote_pg_host="127.0.0.1",
    remote_pg_port=5432, local_tunnel_port=15440, remote_pg_user="gl02_sync",
    remote_pg_db="bf_trend", connect_timeout=20,
))()

with b.sensor_ssh_tunnel(ns) as (port, client):
    params = b.remote_sensor_params(ns, port, client)
    params["options"] = "-c default_transaction_read_only=on -c statement_timeout=60000"
    with psycopg.connect(**params, row_factory=dict_row) as conn:
        print("SUMMARY")
        rows = conn.execute("""
            SELECT meltno,furnace_no,work_date,open_ts,close_ts,si_avg,
                   hot_metal_sample_count,quality_status,source_updated_at
            FROM bf_assistant.heat_performance_quality_summary
            WHERE meltno IN ('2#20260807-089','2#20260807-090')
               OR meltno LIKE '%-089' OR meltno LIKE '%-090'
            ORDER BY open_ts DESC NULLS LAST
        """).fetchall()
        for row in rows:
            print(dict(row))
        print("IMES_OUTPUT")
        rows = conn.execute("""
            SELECT meltno,workDate,openTime,closeTime,tappingTime,
                   takesampletime,judgetime,value_01,value_02,value_03,
                   value_04,value_05,batchno,id
            FROM bf_imes.imes_bf2_output_list_cond_data
            WHERE meltno LIKE '%-089' OR meltno LIKE '%-090'
            ORDER BY openTime DESC NULLS LAST
            LIMIT 100
        """).fetchall()
        for row in rows:
            print(dict(row))
        print("HEAT_LAB")
        rows = conn.execute("""
            SELECT meltno,workDate,sumBatch,inspElemName,receivesampletime,
                   publishtime,value_01,value_02,value_03,batchno,id
            FROM bf_imes.imes_bf2_heat_lab_list_cond_data_avg2
            WHERE meltno LIKE '%-089' OR meltno LIKE '%-090'
            ORDER BY publishtime DESC NULLS LAST
            LIMIT 200
        """).fetchall()
        for row in rows:
            print(dict(row))
