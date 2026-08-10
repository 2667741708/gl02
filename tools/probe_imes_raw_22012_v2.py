from pathlib import Path
import sys, psycopg
from psycopg.rows import dict_row
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import build_hot_metal_si_dataset as b
ns=type('N',(),dict(ssh_host='10.30.220.12',ssh_user='administrator',remote_pg_host='127.0.0.1',remote_pg_port=5432,local_tunnel_port=15443,remote_pg_user='gl02_sync',remote_pg_db='bf_trend',connect_timeout=20))()
with b.sensor_ssh_tunnel(ns) as (port,client):
 p=b.remote_sensor_params(ns,port,client); p['options']='-c default_transaction_read_only=on -c statement_timeout=60000'
 with psycopg.connect(**p,row_factory=dict_row) as c:
  rows=c.execute("SELECT dataset_key,row_key,dataset_label,endpoint,workdate,lot,charge,row_json,fetched_at FROM bf_imes.raw_rows WHERE row_json::text LIKE '%20260807-089%' OR row_json::text LIKE '%20260807-090%' LIMIT 20").fetchall(); print([dict(x) for x in rows])
