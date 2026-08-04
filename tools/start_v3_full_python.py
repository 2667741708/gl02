#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Start the local V3 dashboard stack with Python only.

This launcher is intentionally small and explicit:
- local PostgreSQL container is ensured when --db-profile local is used;
- 8767 WebSocket bridge is started through tools/start_v3_ws_bridge_python.py;
- 8092 dashboard/API proxy is started through tools/start_v3_8092_python.py;
- model backend is checked, and local Ollama can be started on request.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from typing import Iterable
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"
LOCAL_PG_CONTAINER = "bf-v3-local-postgres"
LOCAL_PG_COMPOSE = ROOT / "docker-compose.local-postgres.yml"

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def default_python() -> str:
    venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def info(message: str) -> None:
    print(f"[v3-full] {message}", flush=True)


def run(cmd: list[str], *, check: bool = False, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=check,
        timeout=timeout,
    )


def port_open(host: str, port: int, timeout: float = 0.8) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_port(host: str, port: int, timeout_seconds: int, label: str) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if port_open(host, port):
            info(f"{label} 已监听：{host}:{port}")
            return True
        time.sleep(1)
    info(f"警告：{label} 在 {timeout_seconds} 秒内没有监听 {host}:{port}")
    return False


def stop_ports(ports: Iterable[int]) -> None:
    stop_script = ROOT / "tools" / "stop_local_ports_python.py"
    if not stop_script.exists():
        return
    cmd = [default_python(), str(stop_script), "--ports", *[str(p) for p in ports]]
    result = run(cmd, check=False, timeout=60)
    if result.stdout.strip():
        print(result.stdout.strip(), flush=True)
    if result.stderr.strip():
        print(result.stderr.strip(), flush=True)


def ensure_docker_ready(timeout_seconds: int = 90) -> bool:
    docker = shutil.which("docker")
    if not docker:
        info("未找到 docker 命令，无法自动启动本地 PostgreSQL 容器。")
        return False

    if run([docker, "info"], timeout=20).returncode == 0:
        return True

    info("Docker 尚未就绪，尝试通过 Python 启动 Docker Desktop / Docker 服务。")
    docker_desktop = Path(r"C:\Program Files\Docker\Docker\Docker Desktop.exe")
    if docker_desktop.exists():
        subprocess.Popen([str(docker_desktop)], cwd=str(ROOT), creationflags=CREATE_NO_WINDOW)
    run(["sc", "start", "com.docker.service"], timeout=20)

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if run([docker, "info"], timeout=20).returncode == 0:
            return True
        time.sleep(3)
    info("Docker 在等待时间内仍未就绪。")
    return False


def ensure_local_postgres(timeout_seconds: int = 90) -> bool:
    if port_open("127.0.0.1", 15432):
        info("本地 PostgreSQL 端口已可用：127.0.0.1:15432")
        return True

    if not LOCAL_PG_COMPOSE.exists():
        info(f"缺少本地数据库编排文件：{LOCAL_PG_COMPOSE}")
        return False

    if not ensure_docker_ready():
        return False

    docker = shutil.which("docker")
    assert docker

    inspect = run([docker, "inspect", LOCAL_PG_CONTAINER], timeout=20)
    if inspect.returncode == 0:
        info(f"启动已有 PostgreSQL 容器：{LOCAL_PG_CONTAINER}")
        run([docker, "start", LOCAL_PG_CONTAINER], timeout=60)
    else:
        info("创建并启动本地 PostgreSQL 容器。")
        compose = run([docker, "compose", "-f", str(LOCAL_PG_COMPOSE), "up", "-d"], timeout=120)
        if compose.returncode != 0:
            info(compose.stderr.strip() or compose.stdout.strip() or "docker compose 启动失败。")
            return False

    if not wait_port("127.0.0.1", 15432, timeout_seconds, "本地 PostgreSQL"):
        return False

    ready = run([docker, "exec", LOCAL_PG_CONTAINER, "pg_isready", "-U", "gl02_sync", "-d", "bf_trend"], timeout=20)
    if ready.returncode == 0:
        info("本地 PostgreSQL 健康检查通过。")
        return True
    info("本地 PostgreSQL 端口已打开，但 pg_isready 未通过，继续启动前端服务。")
    return True


def parse_host_port(base_url: str) -> tuple[str, int] | None:
    parsed = urlparse(base_url)
    if not parsed.scheme or not parsed.hostname:
        return None
    if parsed.port:
        return parsed.hostname, parsed.port
    return parsed.hostname, 443 if parsed.scheme == "https" else 80


def maybe_start_local_ollama(base_url: str, log_path: Path) -> None:
    host_port = parse_host_port(base_url)
    if not host_port:
        return
    host, port = host_port
    if host not in {"127.0.0.1", "localhost", "::1"} or port != 11434:
        return
    if port_open("127.0.0.1", 11434):
        info("本机 Ollama 已在 127.0.0.1:11434 监听。")
        return
    ollama = shutil.which("ollama")
    if not ollama:
        info("未找到 ollama 命令，无法自动启动本机 Ollama。")
        return
    info("启动本机 Ollama 服务：127.0.0.1:11434")
    LOG_DIR.mkdir(exist_ok=True)
    log_file = log_path.open("a", encoding="utf-8", errors="replace")
    subprocess.Popen([ollama, "serve"], cwd=str(ROOT), stdout=log_file, stderr=subprocess.STDOUT, creationflags=CREATE_NO_WINDOW)
    wait_port("127.0.0.1", 11434, 30, "本机 Ollama")


