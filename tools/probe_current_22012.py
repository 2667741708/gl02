from __future__ import annotations

import argparse
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_hot_metal_si_dataset as b  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--local-tunnel-port", type=int, default=15435)
    args = p.parse_args()
    ns = argparse.Namespace(
        ssh_host="10.30.220.12", ssh_user="administrator", remote_pg_host="127.0.0.1",
        remote_pg_port=5432, local_tunnel_port=args.local_tunnel_port,
        remote_pg_user="gl02_sync", remote_pg_db="bf_trend", connect_timeout=20,
    )
    with b.sensor_ssh_tunnel(ns) as (port, client):
        params = b.remote_sensor_params(ns, port, client)
        params["options"] = "-c default_transaction_read_only=on -c statement_timeout=30000"
        with psycopg.connect(**params, row_factory=dict_row) as conn:
            tables = conn.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema') ORDER BY 1,2").fetchall()
            print("TABLES")
            for row in tables:
                print(f"{row['table_schema']}.{row['table_name']}")
            for table in tables:
                schema = table["table_schema"]
                name = table["table_name"]
                cols = conn.execute("SELECT column_name,data_type FROM information_schema.columns WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position", (schema, name)).fetchall()
                text = ", ".join(f"{x['column_name']}:{x['data_type']}" for x in cols)
                if any(k in text.lower() for k in ("melt", "heat", "silicon", "si", "sample")):
                    print(f"COLUMNS {schema}.{name}: {text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
