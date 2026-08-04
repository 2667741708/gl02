#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Run the 220.12 PostgreSQL -> local Docker PostgreSQL sync loop.

This Python launcher is the preferred local entry when the workspace path
contains non-ASCII characters. It avoids PowerShell pipeline execution of the
virtualenv Python path, which can fail before the sync script starts.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"
SYNC_SCRIPT = ROOT / "tools" / "sync_22012_pg_to_local.py"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DETACHED_PROCESS = getattr(subprocess, "DETACHED_PROCESS", 0)


def utcish_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def append_line(path: Path, item: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", errors="replace") as fh:
        if isinstance(item, str):
            fh.write(item.rstrip("\n") + "\n")
        else:
            fh.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")


def default_python() -> str:
    venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def build_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("GL02_LOCAL_PGHOST", "127.0.0.1")
    env.setdefault("GL02_LOCAL_PGPORT", "15432")
    env.setdefault("GL02_LOCAL_PGDATABASE", "bf_trend")
    env.setdefault("GL02_LOCAL_PGUSER", "gl02_sync")
    env.setdefault("GL02_LOCAL_PGPASSWORD", "gl02_local_sync")
    return env


def run_once(args: argparse.Namespace, log_path: Path) -> int:
    append_line(log_path, {"event": "sync_start", "started_at": utcish_now(), "launcher": "python"})
    cmd = [
        sys.executable,
        str(SYNC_SCRIPT),
        "--batch-size",
        str(args.batch_size),
        "--local-tunnel-port",
        str(args.local_tunnel_port),
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            env=build_env(),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=args.sync_timeout_seconds,
        )
        if proc.stdout:
            append_line(log_path, proc.stdout.rstrip("\n"))
        status = "ok" if proc.returncode == 0 else "failed"
        append_line(
            log_path,
            {
                "event": "sync_finish",
                "finished_at": utcish_now(),
                "status": status,
                "returncode": proc.returncode,
            },
        )
        return proc.returncode
    except Exception as exc:  # noqa: BLE001
        append_line(
            log_path,
            {
                "event": "sync_error",
                "finished_at": utcish_now(),
                "error": str(exc),
            },
        )
        return 1


def start_background(args: argparse.Namespace) -> int:
    """Relaunch this sync loop detached from the interactive console.

    The visible black Python window appears when the loop is started by a
    normal console Python. This branch starts the same loop with redirected
    output and Windows no-window flags so it can keep syncing quietly.
    """

    log_path = Path(args.background_log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("a", encoding="utf-8", errors="replace")
    cmd = [
        default_python(),
        str(Path(__file__).resolve()),
        "--interval-seconds",
        str(args.interval_seconds),
        "--batch-size",
        str(args.batch_size),
        "--local-tunnel-port",
        str(args.local_tunnel_port),
        "--sync-timeout-seconds",
        str(args.sync_timeout_seconds),
        "--log-file",
        str(args.log_file),
    ]
    if args.once:
        cmd.append("--once")
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        env=build_env(),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
    )
    print(f"Started hidden local PostgreSQL sync loop, PID={proc.pid}, log={log_path}", flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Start the local PostgreSQL sync loop using Python only.")
    parser.add_argument("--interval-seconds", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=10000)
    parser.add_argument("--local-tunnel-port", type=int, default=56432)
    parser.add_argument("--sync-timeout-seconds", type=int, default=1800)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--log-file", default=str(LOG_DIR / "local_pg_sync_loop.jsonl"))
    parser.add_argument("--background", action="store_true", help="Relaunch the loop hidden and exit.")
    parser.add_argument("--background-log-file", default=str(LOG_DIR / "local_pg_sync_loop_background.log"))
    args = parser.parse_args()

    if not SYNC_SCRIPT.exists():
        raise SystemExit(f"missing sync script: {SYNC_SCRIPT}")

    if args.background:
        return start_background(args)

    log_path = Path(args.log_file)
    interval = max(30, args.interval_seconds)
    print("Starting local PostgreSQL sync loop", flush=True)
    print("Remote PostgreSQL: administrator@10.30.220.12 -> 127.0.0.1:5432/bf_trend", flush=True)
    print(f"Local tunnel: 127.0.0.1:{args.local_tunnel_port}", flush=True)
    print("Local PostgreSQL: 127.0.0.1:15432/bf_trend", flush=True)
    print(f"Interval seconds: {interval}", flush=True)
    print(f"Log file: {log_path}", flush=True)
    while True:
        run_once(args, log_path)
        if args.once:
            return 0
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