def check_model_backend(base_url: str) -> None:
    url = base_url.rstrip("/") + "/api/version"
    try:
        with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=5) as response:
            text = response.read().decode("utf-8", errors="replace")[:300]
        info(f"模型后端可达：{url} -> {text}")
    except Exception as exc:
        info(f"警告：模型后端暂不可达：{url}，原因：{exc}")


def check_chronos_backend(base_url: str) -> None:
    if not base_url:
        info("Chronos 预测服务未配置；趋势页预测请求会保持禁用/报错状态。")
        return
    url = base_url.rstrip("/") + "/api/chronos/status"
    try:
        with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=6) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
        info(f"Chronos 预测服务状态：ok={data.get('ok')} engine={data.get('engine')} url={url}")
    except Exception as exc:
        info(f"警告：Chronos 预测服务暂不可达：{url}，原因：{exc}")


def start_background(name: str, cmd: list[str], log_path: Path, env: dict[str, str]) -> int:
    LOG_DIR.mkdir(exist_ok=True)
    log_file = log_path.open("a", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        creationflags=CREATE_NO_WINDOW,
    )
    info(f"{name} 已启动，PID={proc.pid}，日志={log_path}")
    return proc.pid


def build_common_env(args: argparse.Namespace) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    if args.ollama_base_url:
        env["OLLAMA_BASE_URL"] = args.ollama_base_url
    if args.model:
        env["BF_LLM_MODEL"] = args.model
    else:
        env.pop("BF_LLM_MODEL", None)
    env.setdefault(
        "BF_ALLOWED_LOADED_MODELS",
        "chiqiong-blast-furnace:latest,chiqiong-blast-furnace:latest_s",
    )
    if args.public_model:
        env["PUBLIC_MODEL_NAME"] = args.public_model
    if args.chronos_base_url:
        env["BF_CHRONOS_BASE_URL"] = args.chronos_base_url.rstrip("/")
    else:
        env.pop("BF_CHRONOS_BASE_URL", None)
    env["BF_CHRONOS_TIMEOUT_SECONDS"] = str(args.chronos_timeout_seconds)
    return env


def db_child_args(args: argparse.Namespace) -> list[str]:
    child_args: list[str] = []
    if args.db_host:
        child_args += ["--db-host", args.db_host]
    if args.db_port:
        child_args += ["--db-port", str(args.db_port)]
    if args.db_name:
        child_args += ["--db-name", args.db_name]
    if args.db_user:
        child_args += ["--db-user", args.db_user]
    if args.db_password_env:
        child_args += ["--db-password-env", args.db_password_env]
    return child_args


