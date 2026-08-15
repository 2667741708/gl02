# -*- coding: utf-8 -*-
"""Execute commands on 10.30.220.12 from the local machine.

This is a small jump-host helper for the current SSLVPN workflow:

    local machine -> SSH -> 10.30.220.12 -> run tools/PythonSDK/MCP there

It does not connect to pSpace by itself. Use it to run commands on 220.12
where ghsc, pythonSDK(1), MCP, and 8092 production services live.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

import paramiko


ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "AGENTS.md"
DEFAULT_REMOTE_ROOT = r"F:\高炉炼铁项目-real-sensor-v2_V3"
DEFAULT_PASSWORD_FILE = (
    Path(os.getenv("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    / "Codex"
    / "secrets"
    / "reliable-ssh"
    / "22012.pw"
)


def read_agents_ssh_password() -> str | None:
    if not AGENTS.exists():
        return None
    text = AGENTS.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"SSH 密码：([^\r\n]+)", text)
    return match.group(1).strip() if match else None


def resolve_password(args: argparse.Namespace) -> str:
    if args.password_env:
        value = os.getenv(args.password_env)
        if value:
            return value
    value = os.getenv("BF_22012_SSH_PASSWORD")
    if value:
        return value
    password_file = Path(str(getattr(args, "password_file", "") or "")).expanduser()
    if password_file.is_file():
        if password_file.stat().st_size > 4096:
            raise SystemExit("220.12 SSH password file exceeds the 4 KiB safety limit.")
        value = password_file.read_text(encoding="utf-8").strip()
        if value:
            return value
    if args.allow_agents_password:
        value = read_agents_ssh_password()
        if value:
            return value
    if args.prompt_password:
        return getpass.getpass(f"SSH password for {args.user}@{args.host}: ")
    raise SystemExit(
        "缺少 220.12 SSH 密码。请设置 BF_22012_SSH_PASSWORD，"
        "或传 --allow-agents-password / --prompt-password。"
    )


def parse_pair(value: str) -> tuple[Path, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("路径映射格式必须是 local=remote")
    left, right = value.split("=", 1)
    return Path(left), right


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a PowerShell/Python command on 10.30.220.12 via SSH.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=r"""
示例：

  # 只检查 220.12 远端项目和 243 端口
  python tools\remote_22012_exec.py --allow-agents-password --command ^
    "Test-Path '.\pythonSDK(1)\PythonAPI\PsServer.py'; Test-NetConnection 10.22.181.243 -Port 8889"

  # 在 220.12 上运行项目内 Python 脚本
  python tools\remote_22012_exec.py --allow-agents-password --python ".\tools\pspace_gl02_text_search.py --help"

  # 上传本地文件到远端临时目录后执行命令
  python tools\remote_22012_exec.py --allow-agents-password ^
    --upload "logs\map.json=C:\Users\Administrator\AppData\Local\Temp\map.json" ^
    --command "Get-Item 'C:\Users\Administrator\AppData\Local\Temp\map.json'"

  # 下载远端结果文件或目录
  python tools\remote_22012_exec.py --allow-agents-password ^
    --download "F:\高炉炼铁项目-real-sensor-v2_V3\高炉传感器数据\out\summary.json=logs\summary.json" ^
    --command "Write-Host done"
