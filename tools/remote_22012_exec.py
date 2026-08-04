# -*- coding: utf-8 -*-
"""Execute commands on 10.30.220.12 from the local machine.

This is a small jump-host helper for the current SSLVPN workflow:

    local machine -> SSH -> 10.30.220.12 -> run tools/PythonSDK/MCP there

It does not connect to pSpace by itself. Use it to run commands on 220.12
where ghsc, pythonSDK(1), MCP, and 8092 production services live.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import os
import re
import sys
import time
from pathlib import Path

import paramiko


ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "AGENTS.md"
DEFAULT_REMOTE_ROOT = r"F:\高炉炼铁项目-real-sensor-v2_V3"


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


def parse_args() -> argparse.Namespace:
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
    parser.add_argument("--allow-agents-password", action="store_true")
    parser.add_argument("--prompt-password", action="store_true")
    parser.add_argument("--timeout", type=int, default=3600)
    parser.add_argument("--upload", action="append", type=parse_pair, default=[], help="Upload local=remote before running.")
    parser.add_argument("--download", action="append", type=parse_pair, default=[], help="Download remote=local after running.")
    parser.add_argument("--command", help="PowerShell command to run on 220.12.")
    parser.add_argument("--script", type=Path, help="Local .ps1 file to run on 220.12.")
    parser.add_argument("--python", dest="python_args", help="Run remote Python311 with these arguments from --workdir.")
    parser.add_argument("--no-profile", action="store_true", default=True)
    parser.add_argument("--keep-remote-script", action="store_true")
    return parser.parse_args()


def connect(args: argparse.Namespace) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    connect_timeout = max(1, min(30, args.timeout))
    client.connect(
        hostname=args.host,
        username=args.user,
        password=resolve_password(args),
        timeout=connect_timeout,
        banner_timeout=connect_timeout,
        auth_timeout=connect_timeout,
        look_for_keys=False,
        allow_agent=False,
    )
    return client


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


def build_remote_script(args: argparse.Namespace) -> str:
    if args.script:
        body = args.script.read_text(encoding="utf-8")
    elif args.python_args:
        escaped = args.python_args.replace("`", "``").replace('"', '`"')
        body = f'& "C:\\Program Files\\Python311\\python.exe" -X utf8 {escaped}'
    elif args.command:
        body = args.command
    else:
        raise SystemExit("必须提供 --command、--script 或 --python 之一。")

    return f"""
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$ProgressPreference = "SilentlyContinue"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
Set-Location -LiteralPath "{args.workdir}"
{body}
exit $LASTEXITCODE
""".strip()


def run_powershell(client: paramiko.SSHClient, script: str, args: argparse.Namespace) -> int:
    # Use EncodedCommand so Chinese paths are interpreted as UTF-16LE by PowerShell.
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    profile = "-NoProfile" if args.no_profile else ""
    command = f"powershell {profile} -ExecutionPolicy Bypass -EncodedCommand {encoded}"
    _, stdout, stderr = client.exec_command(command, timeout=args.timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    if out:
        print(out, end="" if out.endswith("\n") else "\n")
    if err:
        print(err, file=sys.stderr, end="" if err.endswith("\n") else "\n")
    return stdout.channel.recv_exit_status()


def main() -> int:
    args = parse_args()
    script = build_remote_script(args)
    client = connect(args)
    try:
        sftp = client.open_sftp()
        try:
            upload_files(sftp, args.upload)
        finally:
            sftp.close()

        print(f"[remote] {args.user}@{args.host} cwd={args.workdir}")
        exit_code = run_powershell(client, script, args)
        print(f"[exit] {exit_code}")

        if args.download:
            sftp = client.open_sftp()
            try:
                download_files(sftp, args.download)
            finally:
                sftp.close()
        return int(exit_code or 0)
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