def verify_stack(args: argparse.Namespace) -> None:
    wait_port(args.host, args.ws_port, 45, "8767 WebSocket 桥接")
    wait_port(args.host, args.port, 45, "8092 前端/API")

    api_url = f"http://{args.host}:{args.port}/api/automation/status"
    try:
        with urlopen(Request(api_url, headers={"Accept": "application/json"}), timeout=8) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
        info(f"8092 自动值守状态：ok={data.get('ok')} database_ok={data.get('database_ok')}")
    except Exception as exc:
        info(f"警告：8092 状态检查失败：{exc}")

    ws_check = ROOT / "tools" / "check_v3_ws_bridge_python.py"
    if ws_check.exists():
        result = run([default_python(), str(ws_check), "--url", f"ws://{args.host}:{args.ws_port}"], timeout=20)
        if result.returncode == 0 and result.stdout.strip():
            info("8767 桥接检查通过。")
            print(result.stdout.strip(), flush=True)
        else:
            info("警告：8767 桥接检查未通过。")
            if result.stdout.strip():
                print(result.stdout.strip(), flush=True)
            if result.stderr.strip():
                print(result.stderr.strip(), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Python-only launcher for the V3 local dashboard stack.")
    parser.add_argument("--db-profile", choices=["local", "22012", "custom", "inherit"], default="local")
    parser.add_argument("--port", type=int, default=8092)
    parser.add_argument("--ws-port", type=int, default=8767)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--db-host", default="", help="Override GL02_PGHOST for custom/forwarded PostgreSQL access.")
    parser.add_argument("--db-port", default="", help="Override GL02_PGPORT for custom/forwarded PostgreSQL access.")
    parser.add_argument("--db-name", default="", help="Override GL02_PGDATABASE.")
    parser.add_argument("--db-user", default="", help="Override GL02_PGUSER.")
    parser.add_argument("--db-password-env", default="GL02_PGPASSWORD", help="Environment variable that holds the PostgreSQL password.")
    parser.add_argument("--ollama-base-url", default=os.environ.get("OLLAMA_BASE_URL", "http://10.30.220.12:11434"))
    parser.add_argument("--model", default=os.environ.get("BF_LLM_MODEL", ""))
    parser.add_argument("--public-model", default=os.environ.get("PUBLIC_MODEL_NAME", "炽穹·高炉炼铁大模型"))
    parser.add_argument("--chronos-base-url", default=os.environ.get("BF_CHRONOS_BASE_URL", ""))
    parser.add_argument("--chronos-port", type=int, default=8777)
    parser.add_argument("--chronos-engine", choices=["local-script", "http-proxy", "constant"], default=os.environ.get("BF_CHRONOS_ENGINE", "local-script"))
    parser.add_argument("--chronos-upstream-base-url", default=os.environ.get("BF_CHRONOS_UPSTREAM_BASE_URL", ""))
    parser.add_argument("--chronos-timeout-seconds", type=float, default=float(os.environ.get("BF_CHRONOS_TIMEOUT_SECONDS", "900")))
    parser.add_argument("--start-chronos-service", action="store_true", help="Start the local Chronos prediction HTTP service.")
    parser.add_argument("--restart", action="store_true", help="Stop 8092/8767 before starting.")
    parser.add_argument("--skip-postgres-start", action="store_true", help="Do not try to start the local PostgreSQL container.")
    parser.add_argument("--start-local-ollama", action="store_true", help="If OLLAMA_BASE_URL is 127.0.0.1:11434, start ollama serve.")
    parser.add_argument("--no-verify", action="store_true")
    args = parser.parse_args()

    if args.restart:
        ports = [args.port, args.ws_port]
        if args.start_chronos_service:
            ports.append(args.chronos_port)
        stop_ports(ports)

    if args.db_profile == "local" and not args.skip_postgres_start:
        ensure_local_postgres()
    elif args.db_profile == "local":
        info("已跳过本地 PostgreSQL 自动启动，只使用现有 127.0.0.1:15432。")
    else:
        info(f"数据库配置交给子启动脚本处理：db-profile={args.db_profile}")

    if args.start_local_ollama:
        maybe_start_local_ollama(args.ollama_base_url, LOG_DIR / "v3_local_ollama_python.log")
    check_model_backend(args.ollama_base_url)

    py = default_python()
    env = build_common_env(args)
    db_args = db_child_args(args)
    ws_script = ROOT / "tools" / "start_v3_ws_bridge_python.py"
    api_script = ROOT / "tools" / "start_v3_8092_python.py"
    chronos_script = ROOT / "tools" / "start_v3_chronos_python.py"

    if args.start_chronos_service:
        if not args.chronos_base_url:
            args.chronos_base_url = f"http://{args.host}:{args.chronos_port}"
            env["BF_CHRONOS_BASE_URL"] = args.chronos_base_url
        if not port_open(args.host, args.chronos_port):
            cmd = [
                py,
                str(chronos_script),
                "--host",
                args.host,
                "--port",
                str(args.chronos_port),
                "--engine",
                args.chronos_engine,
                "--timeout-seconds",
                str(args.chronos_timeout_seconds),
            ]
            if args.chronos_upstream_base_url:
                cmd += ["--upstream-base-url", args.chronos_upstream_base_url]
            start_background(
                "8777 Chronos 预测服务",
                cmd,
                LOG_DIR / f"v3_chronos_{args.chronos_port}_python.log",
                env,
            )
            wait_port(args.host, args.chronos_port, 45, "Chronos 预测服务")
        else:
            info(f"Chronos 预测服务已在运行：{args.host}:{args.chronos_port}")
    check_chronos_backend(args.chronos_base_url)

    if not port_open(args.host, args.ws_port):
        start_background(
            "8767 WebSocket 桥接",
            [
                py,
                str(ws_script),
                "--db-profile",
                args.db_profile,
                "--host",
                args.host,
                "--port",
                str(args.ws_port),
                "--chronos-base-url",
                args.chronos_base_url,
                "--chronos-timeout-seconds",
                str(args.chronos_timeout_seconds),
                *db_args,
            ],
            LOG_DIR / "v3_ws_bridge_8767_python.log",
            env,
        )
    else:
        info(f"8767 WebSocket 桥接已在运行：{args.host}:{args.ws_port}")

    if not port_open(args.host, args.port):
        start_background(
            "8092 前端/API",
            [
                py,
                str(api_script),
                "--db-profile",
                args.db_profile,
                "--host",
                args.host,
                "--port",
                str(args.port),
                "--ollama-base-url",
                args.ollama_base_url,
                *(
                    ["--model", args.model]
                    if args.model
                    else []
                ),
                "--public-model",
                args.public_model,
                *db_args,
            ],
            LOG_DIR / "v3_8092_python.log",
            env,
        )
    else:
        info(f"8092 前端/API 已在运行：{args.host}:{args.port}")

    if not args.no_verify:
        verify_stack(args)

    info(f"入口：http://{args.host}:{args.port}/frontend_dashboard_v3.server.html?ws_port={args.ws_port}")
    if args.chronos_base_url:
        info(f"Chronos 预测服务：{args.chronos_base_url.rstrip('/')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