""",
    )
    parser.add_argument("--host", default=os.getenv("BF_22012_HOST", "10.30.220.12"))
    parser.add_argument("--user", default=os.getenv("BF_22012_USER", "administrator"))
    parser.add_argument("--workdir", default=os.getenv("BF_22012_PROJECT_ROOT", DEFAULT_REMOTE_ROOT))
    parser.add_argument("--password-env", default="BF_22012_SSH_PASSWORD")
    parser.add_argument(
        "--password-file",
        default=os.getenv("BF_22012_SSH_PASSWORD_FILE", str(DEFAULT_PASSWORD_FILE)),
        help="Read the SSH password from a protected local file without emitting it.",
    )
    parser.add_argument("--allow-agents-password", action="store_true")
    parser.add_argument("--prompt-password", action="store_true")
    parser.add_argument("--timeout", type=int, default=3600)
    parser.add_argument("--upload", action="append", type=parse_pair, default=[], help="Upload local=remote before running.")
    parser.add_argument("--upload-only", action="store_true", help="Upload staged files and exit without starting a remote shell command.")
    parser.add_argument("--download", action="append", type=parse_pair, default=[], help="Download remote=local after running.")
    parser.add_argument("--command", help="PowerShell command to run on 220.12.")
    parser.add_argument("--script", type=Path, help="Local .ps1 file to run on 220.12.")
    parser.add_argument("--python", dest="python_args", help="Run remote Python311 with these arguments from --workdir.")
    parser.add_argument(
        "--remote-shell",
        choices=("pwsh", "windows-powershell"),
        default="pwsh",
        help="Remote PowerShell runtime. Defaults to PowerShell 7; Windows PowerShell is explicit legacy bootstrap only.",
    )
    parser.add_argument("--no-profile", action="store_true", default=True)
    parser.add_argument("--keep-remote-script", action="store_true")
    parser.add_argument(
        "--emit-timing-json",
        action="store_true",
        help="Emit sanitized per-phase latency as bf.remote-exec.timing.v1 JSON.",
    )
    return parser.parse_args(argv)


def connect(args: argparse.Namespace) -> paramiko.SSHClient:
    connect_timeout = max(1, min(30, args.timeout))
    password = resolve_password(args)
    last_error: Exception | None = None
    for attempt in range(1, 4):
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=args.host,
                username=args.user,
                password=password,
                timeout=connect_timeout,
                banner_timeout=connect_timeout,
                auth_timeout=connect_timeout,
                look_for_keys=False,
                allow_agent=False,
            )
            transport = client.get_transport()
            if transport is not None:
                transport.set_keepalive(30)
            return client
        except (paramiko.SSHException, OSError) as exc:
            last_error = exc
            client.close()
            if attempt < 3:
                time.sleep(2)
    assert last_error is not None
    raise last_error


def sftp_mkdirs(sftp: paramiko.SFTPClient, remote_path: str) -> None:
    normalized = remote_path.replace("\\", "/")
    if re.match(r"^[A-Za-z]:/", normalized):
        parts = normalized.split("/")
        current = parts[0] + "/"
        parts = parts[1:]
    else:
        current = "/" if normalized.startswith("/") else ""
        parts = [part for part in normalized.strip("/").split("/") if part]
    for part in parts:
        current = current.rstrip("/") + "/" + part
        try:
            sftp.stat(current)
        except IOError:
            try:
                sftp.mkdir(current)
            except IOError:
                pass


def upload_files(sftp: paramiko.SFTPClient, uploads: list[tuple[Path, str]]) -> None:
    for local, remote in uploads:
        if not local.exists():
            raise SystemExit(f"本地上传文件不存在：{local}")
        sftp_mkdirs(sftp, str(Path(remote).parent))
        sftp.put(str(local), remote)
        print(f"[upload] {local} -> {remote}")


def download_one(sftp: paramiko.SFTPClient, remote: str, local: Path) -> None:
    try:
        attrs = sftp.stat(remote)
    except IOError as exc:
        raise SystemExit(f"远端下载路径不存在：{remote}") from exc
    # Directory bit in st_mode. Avoid importing stat just for this tiny check.
    is_dir = bool(attrs.st_mode and (attrs.st_mode & 0o040000))
    if not is_dir:
        local.parent.mkdir(parents=True, exist_ok=True)
        sftp.get(remote, str(local))
        print(f"[download] {remote} -> {local}")
        return
    local.mkdir(parents=True, exist_ok=True)
    for item in sftp.listdir_attr(remote):
        child_remote = remote.rstrip("\\/") + "/" + item.filename
        child_local = local / item.filename
        if item.st_mode and (item.st_mode & 0o040000):
            download_one(sftp, child_remote, child_local)
        else:
            child_local.parent.mkdir(parents=True, exist_ok=True)
            sftp.get(child_remote, str(child_local))
            print(f"[download] {child_remote} -> {child_local}")


def download_files(sftp: paramiko.SFTPClient, downloads: list[tuple[Path, str]]) -> None:
    for remote_path, local_path in downloads:
        download_one(sftp, str(remote_path), Path(local_path))


def build_remote_script(args: argparse.Namespace, payload_path: str | None = None) -> str:
    if args.script:
        if not payload_path:
            raise ValueError("payload_path is required for --script")
        body = f'& "{payload_path}"'
    elif args.python_args:
        escaped = args.python_args.replace("`", "``").replace('"', '`"')
        body = f'& "C:\\Program Files\\Python311\\python.exe" -X utf8 {escaped}'
    elif args.command:
        body = args.command
    else:
        raise SystemExit("必须提供 --command、--script 或 --python 之一。")

    return f"""
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$ProgressPreference = "SilentlyContinue"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
Set-Location -LiteralPath "{args.workdir}"
{body}
exit $LASTEXITCODE
""".strip()


def run_powershell(
    client: paramiko.SSHClient,
    args: argparse.Namespace,
    sftp: paramiko.SFTPClient | None = None,
    timings: dict[str, float] | None = None,
) -> int:
    """Stage UTF-8 scripts and execute them with a short PowerShell 7 -File command."""

    token = uuid.uuid4().hex
    temp_root = r"C:\Users\Administrator\AppData\Local\Temp"
    wrapper_path = rf"{temp_root}\bf_remote_exec_{token}.ps1"
    payload_path = rf"{temp_root}\bf_remote_payload_{token}.ps1" if args.script else None
    remote_paths = [wrapper_path]
    if payload_path:
        remote_paths.append(payload_path)

    stage_started = time.perf_counter()
    owns_sftp = sftp is None
    if sftp is None:
        sftp = client.open_sftp()
    try:
        if args.script and payload_path:
            payload = args.script.read_bytes()
            with sftp.file(payload_path, "wb") as remote_payload:
                remote_payload.write(payload)
        wrapper = build_remote_script(args, payload_path=payload_path).encode("utf-8")
        with sftp.file(wrapper_path, "wb") as remote_wrapper:
            remote_wrapper.write(wrapper)
    finally:
        if owns_sftp:
            sftp.close()
    if timings is not None:
        timings["wrapper_stage_ms"] = round((time.perf_counter() - stage_started) * 1000, 3)

    if args.remote_shell == "pwsh":
        executable = r"C:\Program Files\PowerShell\7\pwsh.exe"
        invocation = (
            f"& '{executable}' -NoLogo -NoProfile -NonInteractive "
            f"-ExecutionPolicy Bypass -File '{wrapper_path}'"
        )
    else:
        invocation = (
            "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass "
            f"-File '{wrapper_path}'"
        )

    try:
        command_started = time.perf_counter()
        _, stdout, stderr = client.exec_command(invocation, timeout=args.timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        if out:
            print(out, end="" if out.endswith("\n") else "\n")
        if err:
            print(err, file=sys.stderr, end="" if err.endswith("\n") else "\n")
        exit_code = stdout.channel.recv_exit_status()
        if timings is not None:
            timings["remote_command_ms"] = round((time.perf_counter() - command_started) * 1000, 3)
        return exit_code
    finally:
        cleanup_started = time.perf_counter()
        if not args.keep_remote_script:
            cleanup_sftp = sftp if not owns_sftp else client.open_sftp()
            try:
                for remote_path in remote_paths:
                    try:
                        cleanup_sftp.remove(remote_path)
                    except OSError:
                        pass
            finally:
                if owns_sftp:
                    cleanup_sftp.close()
        if timings is not None:
            timings["remote_cleanup_ms"] = round((time.perf_counter() - cleanup_started) * 1000, 3)


def execute(
    args: argparse.Namespace,
    client: paramiko.SSHClient | None = None,
    sftp: paramiko.SFTPClient | None = None,
    timings: dict[str, float] | None = None,
) -> int:
    """Execute one request, optionally reusing a caller-owned SSH client."""

    if args.upload_only and not args.upload:
        raise SystemExit("--upload-only 至少需要一个 --upload。")
    if not args.upload_only and not (args.script or args.python_args or args.command):
        raise SystemExit("必须提供 --command、--script 或 --python 之一。")
    total_started = time.perf_counter()
    phase_timings = timings if timings is not None else {}
    owns_client = client is None
    if client is None:
        connect_started = time.perf_counter()
        client = connect(args)
        phase_timings["connect_auth_ms"] = round((time.perf_counter() - connect_started) * 1000, 3)
    else:
        phase_timings["connect_auth_ms"] = 0.0
    try:
        upload_started = time.perf_counter()
        owns_sftp = sftp is None
        operation_sftp = sftp if sftp is not None else client.open_sftp()
        try:
            upload_files(operation_sftp, args.upload)
        finally:
            if owns_sftp:
                operation_sftp.close()
        phase_timings["prestage_upload_ms"] = round((time.perf_counter() - upload_started) * 1000, 3)

        if args.upload_only:
            print(f"[upload-only] {len(args.upload)} file(s) staged")
            return 0

        print(f"[remote] {args.user}@{args.host} cwd={args.workdir}")
        exit_code = run_powershell(client, args, sftp=sftp, timings=phase_timings)
        print(f"[exit] {exit_code}")

        if args.download:
            download_started = time.perf_counter()
            download_sftp = sftp if sftp is not None else client.open_sftp()
            try:
                download_files(download_sftp, args.download)
            finally:
                if sftp is None:
                    download_sftp.close()
            phase_timings["download_ms"] = round((time.perf_counter() - download_started) * 1000, 3)
        else:
            phase_timings["download_ms"] = 0.0
        return int(exit_code or 0)
    finally:
        if owns_client:
            client.close()
        phase_timings["total_ms"] = round((time.perf_counter() - total_started) * 1000, 3)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    timings: dict[str, float] = {}
    exit_code = execute(args, timings=timings)
    if args.emit_timing_json:
        print(json.dumps({"schema": "bf.remote-exec.timing.v1", "phases_ms": timings}, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
