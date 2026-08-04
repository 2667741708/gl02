#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Start the GL02 database dashboard with Python-only operations.

The dashboard itself reads its database connection from GL02_PG* environment
variables.  This launcher keeps the local-development defaults explicit and
allows a clean restart without using PowerShell wrappers.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def default_python() -> str:
    venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def port_open(host: str, port: int, timeout: float = 0.8) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_http(url: str, timeout_seconds: int) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=3) as resp:
                if 200 <= resp.status < 300:
                    return True
        except (OSError, URLError):
            time.sleep(1)
    return False


def stop_port(port: int) -> None:
    stop_script = ROOT / "tools" / "stop_local_ports_python.py"
    if not stop_script.exists():
        return
    subprocess.run(
        [default_python(), str(stop_script), "--ports", str(port)],
        cwd=str(ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def ensure_local_postgres() -> bool:
    tools_dir = ROOT / "tools"
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    try:
        from start_v3_full_python import ensure_local_postgres as ensure_pg  # type: ignore
    except Exception as exc:  # noqa: BLE001
        print(f"warning: cannot import local PostgreSQL helper: {exc}", flush=True)
        return False
    return bool(ensure_pg())


def build_env(args: argparse.Namespace) -> dict[str, str]:
    env = os.environ.copy()
    if args.db_profile == "local":
        env.update(
            {
                "GL02_PGHOST": "127.0.0.1",
                "GL02_PGPORT": "15432",
                "GL02_PGDATABASE": "bf_trend",
                "GL02_PGUSER": "gl02_sync",
                "GL02_PGPASSWORD": "gl02_local_sync",
            }
        )
    env["BF_DB_DASHBOARD_HOST"] = args.host
    env["BF_DB_DASHBOARD_PORT"] = str(args.port)
    env["BF_DB_DASHBOARD_SYNC_INTERVAL_SECONDS"] = str(args.sync_interval_seconds)
    return env


def main() -> int:
    parser = argparse.ArgumentParser(description="Start the GL02 database dashboard on port 8890.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8890)
    parser.add_argument(
        "--db-profile",
        choices=["local", "env"],
        default="local",
        help="local sets 127.0.0.1:15432/gl02_sync; env preserves existing GL02_PG* values.",
    )
    parser.add_argument("--sync-interval-seconds", type=int, default=300)
    parser.add_argument(
        "--no-ensure-local-postgres",
        action="store_true",
        help="Do not try to start/check the local Docker PostgreSQL container when --db-profile local is used.",
    )
    parser.add_argument("--restart", action="store_true", help="Stop an existing listener on the target port first.")
    parser.add_argument("--foreground", action="store_true", help="Run server.py in the foreground.")
    parser.add_argument("--wait-seconds", type=int, default=20)
    parser.add_argument("--log-file", default=str(LOG_DIR / "db_dashboard_8890_python.log"))
    args = parser.parse_args()

    server_script = ROOT / "db_dashboard" / "server.py"
    if not server_script.exists():
        print(f"missing server script: {server_script}", flush=True)
        return 2

    if args.restart:
        stop_port(args.port)

    if args.db_profile == "local" and not args.no_ensure_local_postgres:
        ensure_local_postgres()

    if port_open(args.host, args.port) and not args.foreground:
        print(f"already running: http://{args.host}:{args.port}/", flush=True)
        return 0

    env = build_env(args)
    cmd = [default_python(), str(server_script)]

    if args.foreground:
        os.execve(cmd[0], cmd, env)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = Path(args.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("a", encoding="utf-8")
    subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        creationflags=CREATE_NO_WINDOW,
    )

    url = f"http://{args.host}:{args.port}/"
    if wait_http(url, args.wait_seconds):
        print(f"started: http://{args.host}:{args.port}/", flush=True)
        print(f"liveness: {url}", flush=True)
        print(
            f"data health: http://{args.host}:{args.port}/api/overview",
            flush=True,
        )
        print(f"log: {log_path}", flush=True)
        return 0

    print(f"started process, but health check did not pass within {args.wait_seconds}s", flush=True)
    print(f"log: {log_path}", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
