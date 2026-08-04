# -*- coding: utf-8 -*-
"""Build a protected, sourceless runtime folder for 服务器实际运行版V3."""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path


def env_path(name: str, default: Path) -> Path:
    """Resolve a project path from an environment variable or a safe default.

    对应需求：
    - REQ-PACKAGE-001 保护包构建脚本必须默认绑定当前项目根目录。

    文档：
    - docs/program_index.md#toolsbuild_protected_v3_deploypy
    - docs/config_reference.md#保护包构建配置
    """

    return Path(os.getenv(name, str(default))).expanduser()


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_ROOT = env_path("BF_V3_DEPLOY_SOURCE_ROOT", PROJECT_ROOT)
DEFAULT_TARGET_ROOT = env_path("BF_V3_DEPLOY_TARGET_ROOT", PROJECT_ROOT / "build" / "protected_v3_runtime")
ENTROPY = os.getenv("BF_V3_DEPLOY_ENTROPY", "server-v3-runtime-20260510").encode("utf-8")


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


crypt32 = ctypes.windll.crypt32
kernel32 = ctypes.windll.kernel32
CRYPTPROTECT_LOCAL_MACHINE = 0x4


def _blob(data: bytes):
    buf = ctypes.create_string_buffer(data)
    return DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte))), buf


def dpapi_protect(data: bytes) -> bytes:
    in_blob, in_buf = _blob(data)
    entropy_blob, entropy_buf = _blob(ENTROPY)
    out_blob = DATA_BLOB()
    ok = crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        None,
        ctypes.byref(entropy_blob),
        None,
        None,
        CRYPTPROTECT_LOCAL_MACHINE,
        ctypes.byref(out_blob),
    )
    _ = (in_buf, entropy_buf)
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding=encoding)


def safe_backup_target(target: Path) -> None:
    if not target.exists():
        return
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = target.with_name(target.name + "_bak_" + stamp)
    try:
        target.rename(backup)
        print(f"[backup] {target} -> {backup}")
        return
    except PermissionError:
        # An empty folder can be held open by Explorer/PowerShell. In that case
        # keep the folder and populate it in place.
        if not any(target.iterdir()):
            print(f"[backup] reuse empty locked target: {target}")
            return
        print(f"[backup] target locked; clearing contents in place: {target}")
        for child in list(target.iterdir()):
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=False)
            else:
                child.unlink()


def should_skip_file(path: Path) -> bool:
    name = path.name
    suffix = path.suffix.lower()
    if name.startswith("."):
        return True
    if ".bak" in name or name.endswith(".bak"):
        return True
    if suffix in {".py", ".pyc", ".pyo"}:
        return True
    if suffix in {".log", ".tmp"}:
        return True
    return False


def copy_tree_filtered(src: Path, dst: Path, *, skip_dirs: set[str] | None = None) -> None:
    skip_dirs = skip_dirs or set()
    if not src.exists():
        return
    for root, dirs, files in os.walk(src):
        root_path = Path(root)
        dirs[:] = [
            d
            for d in dirs
            if d not in skip_dirs
            and d != "__pycache__"
            and not d.startswith(".")
            and d.lower() not in {"logs", "tests", "docs"}
        ]
        rel = root_path.relative_to(src)
        out_dir = dst / rel
        out_dir.mkdir(parents=True, exist_ok=True)
        for file_name in files:
            path = root_path / file_name
            if should_skip_file(path):
                continue
            out = out_dir / file_name
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, out)


def compile_source_to_pyc(source_text: str, dst_pyc: Path, pseudo_py: Path) -> None:
    pseudo_py.parent.mkdir(parents=True, exist_ok=True)
    pseudo_py.write_text(source_text, encoding="utf-8")
    dst_pyc.parent.mkdir(parents=True, exist_ok=True)
    py_compile.compile(str(pseudo_py), cfile=str(dst_pyc), doraise=True, optimize=2)
    pseudo_py.unlink(missing_ok=True)


def copy_compile_py(src_py: Path, dst_pyc: Path, *, patch_kind: str | None = None) -> None:
    text = read_text(src_py)
    if patch_kind == "proxy":
        text = patch_proxy_source(text)
    elif patch_kind == "bridge":
        text = patch_bridge_source(text)
    elif patch_kind == "mcp":
        text = patch_mcp_source(text)
    compile_source_to_pyc(text, dst_pyc, dst_pyc.with_suffix(".py"))


