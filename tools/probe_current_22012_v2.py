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
    p.add_argument("--local-tunnel-port", type=int, default=15436)
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
            rows = conn.execute("""
                SELECT meltno,furnace_no,open_ts,close_ts,first_sample_ts,last_sample_ts,
                       si_avg,si_min,si_max,hot_metal_sample_count,quality_status,source_updated_at
                FROM bf_assistant.heat_performance_quality_summary
                WHERE furnace_no='2' AND open_ts >= timestamp '2026-08-01'
                ORDER BY open_ts DESC LIMIT 120
            """).fetchall()
            print("LATEST_HEATS")
            for row in rows:
                print("|".join(str(row.get(k) if row.get(k) is not None else "") for k in (
                    "meltno","open_ts","close_ts","first_sample_ts","last_sample_ts","si_avg","si_min","si_max","hot_metal_sample_count","quality_status","source_updated_at")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
