"""Add time-repair lineage and future-isolation columns to the heat summary.

This migration is idempotent.  It keeps ``open_ts``/``close_ts`` as the
effective timestamps consumed by 8093, while adding provenance columns for the
original MES timestamps and the repaired timestamps inferred during IMES
back-check synchronization.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_hot_metal_si_dataset as tunnel_builder  # noqa: E402


DDL = """
ALTER TABLE bf_assistant.heat_performance_quality_summary
    ADD COLUMN IF NOT EXISTS raw_open_ts timestamp without time zone;
ALTER TABLE bf_assistant.heat_performance_quality_summary
    ADD COLUMN IF NOT EXISTS raw_close_ts timestamp without time zone;
ALTER TABLE bf_assistant.heat_performance_quality_summary
    ADD COLUMN IF NOT EXISTS repaired_open_ts timestamp without time zone;
ALTER TABLE bf_assistant.heat_performance_quality_summary
    ADD COLUMN IF NOT EXISTS repaired_close_ts timestamp without time zone;
ALTER TABLE bf_assistant.heat_performance_quality_summary
    ADD COLUMN IF NOT EXISTS time_anomaly_reasons jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE bf_assistant.heat_performance_quality_summary
    ADD COLUMN IF NOT EXISTS repair_checked_at timestamp with time zone;
ALTER TABLE bf_assistant.heat_performance_quality_summary
    ADD COLUMN IF NOT EXISTS future_pending boolean NOT NULL DEFAULT false;
UPDATE bf_assistant.heat_performance_quality_summary
SET raw_open_ts = COALESCE(raw_open_ts, open_ts),
    raw_close_ts = COALESCE(raw_close_ts, close_ts)
WHERE raw_open_ts IS NULL OR raw_close_ts IS NULL;
UPDATE bf_assistant.heat_performance_quality_summary
SET repaired_open_ts = COALESCE(repaired_open_ts, open_ts),
    repaired_close_ts = COALESCE(repaired_close_ts, close_ts)
WHERE source_status = 'time_anomaly_repaired'
  AND (repaired_open_ts IS NULL OR repaired_close_ts IS NULL);
"""


def _ns(port: int) -> argparse.Namespace:
    return argparse.Namespace(
        ssh_host="10.30.220.12",
        ssh_user="administrator",
        remote_pg_host="127.0.0.1",
        remote_pg_port=5432,
        local_tunnel_port=port,
        remote_pg_user="gl02_sync",
        remote_pg_db="bf_trend",
        connect_timeout=20,
    )


def _column_audit(conn: psycopg.Connection[Any]) -> list[dict[str, Any]]:
    return list(
        conn.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'bf_assistant'
              AND table_name = 'heat_performance_quality_summary'
              AND column_name IN (
                  'raw_open_ts', 'raw_close_ts',
                  'repaired_open_ts', 'repaired_close_ts',
                  'time_anomaly_reasons', 'repair_checked_at', 'future_pending',
                  'open_ts', 'close_ts'
              )
            ORDER BY column_name
            """
        ).fetchall()
    )


def _repair_audit(conn: psycopg.Connection[Any]) -> list[dict[str, Any]]:
    return list(
        conn.execute(
            """
            SELECT meltno, open_ts, close_ts, raw_open_ts, raw_close_ts,
                   repaired_open_ts, repaired_close_ts, source_status,
                   time_anomaly_reasons, repair_checked_at, future_pending
            FROM bf_assistant.heat_performance_quality_summary
            WHERE source_status IN ('time_anomaly_repaired', 'future_pending')
            ORDER BY open_ts DESC NULLS LAST
            LIMIT 20
            """
        ).fetchall()
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Idempotently migrate 220.12 heat quality time repair audit columns."
    )
    parser.add_argument("--local-tunnel-port", type=int, default=15438)
    args = parser.parse_args()
    ns = _ns(args.local_tunnel_port)
    with tunnel_builder.sensor_ssh_tunnel(ns) as (port, client):
        params = tunnel_builder.remote_sensor_params(ns, port, client)
        params["options"] = "-c statement_timeout=120000"
        with psycopg.connect(**params, row_factory=dict_row) as conn:
            conn.execute(DDL)
            conn.commit()
            result = {
                "ok": True,
                "columns": _column_audit(conn),
                "repaired_rows": _repair_audit(conn),
            }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