def patch_proxy_source(text: str) -> str:
    old = '    mcp_path = ASSISTANT_DIR / "mcp" / "bf_data_mcp_server.py"\n    if not mcp_path.exists():'
    new = (
        '    mcp_path = ASSISTANT_DIR / "mcp" / "bf_data_mcp_server.py"\n'
        '    if not mcp_path.exists():\n'
        '        mcp_pyc = ASSISTANT_DIR / "mcp" / "bf_data_mcp_server.pyc"\n'
        '        if mcp_pyc.exists():\n'
        '            mcp_path = mcp_pyc\n'
        '    if not mcp_path.exists():'
    )
    text = text.replace(old, new)
    text = text.replace('"chiqiong-blast-furnace:latest"', 'os.environ.get("BF_BRAND_MODEL_TOKEN", "炽穹·高炉炼铁大模型")')
    text = text.replace('"chiqiong-blast-furnace"', 'os.environ.get("BF_BRAND_MODEL_TOKEN_SHORT", "炽穹")')
    text = text.replace(
        '        if parsed.path == "/api/ollama/status":\n            self.handle_ollama_status()',
        '        if parsed.path in {"/api/ollama/status", "/api/model/status"}:\n            self.handle_ollama_status()',
    )
    return text


def patch_bridge_source(text: str) -> str:
    text = text.replace(
        'DEFAULT_CHRONOS_SCRIPT = ROOT_DIR / "chronos外推预测" / "src" / "inference" / "live_chronos_predict.py"',
        'DEFAULT_CHRONOS_SCRIPT = Path(os.getenv("BF_CHRONOS_SCRIPT", str(ROOT_DIR / "chronos外推预测" / "src" / "inference" / "live_chronos_predict.pyc")))',
    )
    new = (
        'DEFAULT_CHRONOS_MODEL_CANDIDATES = (\n'
        '    Path(os.getenv("BF_CHRONOS_MODEL_PATH", "")) if os.getenv("BF_CHRONOS_MODEL_PATH") else None,\n'
        '    ROOT_DIR / "runtime_cache" / "chronos-v2",\n'
        ')'
    )
    text = re.sub(r'DEFAULT_CHRONOS_MODEL_CANDIDATES = \(\n(?:    .+\n)+\)', new, text, count=1)
    text = text.replace("Chronos-2 model directory was not found. Set BF_CHRONOS_MODEL_PATH.", "prediction model directory was not found.")
    text = text.replace("Chronos script not found:", "prediction script not found:")
    text = text.replace(
        '        if (path / "PythonAPI" / "PsServer.py").exists():\n            return path\n        if path.name == "PythonAPI" and (path / "PsServer.py").exists():\n            return path.parent',
        '        if (path / "PythonAPI" / "PsServer.py").exists() or (path / "PythonAPI" / "PsServer.pyc").exists():\n            return path\n        if path.name == "PythonAPI" and ((path / "PsServer.py").exists() or (path / "PsServer.pyc").exists()):\n            return path.parent',
    )
    return text


def patch_mcp_source(text: str) -> str:
    old = '    helper = MCP_DIR / "gl02_pspace_direct_query.py"\n    cmd = [\n        sys.executable,\n        str(helper),'
    new = (
        '    helper = MCP_DIR / "gl02_pspace_direct_query.py"\n'
        '    if not helper.exists():\n'
        '        helper_pyc = MCP_DIR / "gl02_pspace_direct_query.pyc"\n'
        '        if helper_pyc.exists():\n'
        '            helper = helper_pyc\n'
        '    cmd = [\n'
        '        sys.executable,\n'
        '        str(helper),'
    )
    text = text.replace(old, new)
    text = text.replace(
        '    if not (sdk_root / "PythonAPI" / "PsServer.py").exists():\n        raise FileNotFoundError(f"找不到 pSpace PythonAPI SDK: {sdk_root}")',
        '    if not ((sdk_root / "PythonAPI" / "PsServer.py").exists() or (sdk_root / "PythonAPI" / "PsServer.pyc").exists()):\n        raise FileNotFoundError(f"找不到 pSpace PythonAPI SDK: {sdk_root}")',
    )
    return text


