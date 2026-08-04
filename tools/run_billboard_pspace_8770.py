# -*- coding: utf-8 -*-
"""Run the dedicated 133-point Billboard pSpace WebSocket on port 8770.

The remote V3 runtime already contains the vendor SDK and its site-local
read-only credential sample.  This supervisor extracts those credentials into
the child process environment without printing or copying them into repository
files, then restarts the bridge after an unexpected exit.
"""

from __future__ import annotations

import ast
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
PYTHON = Path(r"C:\Program Files\Python311\python.exe")
SDK_ROOT = ROOT_DIR / "pythonSDK(1)"
CREDENTIAL_SAMPLE = SDK_ROOT / "read_sensor_data.py"
BRIDGE = ROOT_DIR / "tools" / "pspace_8092_realtime_bridge.py"
LOG_DIR = ROOT_DIR / "logs"
OUT_LOG = LOG_DIR / "billboard_pspace_8770.out.log"
ERR_LOG = LOG_DIR / "billboard_pspace_8770.err.log"
STOP_REQUESTED = False


def _literal_assignment(source: str, name: str) -> str | None:
    match = re.search(rf"(?m)^\s*{re.escape(name)}\s*=\s*(.+?)\s*$", source)
    if not match:
        return None
    try:
        value = ast.literal_eval(match.group(1))
    except (SyntaxError, ValueError):
        return None
    return value if isinstance(value, str) and value else None


def load_credentials() -> tuple[str, str]:
    source = CREDENTIAL_SAMPLE.read_text(encoding="utf-8-sig")
    user = _literal_assignment(source, "DEFAULT_USER")
    password = _literal_assignment(source, "DEFAULT_PASSWORD")
    if not user or not password:
        raise RuntimeError("Site-local pSpace read-only credentials were not found")
    return user, password


def request_stop(_signum: int, _frame: object) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True


def main() -> int:
    for required in (PYTHON, SDK_ROOT / "PythonAPI" / "PsServer.py", CREDENTIAL_SAMPLE, BRIDGE):
        if not required.exists():
            raise SystemExit(f"Required runtime path is missing: {required}")

    user, password = load_credentials()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "PYTHONUTF8": "1",
            "PSPACE_USER": user,
            "PSPACE_PASSWORD": password,
            "PSPACE_SDK_ROOT": str(SDK_ROOT),
            "PSPACE_POLL_SECONDS": "1",
            "PSPACE_REALREAD_BATCH_SIZE": "100",
        }
    )
    command = [
        str(PYTHON),
        "-X",
        "utf8",
        "-u",
        str(BRIDGE),
        "--serve",
        "--host",
        "0.0.0.0",
        "--port",
        "8770",
        "--poll-seconds",
        "1",
        "--no-history",
        "--no-diagnosis",
        "--snapshot-interval-seconds",
        "0",
    ]

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    while not STOP_REQUESTED:
        with OUT_LOG.open("a", encoding="utf-8") as stdout, ERR_LOG.open("a", encoding="utf-8") as stderr:
            stdout.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] starting Billboard pSpace bridge\n")
            stdout.flush()
            process = subprocess.Popen(command, cwd=str(ROOT_DIR), env=env, stdout=stdout, stderr=stderr)
            while process.poll() is None and not STOP_REQUESTED:
                time.sleep(1)
            if STOP_REQUESTED and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            return_code = process.returncode
        if STOP_REQUESTED:
            break
        time.sleep(5 if return_code else 2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
