from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Start the 8778 multi-model time-series benchmark sidecar.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8778)
    parser.add_argument("--chronos-url", default="http://127.0.0.1:8777")
    parser.add_argument("--default-model", choices=["last_value", "linear_drift", "ridge_delta", "chronos2"], default="last_value")
    parser.add_argument("--model-dir", default=str(root / "PT" / "时间序列预测评测" / "models"))
    parser.add_argument("--leaderboard-file", default=str(root / "PT" / "时间序列预测评测" / "results" / "timeseries_model_leaderboard_current.json"))
    parser.add_argument("--log-file", default=str(root / "logs" / "timeseries_sidecar_8778.log"))
    args = parser.parse_args()
    command = [
        sys.executable,
        str(root / "tools" / "timeseries_sidecar_service.py"),
        "--host", args.host,
        "--port", str(args.port),
        "--chronos-url", args.chronos_url,
        "--default-model", args.default_model,
        "--model-dir", args.model_dir,
        "--leaderboard-file", args.leaderboard_file,
        "--log-file", args.log_file,
    ]
    return subprocess.call(command, cwd=str(root))


if __name__ == "__main__":
    raise SystemExit(main())
