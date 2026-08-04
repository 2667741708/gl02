from __future__ import annotations

import argparse
import importlib.util
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
    },
    "22012": {
        "GL02_PGHOST": "10.30.220.12",
        "GL02_PGPORT": "5432",
        "GL02_PGDATABASE": "bf_trend",
        "GL02_PGUSER": "gl02_reader",
    },
}


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def ensure_mcp_dependency(root: Path) -> bool:
    """Ensure the 8092 runtime Python can import the MCP SDK."""
    if importlib.util.find_spec("mcp") is not None:
        return True

    requirements = root / "requirements-local.txt"
    if not requirements.exists():
        print(f"MCP Python 依赖缺失，且缺少依赖文件：{requirements}")
        return False

    print(f"MCP Python 依赖缺失，正在使用当前解释器安装：{requirements}")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(requirements)],
        cwd=str(root),
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    importlib.invalidate_caches()
    if result.returncode != 0 or importlib.util.find_spec("mcp") is None:
        print("MCP Python 依赖安装失败；请先修复 requirements-local.txt 或当前 Python 环境。")
        return False
    return True


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
    parser = argparse.ArgumentParser(description="Start the V3 8092 frontend proxy with selected model and database backends.")
    parser.add_argument("--ollama-base-url", default="http://10.30.220.12:11434")
    parser.add_argument("--model", default="", help="Optional model pin; omit to use the model discovered from Ollama.")
    parser.add_argument("--public-model", default="高炉大模型服务")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default="8092")
    parser.add_argument("--db-profile", choices=["inherit", "local", "22012", "custom"], default="local")
    parser.add_argument("--db-host", default="")
    parser.add_argument("--db-port", default="")
    parser.add_argument("--db-name", default="")
    parser.add_argument("--db-user", default="")
    parser.add_argument("--db-password", default="")
    parser.add_argument("--db-password-env", default="GL02_PGPASSWORD")
    parser.add_argument(
        "--backend-script",
        default=str(root / "高炉前端数据" / "智能助手" / "backend" / "ollama_proxy_server.py"),
    )
    args = parser.parse_args(argv)

    if not ensure_mcp_dependency(root):
        return 3

    env = os.environ.copy()
    env["BF_PROXY_HOST"] = args.host
    env["BF_PROXY_PORT"] = str(args.port)
    env["OLLAMA_BASE_URL"] = args.ollama_base_url.rstrip("/")
    if args.model.strip():
        env["BF_LLM_MODEL"] = args.model.strip()
    else:
        env.pop("BF_LLM_MODEL", None)
    env["BF_PUBLIC_MODEL_NAME"] = args.public_model
    env.setdefault("BF_MCP_PYTHON", sys.executable)
    env.setdefault("BF_FRONTEND_DIR", str(root / "高炉前端数据"))
    env.setdefault("BF_INDEX_FILE", "frontend_dashboard_v3.server.html")
    apply_db_profile(env, args)

    print(f"Starting V3 proxy: http://{args.host}:{args.port}")
    print(f"Model backend: {env['OLLAMA_BASE_URL']}")
    print(f"Model pin: {env.get('BF_LLM_MODEL', '<discover-from-ollama-11434>')}")
    print(
        "Database: "
        f"{env.get('GL02_PGUSER', '')}@{env.get('GL02_PGHOST', '')}:"
        f"{env.get('GL02_PGPORT', '')}/{env.get('GL02_PGDATABASE', '')}"
    )
    return subprocess.call([sys.executable, args.backend_script], cwd=str(root), env=env)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
