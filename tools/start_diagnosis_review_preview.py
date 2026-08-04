#!/usr/bin/env python3
"""Start the isolated local diagnosis-review prototype on 8096/8769."""

from __future__ import annotations

import argparse
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "高炉前端数据"
BACKEND = FRONTEND / "智能助手" / "backend" / "ollama_proxy_server.py"
BRIDGE = ROOT / "自动诊断服务" / "local_pg_ws_bridge.py"


def port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex((host, port)) != 0


def require_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"缺少环境变量 {name}")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="启动本机异常炉况诊断复核原型（不修改220.12）")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8096)
    parser.add_argument("--ws-port", type=int, default=8769)
    parser.add_argument("--fixture-only", action="store_true", help="只启动页面/API与本机测试场景，不连接实时桥接")
    parser.add_argument("--no-test-mode", action="store_true", help="关闭本机测试场景接口")
    parser.add_argument("--ollama-base-url", default="http://10.30.220.12:11434")
    args = parser.parse_args(argv)

    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("本地复核原型只允许绑定回环地址")
    for port in ([args.port] if args.fixture_only else [args.port, args.ws_port]):
        if not port_is_free(args.host, port):
            raise RuntimeError(f"本机端口 {port} 已被占用")

    env = os.environ.copy()
    local_packages = ROOT / ".tmp_pylibs"
    if local_packages.is_dir():
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(local_packages) + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
    env.update({
        "BF_PROXY_HOST": args.host,
        "BF_PROXY_PORT": str(args.port),
        "BF_FRONTEND_DIR": str(FRONTEND),
        "BF_INDEX_FILE": "frontend_dashboard_v3.server.html",
        "OLLAMA_BASE_URL": args.ollama_base_url.rstrip("/"),
        "BF_DIAGNOSIS_REVIEW_ENABLED": "1",
        "BF_DIAGNOSIS_REVIEW_TEST_MODE": "0" if args.no_test_mode else "1",
        "BF_DIAG_REVIEW_PGHOST": env.get("BF_DIAG_REVIEW_PGHOST", "127.0.0.1"),
        "BF_DIAG_REVIEW_PGPORT": env.get("BF_DIAG_REVIEW_PGPORT", "18000"),
        "BF_DIAG_REVIEW_PGDATABASE": env.get("BF_DIAG_REVIEW_PGDATABASE", "bf_trend"),
        "BF_DIAG_REVIEW_PGUSER": env.get("BF_DIAG_REVIEW_PGUSER", "postgres"),
        "BF_DIAG_REVIEW_ALLOWED_ROLES": env.get("BF_DIAG_REVIEW_ALLOWED_ROLES", "高组长"),
        "BF_LOGIN_USERS": env.get("BF_LOGIN_USERS", "zhgl"),
        "BF_LOGIN_ZHGL_ROLE": env.get("BF_LOGIN_ZHGL_ROLE", "高组长"),
        "BF_AUTH_SESSION_SECRET": env.get("BF_AUTH_SESSION_SECRET", secrets.token_urlsafe(48)),
        "BF_SKIP_ASSISTANT_STARTUP": "1",
    })
    env["BF_DIAG_REVIEW_PGPASSWORD"] = require_env("BF_DIAG_REVIEW_PGPASSWORD")
    env["BF_LOGIN_ZHGL_PASSWORD"] = require_env("BF_LOGIN_ZHGL_PASSWORD")

    children: list[subprocess.Popen] = []
    try:
        if not args.fixture_only:
            env["GL02_PGHOST"] = "10.30.220.12"
            env["GL02_PGPORT"] = "5432"
            env["GL02_PGDATABASE"] = "bf_trend"
            env["GL02_PGUSER"] = "gl02_reader"
            env["GL02_PGPASSWORD"] = require_env("GL02_PGPASSWORD")
            bridge_env = env.copy()
            bridge_env.update({"BF_WS_HOST": args.host, "BF_WS_PORT": str(args.ws_port)})
            children.append(subprocess.Popen([sys.executable, str(BRIDGE)], cwd=ROOT, env=bridge_env))
        children.append(subprocess.Popen([sys.executable, str(BACKEND)], cwd=ROOT, env=env))
        page = f"http://{args.host}:{args.port}/diagnosis_review_local_test.html"
        live = f"http://{args.host}:{args.port}/frontend_dashboard_v3.server.html?ws_port={args.ws_port}"
        print(f"本机测试场景：{page}")
        if not args.fixture_only:
            print(f"本机实时页面：{live}")
        print("按 Ctrl+C 停止本次启动的本机进程。")
        while True:
            failed = next((child for child in children if child.poll() is not None), None)
            if failed:
                return int(failed.returncode or 1)
            time.sleep(1)
    except KeyboardInterrupt:
        return 0
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()


if __name__ == "__main__":
    raise SystemExit(main())
