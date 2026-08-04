from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


DB_PROFILES: dict[str, dict[str, str]] = {
    "local": {
        "GL02_PGHOST": "127.0.0.1",
        "GL02_PGPORT": "15432",
        "GL02_PGDATABASE": "bf_trend",
        "GL02_PGUSER": "gl02_sync",
        "GL02_PGPASSWORD": "gl02_local_sync",
        "BF_WS_READ_POLICY": "local_database_primary_synced_from_22012",
    },
    "22012": {
        "GL02_PGHOST": "10.30.220.12",
        "GL02_PGPORT": "5432",
        "GL02_PGDATABASE": "bf_trend",
        "GL02_PGUSER": "gl02_reader",
        "BF_WS_READ_POLICY": "readonly_22012_postgresql",
    },
}


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def apply_db_profile(env: dict[str, str], args: argparse.Namespace) -> None:
    if args.db_profile in DB_PROFILES:
        env.update(DB_PROFILES[args.db_profile])

    if args.db_host:
        env["GL02_PGHOST"] = args.db_host
    if args.db_port:
        env["GL02_PGPORT"] = str(args.db_port)
    if args.db_name:
        env["GL02_PGDATABASE"] = args.db_name
    if args.db_user:
        env["GL02_PGUSER"] = args.db_user

    if args.db_password:
        env["GL02_PGPASSWORD"] = args.db_password
    elif args.db_password_env and (args.db_profile != "local" or not env.get("GL02_PGPASSWORD")):
        password = os.environ.get(args.db_password_env, "")
        if password:
            env["GL02_PGPASSWORD"] = password


def main(argv: list[str] | None = None) -> int:
    root = project_root()
    parser = argparse.ArgumentParser(description="Start the V3 8767 WebSocket bridge with a selected database backend.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default="8767")
    parser.add_argument("--history-hours", default="8")
    parser.add_argument("--tick-seconds", default="30")
    parser.add_argument("--chronos-base-url", default=os.environ.get("BF_CHRONOS_BASE_URL", ""))
    parser.add_argument("--chronos-timeout-seconds", default=os.environ.get("BF_CHRONOS_TIMEOUT_SECONDS", "900"))
    parser.add_argument("--db-profile", choices=["inherit", "local", "22012", "custom"], default="local")
    parser.add_argument("--db-host", default="")
    parser.add_argument("--db-port", default="")
    parser.add_argument("--db-name", default="")
    parser.add_argument("--db-user", default="")
    parser.add_argument("--db-password", default="")
    parser.add_argument("--db-password-env", default="GL02_PGPASSWORD")
    parser.add_argument(
        "--bridge-script",
        default=str(root / "自动诊断服务" / "local_pg_ws_bridge.py"),
    )
    args = parser.parse_args(argv)

    env = os.environ.copy()
    env["BF_WS_HOST"] = args.host
    env["BF_WS_PORT"] = str(args.port)
    env["BF_WS_HISTORY_HOURS"] = str(args.history_hours)
    env["BF_WS_TICK_SECONDS"] = str(args.tick_seconds)
    if args.chronos_base_url:
        env["BF_CHRONOS_BASE_URL"] = args.chronos_base_url.rstrip("/")
    else:
        env.pop("BF_CHRONOS_BASE_URL", None)
    env["BF_CHRONOS_TIMEOUT_SECONDS"] = str(args.chronos_timeout_seconds)
    apply_db_profile(env, args)

    print(f"Starting V3 WebSocket bridge: ws://{args.host}:{args.port}")
    print(
        "Database: "
        f"{env.get('GL02_PGUSER', '')}@{env.get('GL02_PGHOST', '')}:"
        f"{env.get('GL02_PGPORT', '')}/{env.get('GL02_PGDATABASE', '')}"
    )
    print(f"Chronos service: {env.get('BF_CHRONOS_BASE_URL', '(disabled)')}")
    return subprocess.call([sys.executable, args.bridge_script], cwd=str(root), env=env)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
