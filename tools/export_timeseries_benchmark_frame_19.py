from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import os
from pathlib import Path

from select_and_backtest_chronos_main_variables_19 import load_core_frame


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a credential-free 19-target frame for remote model benchmarks.")
    parser.add_argument("--db-host", default="10.30.220.12")
    parser.add_argument("--db-port", type=int, default=5432)
    parser.add_argument("--db-name", default="bf_trend")
    parser.add_argument("--db-user", default="gl02_reader")
    parser.add_argument("--db-password-env", default="GL02_PGPASSWORD")
    parser.add_argument("--hours", type=float, default=72.0)
    parser.add_argument("--output", default=str(ROOT / "PT" / "时间序列预测评测" / "timeseries_benchmark_frame_19.csv"))
    args = parser.parse_args()
    password = os.environ.get(args.db_password_env, "")
    if not password:
        raise SystemExit(f"missing database password environment variable: {args.db_password_env}")
    params = {
        "host": args.db_host,
        "port": args.db_port,
        "dbname": args.db_name,
        "user": args.db_user,
        "password": password,
        "connect_timeout": 12,
    }
    frame = load_core_frame(params, datetime.now() - timedelta(hours=args.hours), datetime.now())
    if frame.empty:
        raise SystemExit("no benchmark frame was loaded")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.index.name = "ts"
    frame.to_csv(output, encoding="utf-8")
    print(f"FRAME {output} rows={len(frame)} columns={len(frame.columns)} start={frame.index.min()} end={frame.index.max()}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
