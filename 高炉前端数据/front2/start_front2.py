from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path


FRONT2_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = FRONT2_DIR.parent
PROJECT_ROOT = FRONTEND_DIR.parent
BACKEND = FRONTEND_DIR / "智能助手" / "backend" / "ollama_proxy_server.py"
INDEX_FILE = "front2/frontend_dashboard_front2.server.html"
STATE_FILE = PROJECT_ROOT / "logs" / "front2_8094.state.json"
LOCAL_PACKAGES = FRONT2_DIR / ".python_packages"


def port_available(host: str, port: int) -> bool:
    probe_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    family = socket.AF_INET6 if ":" in probe_host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((probe_host, port)) != 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the isolated front2 UI with the existing blast-furnace backend entry."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8094)
    parser.add_argument("--ws-port", type=int, default=8767)
    parser.add_argument("--strictPort", "--strict-port", action="store_true")
    parser.add_argument("--detached", action="store_true", help="Start hidden in the background and return.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not BACKEND.is_file():
        raise FileNotFoundError(f"Backend entry is missing: {BACKEND}")
    if not (FRONT2_DIR / "frontend_dashboard_front2.server.html").is_file():
        raise FileNotFoundError("front2 HTML entry is missing")
    if not port_available(args.host, args.port):
        print(f"Port {args.port} is already in use; front2 was not started.", file=sys.stderr)
        return 2

    if args.detached:
        logs_dir = PROJECT_ROOT / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        out_log = logs_dir / "front2_8094.out.log"
        err_log = logs_dir / "front2_8094.err.log"
        command = [
            sys.executable,
            "-X",
            "utf8",
            "-u",
            str(Path(__file__).resolve()),
            "--host",
            args.host,
            "--port",
            str(args.port),
            "--ws-port",
            str(args.ws_port),
            "--strictPort",
        ]
        creationflags = 0
        popen_options: dict[str, object] = {"close_fds": True}
        if os.name == "nt":
            creationflags = (
                subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.DETACHED_PROCESS
                | subprocess.CREATE_NO_WINDOW
            )
        else:
            popen_options["start_new_session"] = True
        with out_log.open("ab") as stdout, err_log.open("ab") as stderr:
            process = subprocess.Popen(
                command,
                cwd=str(FRONT2_DIR),
                stdout=stdout,
                stderr=stderr,
                creationflags=creationflags,
                **popen_options,
            )
        print(
            json.dumps(
                {
                    "ok": True,
                    "launcher_pid": process.pid,
                    "url": f"http://{args.host}:{args.port}/?ws_port={args.ws_port}#overview",
                    "stdout": str(out_log),
                    "stderr": str(err_log),
                },
                ensure_ascii=False,
            )
        )
        return 0

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env["BF_PROXY_HOST"] = args.host
    env["BF_PROXY_PORT"] = str(args.port)
    env["BF_FRONTEND_DIR"] = str(FRONTEND_DIR)
    env["BF_INDEX_FILE"] = INDEX_FILE
    if LOCAL_PACKAGES.is_dir():
        current_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = os.pathsep.join(
            part for part in (str(LOCAL_PACKAGES), current_pythonpath) if part
        )
    env.setdefault("GL02_PGHOST", "127.0.0.1")
    env.setdefault("GL02_PGPORT", "5443")
    env.setdefault("GL02_PGDATABASE", "bf_trend")

    command = [sys.executable, "-X", "utf8", "-u", str(BACKEND)]
    child = subprocess.Popen(command, cwd=str(PROJECT_ROOT), env=env)
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(
            {
                "pid": child.pid,
                "host": args.host,
                "port": args.port,
                "ws_port": args.ws_port,
                "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "backend": str(BACKEND),
                "index_file": INDEX_FILE,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"front2 preview: http://{args.host}:{args.port}/?ws_port={args.ws_port}#overview")
    print(f"backend entry: {BACKEND}")
    try:
        return child.wait()
    except KeyboardInterrupt:
        child.terminate()
        try:
            return child.wait(timeout=8)
        except subprocess.TimeoutExpired:
            child.kill()
            return child.wait()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
