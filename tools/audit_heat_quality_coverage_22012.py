from pathlib import Path
import sys, psycopg
from psycopg.rows import dict_row
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import build_hot_metal_si_dataset as b
ns=type('N',(),dict(ssh_host='10.30.220.12',ssh_user='administrator',remote_pg_host='127.0.0.1',remote_pg_port=5432,local_tunnel_port=15445,remote_pg_user='gl02_sync',remote_pg_db='bf_trend',connect_timeout=20))()
with b.sensor_ssh_tunnel(ns) as (port,client):
 p=b.remote_sensor_params(ns,port,client); p['options']='-c default_transaction_read_only=on -c statement_timeout=60000'
 with psycopg.connect(**p,row_factory=dict_row) as c:
  queries={
   'summary_overall': """SELECT count(*) rows, min(open_ts) min_open, max(open_ts) max_open, count(*) FILTER (WHERE si_avg IS NOT NULL) si_rows, count(*) FILTER (WHERE quality_status='complete') complete_rows, count(*) FILTER (WHERE source_status='time_anomaly_repaired') repaired_rows FROM bf_assistant.heat_performance_quality_summary""",
   'recent_7d': """SELECT count(*) rows, count(*) FILTER (WHERE si_avg IS NOT NULL) si_rows, count(*) FILTER (WHERE source_status='time_anomaly_repaired') repaired_rows FROM bf_assistant.heat_performance_quality_summary WHERE open_ts >= now() - interval '7 days'""",
   'recent_repaired': """SELECT meltno, work_date, open_ts, close_ts, si_avg, source_status FROM bf_assistant.heat_performance_quality_summary WHERE source_status='time_anomaly_repaired' ORDER BY open_ts DESC LIMIT 20""",
   'null_quality_recent': """SELECT meltno, work_date, open_ts, close_ts, quality_status, si_avg, hot_metal_sample_count, output_count, source_status FROM bf_assistant.heat_performance_quality_summary WHERE open_ts >= now() - interval '7 days' AND (si_avg IS NULL OR output_count=0) ORDER BY open_ts DESC LIMIT 30""",
  }
  for name, sql in queries.items():
   rows=c.execute(sql).fetchall(); print(name); [print(dict(r)) for r in rows]
