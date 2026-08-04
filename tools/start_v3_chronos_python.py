from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    root = project_root()
    parser = argparse.ArgumentParser(description="Start the V3 Chronos prediction HTTP service.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8777)
    parser.add_argument("--engine", choices=["local-script", "http-proxy", "constant"], default="local-script")
    parser.add_argument("--upstream-base-url", default="")
    parser.add_argument("--chronos-python", default="")
    parser.add_argument("--chronos-dtype", default=os.environ.get("BF_CHRONOS_DTYPE", "float32"))
    parser.add_argument("--chronos-device", default=os.environ.get("BF_CHRONOS_DEVICE", "cpu"))
    parser.add_argument("--model-path", default=str(root / "chronos外推预测" / "chronos-v2"))
    parser.add_argument(
        "--chronos-script",
        default=str(root / "chronos外推预测" / "src" / "inference" / "live_chronos_predict.py"),
    )
    parser.add_argument("--timeout-seconds", type=float, default=900)
    parser.add_argument(
        "--service-script",
        default=str(root / "趋势分析" / "trend_backend" / "chronos_prediction_service.py"),
    )
    args = parser.parse_args(argv)

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    env["BF_CHRONOS_HOST"] = args.host
    env["BF_CHRONOS_PORT"] = str(args.port)
    env["BF_CHRONOS_ENGINE"] = args.engine
    env["BF_CHRONOS_MODEL_PATH"] = args.model_path
    env["BF_CHRONOS_SCRIPT"] = args.chronos_script
    env["BF_CHRONOS_TIMEOUT_SECONDS"] = str(args.timeout_seconds)
    env["BF_CHRONOS_DTYPE"] = args.chronos_dtype
    env["BF_CHRONOS_DEVICE"] = args.chronos_device
    if args.upstream_base_url:
        env["BF_CHRONOS_UPSTREAM_BASE_URL"] = args.upstream_base_url.rstrip("/")
    if args.chronos_python:
        env["BF_CHRONOS_PYTHON"] = args.chronos_python

    print(f"Starting Chronos service: http://{args.host}:{args.port}")
    print(f"Chronos engine: {args.engine}")
    if args.engine == "http-proxy":
        print(f"Chronos upstream: {env.get('BF_CHRONOS_UPSTREAM_BASE_URL', '')}")
    else:
        print(f"Chronos model path: {args.model_path}")
    return subprocess.call([sys.executable, args.service_script], cwd=str(root), env=env)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