def compile_tree(src: Path, dst: Path, *, patch_by_name: dict[str, str] | None = None) -> None:
    patch_by_name = patch_by_name or {}
    for path in src.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(src)
        patch_kind = patch_by_name.get(str(rel).replace("\\", "/")) or patch_by_name.get(path.name)
        copy_compile_py(path, (dst / rel).with_suffix(".pyc"), patch_kind=patch_kind)


def sanitize_frontend(html_path: Path) -> None:
    text = read_text(html_path)
    text = text.replace(
        "const LLM_MODEL_ALIASES={'炽穹·高炉炼铁大模型':'chiqiong-blast-furnace:latest','chiqiong-blast-furnace':'chiqiong-blast-furnace:latest'};"
        "function normalizeLlmPayload(payload){const p={...(payload||{})};p.model=LLM_MODEL_ALIASES[p.model]||p.model||'chiqiong-blast-furnace:latest';",
        "const LLM_MODEL_ALIASES={'炽穹·高炉炼铁大模型':'炽穹·高炉炼铁大模型'};"
        "function normalizeLlmPayload(payload){const p={...(payload||{})};p.model=LLM_MODEL_ALIASES[p.model]||p.model||'炽穹·高炉炼铁大模型';",
    )
    text = text.replace("Ollama", "模型服务")
    text = text.replace("/api/ollama/status", "/api/model/status")
    text = text.replace("chiqiong-blast-furnace:latest", "炽穹·高炉炼铁大模型")
    text = text.replace("chiqiong-blast-furnace", "炽穹")
    sensitive_prefixes = ("qw" + "en", "Qw" + "en")
    for prefix in sensitive_prefixes:
        text = text.replace(prefix, "model")
    write_text(html_path, text)


