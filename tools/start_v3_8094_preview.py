"""Serve the current local V3 page on port 8094 without touching 8093."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "高炉前端数据"
BACKEND = FRONTEND_DIR / "智能助手" / "backend" / "ollama_proxy_server.py"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8094)
    args = parser.parse_args()

    if not BACKEND.is_file():
        raise FileNotFoundError(f"Missing backend entry: {BACKEND}")

    env = os.environ.copy()
    env.update(
        {
            "PYTHONUTF8": "1",
            "PYTHONUNBUFFERED": "1",
            "BF_PROXY_HOST": args.host,
            "BF_PROXY_PORT": str(args.port),
            "BF_FRONTEND_DIR": str(FRONTEND_DIR),
            "BF_INDEX_FILE": "frontend_dashboard_v3.server.html",
        }
    )
    return subprocess.call(
        [sys.executable, "-X", "utf8", "-u", str(BACKEND)],
        cwd=str(ROOT),
        env=env,
    )


if __name__ == "__main__":
    raise SystemExit(main())