def parse_pspace_config(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    in_block = False
    for line in read_text(path).splitlines():
        if re.match(r"^pspace\s*:\s*$", line):
            in_block = True
            continue
        if in_block and line.strip() and not line[:1].isspace():
            break
        if not in_block:
            continue
        m = re.match(r"\s*([A-Za-z0-9_-]+)\s*:\s*[\"']?([^\"'#]+)", line)
        if m:
            out[m.group(1).strip()] = m.group(2).strip()
    return out


def parse_sdk_sample(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    text = read_text(path)
    user = re.search(r'DEFAULT_USER\s*=\s*"([^"]+)"', text)
    password = re.search(r'DEFAULT_PASSWORD\s*=\s*"([^"]+)"', text)
    if user:
        out["username"] = user.group(1)
    if password:
        out["password"] = password.group(1)
    return out


def make_secrets(source: Path) -> dict[str, str]:
    cfg = parse_pspace_config(source / "ghsc" / "src" / "main" / "resources" / "application-prod.yml")
    sample = parse_sdk_sample(source / "pythonSDK(1)" / "read_sensor_data.py")
    merged = {**sample, **cfg}
    return {
        "PSPACE_USER": os.getenv("PSPACE_USER") or merged.get("username") or "admin",
        "PSPACE_PASSWORD": os.getenv("PSPACE_PASSWORD") or merged.get("password") or "",
        "OLLAMA_BASE_URL": os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434",
        "BF_LLM_MODEL": os.getenv("BF_LLM_MODEL") or "chiqiong-blast-furnace:latest",
        "BF_PUBLIC_MODEL_ID": "炽穹·高炉炼铁大模型",
        "BF_PUBLIC_MODEL_NAME": "炽穹·高炉炼铁大模型",
    }


def find_chronos_model(source: Path) -> Path:
    env_model_path = os.getenv("BF_CHRONOS_MODEL_PATH")
    candidates = [
        Path(env_model_path).expanduser() if env_model_path else None,
        source / "chronos外推预测" / "chronos-v2",
    ]
    for c in candidates:
        if c and (c / "config.json").exists() and any(c.glob("*.safetensors")):
            return c
    raise FileNotFoundError("Chronos model directory not found. Set BF_CHRONOS_MODEL_PATH or place chronos-v2 under the source project.")


def encrypt_model_dir(model_dir: Path, out_file: Path, manifest_file: Path) -> None:
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp_zip = Path(tmp.name)
    try:
        with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_STORED) as zf:
            for path in model_dir.rglob("*"):
                if path.is_file():
                    zf.write(path, path.relative_to(model_dir).as_posix())
        plain = tmp_zip.read_bytes()
        out_file.write_bytes(dpapi_protect(plain))
        manifest = {
            "encrypted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "source_file_count": sum(1 for p in model_dir.rglob("*") if p.is_file()),
            "plain_zip_sha256": hashlib.sha256(plain).hexdigest(),
            "encrypted_file_sha256": sha256_file(out_file),
        }
        write_text(manifest_file, json.dumps(manifest, ensure_ascii=False, indent=2))
    finally:
        tmp_zip.unlink(missing_ok=True)


LAUNCHER_SOURCE = r'''
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

ENTROPY = os.getenv("BF_V3_DEPLOY_ENTROPY", "server-v3-runtime-20260510").encode("utf-8")

class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

crypt32 = ctypes.windll.crypt32
kernel32 = ctypes.windll.kernel32

def _blob(data: bytes):
    buf = ctypes.create_string_buffer(data)
    return DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte))), buf

def dpapi_unprotect(data: bytes) -> bytes:
    in_blob, in_buf = _blob(data)
    entropy_blob, entropy_buf = _blob(ENTROPY)
    out_blob = DATA_BLOB()
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        ctypes.byref(entropy_blob),
        None,
        None,
        0,
        ctypes.byref(out_blob),
    )
    _ = (in_buf, entropy_buf)
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)

def root_dir() -> Path:
    return Path(__file__).resolve().parent

def python_exe() -> str:
    candidate = os.getenv("BF_V3_RUNTIME_PYTHON")
    if candidate and Path(candidate).expanduser().exists():
        return str(Path(candidate).expanduser())
    return sys.executable

def load_secrets(root: Path) -> dict:
    path = root / "secure" / "runtime_secrets.dpapi"
    if not path.exists():
        return {}
    return json.loads(dpapi_unprotect(path.read_bytes()).decode("utf-8"))

def ensure_prediction_model(root: Path) -> Path:
    secure_path = root / "secure" / "prediction_model.dpapi"
    cache_root = Path(os.environ.get("LOCALAPPDATA", str(root / "runtime_cache"))) / "ChiqiongBFV3Runtime"
    out_dir = cache_root / "chronos-v2"
    if (out_dir / "config.json").exists() and any(out_dir.glob("*.safetensors")):
        return out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_root.mkdir(parents=True, exist_ok=True)
    tmp_zip = cache_root / "prediction_model.zip"
    tmp_zip.write_bytes(dpapi_unprotect(secure_path.read_bytes()))
    try:
        with zipfile.ZipFile(tmp_zip, "r") as zf:
            zf.extractall(out_dir)
    finally:
        tmp_zip.unlink(missing_ok=True)
    return out_dir

def pid_file(root: Path, name: str) -> Path:
    return root / "runtime" / f"{name}.pid"

def is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        result = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True, timeout=10)
        return str(pid) in result.stdout
    except Exception:
        return False

def read_pid(root: Path, name: str) -> int:
    try:
        return int(pid_file(root, name).read_text(encoding="utf-8").strip())
    except Exception:
        return 0

def launch(name: str, args: list[str], cwd: Path, env: dict, root: Path) -> int:
    root.joinpath("runtime").mkdir(exist_ok=True)
    log_dir = root / "logs"
    log_dir.mkdir(exist_ok=True)
    out = open(log_dir / f"{name}.log", "ab", buffering=0)
    err = open(log_dir / f"{name}.err.log", "ab", buffering=0)
    creationflags = 0
    if os.name == "nt":
        creationflags = (
            subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.DETACHED_PROCESS
            | getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0x01000000)
        )
    proc = subprocess.Popen(args, cwd=str(cwd), env=env, stdout=out, stderr=err, creationflags=creationflags)
    pid_file(root, name).write_text(str(proc.pid), encoding="utf-8")
    return proc.pid

def base_env(root: Path, api_port: int, ws_port: int) -> dict:
    env = os.environ.copy()
    env.update({k: str(v) for k, v in load_secrets(root).items() if v is not None})
    model_dir = ensure_prediction_model(root)
    frontend = root / "高炉前端数据"
    env.update({
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "BF_PROXY_HOST": "0.0.0.0",
        "BF_PROXY_PORT": str(api_port),
        "BF_FRONTEND_DIR": str(frontend),
        "BF_INDEX_FILE": "frontend_dashboard_v3.server.html",
        "BF_WS_HOST": "0.0.0.0",
        "BF_WS_PORT": str(ws_port),
        "BF_QA_DB": str(frontend / "data" / "bf_qa.sqlite3"),
        "BF_QA_PROJECTS_DIR": str(frontend / "data" / "projects"),
        "BF_REPORTS_DIR": str(frontend / "data" / "reports"),
        "BF_QA_KNOWLEDGE_DB": str(frontend / "data" / "bf_unified_vectors.sqlite3"),
        "BF_TREND_HISTORY_SOURCE": "sqlite",
        "BF_MCP_DATA_SOURCE": "pspace_243",
        "BF_GL02_MAPPING_PATH": str(root / "趋势分析" / "trend_backend" / "config" / "gl02_sio_mapping.json"),
        "BF_GL02_STORAGE_CONFIG": str(root / "趋势分析" / "trend_backend" / "config" / "gl02_1min_storage.json"),
        "PSPACE_SDK_ROOT": str(root / "pythonSDK(1)"),
        "PSPACE_SERVER": "10.22.181.243",
        "PSPACE_PORT": "8889",
        "BF_CHRONOS_MODEL_PATH": str(model_dir),
        "BF_CHRONOS_SCRIPT": str(root / "chronos外推预测" / "src" / "inference" / "live_chronos_predict.pyc"),
        "BF_CHRONOS_PYTHON": python_exe(),
        "BF_BRAND_MODEL_TOKEN": "炽穹·高炉炼铁大模型",
        "BF_BRAND_MODEL_TOKEN_SHORT": "炽穹",
    })
    return env

def start(args) -> None:
    root = root_dir()
    env = base_env(root, args.api_port, args.ws_port)
    py = python_exe()
    api_pid = read_pid(root, "api")
    bridge_pid = read_pid(root, "bridge")
    if not is_running(api_pid):
        api_script = root / "高炉前端数据" / "智能助手" / "backend" / "ollama_proxy_server.pyc"
        api_pid = launch("api", [py, "-X", "utf8", "-u", str(api_script)], root / "高炉前端数据", env, root)
    if not is_running(bridge_pid):
        bridge_script = root / "tools" / "pspace_8092_realtime_bridge.pyc"
        bridge_args = [
            py, "-X", "utf8", "-u", str(bridge_script),
            "--host", "0.0.0.0",
            "--port", str(args.ws_port),
            "--poll-seconds", "60",
            "--history-hours", "8",
            "--history-max-values", "20000",
            "--history-interval-seconds", "60",
            "--history-aggregate", "PS_HIS_AVERAGE",
            "--qa-db", str(root / "高炉前端数据" / "data" / "bf_qa.sqlite3"),
            "--snapshot-interval-seconds", "60",
            "--serve",
        ]
        bridge_pid = launch("bridge", bridge_args, root, env, root)
    print(json.dumps({"ok": True, "api_port": args.api_port, "ws_port": args.ws_port, "api_pid": api_pid, "bridge_pid": bridge_pid, "url": f"http://10.30.220.12:{args.api_port}/"}, ensure_ascii=False))

def stop(args) -> None:
    root = root_dir()
    stopped = []
    for name in ("api", "bridge"):
        pid = read_pid(root, name)
        if is_running(pid):
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True)
            stopped.append({"name": name, "pid": pid})
        pid_file(root, name).unlink(missing_ok=True)
    if args.clear_model_cache:
        shutil.rmtree(root / "runtime_cache" / "chronos-v2", ignore_errors=True)
        local_cache = Path(os.environ.get("LOCALAPPDATA", str(root / "runtime_cache"))) / "ChiqiongBFV3Runtime"
        shutil.rmtree(local_cache / "chronos-v2", ignore_errors=True)
    print(json.dumps({"ok": True, "stopped": stopped}, ensure_ascii=False))

def status(args) -> None:
    root = root_dir()
    api_pid = read_pid(root, "api")
    bridge_pid = read_pid(root, "bridge")
    out = {
        "api_pid": api_pid,
        "api_running": is_running(api_pid),
        "bridge_pid": bridge_pid,
        "bridge_running": is_running(bridge_pid),
    }
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{args.api_port}/api/ollama/status", timeout=5) as resp:
            out["api_status_code"] = resp.status
            out["api_status"] = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        out["api_status_error"] = str(exc)
    print(json.dumps(out, ensure_ascii=False, indent=2))

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_start = sub.add_parser("start")
    p_start.add_argument("--api-port", type=int, default=18092)
    p_start.add_argument("--ws-port", type=int, default=18767)
    p_stop = sub.add_parser("stop")
    p_stop.add_argument("--clear-model-cache", action="store_true")
    p_status = sub.add_parser("status")
    p_status.add_argument("--api-port", type=int, default=18092)
    ns = parser.parse_args()
    if ns.cmd == "start":
        start(ns)
    elif ns.cmd == "stop":
        stop(ns)
    elif ns.cmd == "status":
        status(ns)

if __name__ == "__main__":
    main()
'''


def write_launch_scripts(target: Path) -> None:
    start_ps1 = '''param(
  [int]$ApiPort = 18092,
  [int]$WsPort = 18767
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = "C:\\Program Files\\Python311\\python.exe"
if (-not (Test-Path -LiteralPath $Python)) { $Python = "python" }
& $Python -X utf8 -u (Join-Path $Root "secure_runtime.pyc") start --api-port $ApiPort --ws-port $WsPort
'''
    stop_ps1 = '''param(
  [switch]$ClearModelCache
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = "C:\\Program Files\\Python311\\python.exe"
if (-not (Test-Path -LiteralPath $Python)) { $Python = "python" }
$argsList = @("-X", "utf8", "-u", (Join-Path $Root "secure_runtime.pyc"), "stop")
if ($ClearModelCache) { $argsList += "--clear-model-cache" }
& $Python @argsList
'''
    status_ps1 = '''param(
  [int]$ApiPort = 18092
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = "C:\\Program Files\\Python311\\python.exe"
if (-not (Test-Path -LiteralPath $Python)) { $Python = "python" }
& $Python -X utf8 -u (Join-Path $Root "secure_runtime.pyc") status --api-port $ApiPort
'''
    bat = '''@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0启动_炽穹V3.ps1"
pause
'''
    write_text(target / "启动_炽穹V3.ps1", start_ps1, encoding="utf-8-sig")
    write_text(target / "停止_炽穹V3.ps1", stop_ps1, encoding="utf-8-sig")
    write_text(target / "状态_炽穹V3.ps1", status_ps1, encoding="utf-8-sig")
    write_text(target / "一键启动.bat", bat, encoding="gbk")
    readme = (
        "炽穹·高炉炼铁大模型V3 受保护运行目录\r\n"
        "启动：右键 PowerShell 运行 启动_炽穹V3.ps1，默认 HTTP 端口 18092，实时桥接端口 18767。\r\n"
        "停止：运行 停止_炽穹V3.ps1。若要清除运行时解密出的预测权重缓存，追加 -ClearModelCache。\r\n"
        "状态：运行 状态_炽穹V3.ps1。\r\n"
        "说明：Python 业务源码已以 sourceless bytecode 形式部署；预测权重与运行密钥使用本机 DPAPI 加密保存。\r\n"
    )
    write_text(target / "README_运行说明.txt", readme, encoding="utf-8-sig")


def scan_plaintext(target: Path) -> dict[str, list[str]]:
    sensitive_prefixes = ("qw" + "en", "Qw" + "en", "qw" + "en3", "qw" + "en2")
    patterns = {
        "sensitive_model": re.compile(
            r"|".join(re.escape(x) for x in sensitive_prefixes) + r"|27B|30B"
        ),
        "python_source": re.compile(r"\.py$"),
    }
    hits = {"sensitive_model": [], "python_source": []}
    for path in target.rglob("*"):
        if path.is_file():
            rel = str(path.relative_to(target))
            if path.suffix.lower() == ".py":
                hits["python_source"].append(rel)
            if path.suffix.lower() in {".txt", ".md", ".json", ".yaml", ".yml", ".html", ".js", ".ps1", ".bat", ".csv"}:
                text = path.read_text(encoding="utf-8", errors="ignore")
                if patterns["sensitive_model"].search(text):
                    hits["sensitive_model"].append(rel)
    return hits


def build(args: argparse.Namespace) -> None:
    source = Path(args.source).resolve()
    target = Path(args.target)
    if not source.exists():
        raise FileNotFoundError(source)
    safe_backup_target(target)
    target.mkdir(parents=True, exist_ok=True)

    frontend_src = source / "高炉前端数据"
    frontend_dst = target / "高炉前端数据"
    copy_tree_filtered(frontend_src / "config", frontend_dst / "config")
    copy_tree_filtered(frontend_src / "data", frontend_dst / "data")
    copy_tree_filtered(frontend_src / "generated", frontend_dst / "generated")
    copy_tree_filtered(frontend_src / "libs", frontend_dst / "libs")
    copy_tree_filtered(frontend_src / "logo", frontend_dst / "logo")
    shutil.copy2(frontend_src / "frontend_dashboard_v3.server.html", frontend_dst / "frontend_dashboard_v3.server.html")
    for name in ("pspace_8092_sensor_map.json", "pspace_8092_candidates.csv"):
        src = frontend_src / name
        if src.exists():
            shutil.copy2(src, frontend_dst / name)
    sanitize_frontend(frontend_dst / "frontend_dashboard_v3.server.html")

    backend_src = frontend_src / "智能助手" / "backend"
    backend_dst = frontend_dst / "智能助手" / "backend"
    copy_compile_py(backend_src / "ollama_proxy_server.py", backend_dst / "ollama_proxy_server.pyc", patch_kind="proxy")
    copy_compile_py(backend_src / "bf_knowledge_rag.py", backend_dst / "bf_knowledge_rag.pyc")

    mcp_src = frontend_src / "智能助手" / "mcp"
    mcp_dst = frontend_dst / "智能助手" / "mcp"
    compile_tree(mcp_src, mcp_dst, patch_by_name={"bf_data_mcp_server.py": "mcp"})

    compile_tree(source / "tools", target / "tools", patch_by_name={"pspace_8092_realtime_bridge.py": "bridge"})
    compile_tree(source / "炉况规则引擎", target / "炉况规则引擎")
    copy_tree_filtered(source / "炉况规则引擎" / "config", target / "炉况规则引擎" / "config")
    compile_tree(source / "调控结论生成引擎", target / "调控结论生成引擎")

    trend_cfg_src = source / "趋势分析" / "trend_backend" / "config"
    copy_tree_filtered(trend_cfg_src, target / "趋势分析" / "trend_backend" / "config")
    chronos_src = source / "chronos外推预测" / "src"
    compile_tree(chronos_src, target / "chronos外推预测" / "src")

    sdk_src = source / "pythonSDK(1)" / "PythonAPI"
    sdk_dst = target / "pythonSDK(1)" / "PythonAPI"
    copy_tree_filtered(sdk_src, sdk_dst)
    compile_tree(sdk_src, sdk_dst)

    secrets = make_secrets(source)
    if not secrets.get("PSPACE_PASSWORD"):
        raise RuntimeError("pSpace password not found for protected runtime.")
    secure_dir = target / "secure"
    secure_dir.mkdir(exist_ok=True)
    (secure_dir / "runtime_secrets.dpapi").write_bytes(dpapi_protect(json.dumps(secrets, ensure_ascii=False).encode("utf-8")))

    model_dir = find_chronos_model(source)
    encrypt_model_dir(model_dir, secure_dir / "prediction_model.dpapi", secure_dir / "prediction_model.manifest.json")

    compile_source_to_pyc(LAUNCHER_SOURCE, target / "secure_runtime.pyc", target / "secure_runtime.py")
    write_launch_scripts(target)

    (target / "logs").mkdir(exist_ok=True)
    (target / "runtime").mkdir(exist_ok=True)
    (target / "runtime_cache").mkdir(exist_ok=True)
    hits = scan_plaintext(target)
    write_text(target / "secure" / "build_report.json", json.dumps({"target": str(target), "source": str(source), "plaintext_scan": hits}, ensure_ascii=False, indent=2))
    print(json.dumps({"ok": True, "target": str(target), "model_source": str(model_dir), "plaintext_scan": hits}, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=str(DEFAULT_SOURCE_ROOT))
    parser.add_argument("--target", default=str(DEFAULT_TARGET_ROOT))
    args = parser.parse_args()
    build(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
