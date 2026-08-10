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
    return parser.parse_args()


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
                transport.set_keepalive(10)
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


def run_powershell(client: paramiko.SSHClient, args: argparse.Namespace) -> int:
    """Stage UTF-8 scripts and execute them with a short PowerShell 7 -File command."""

    token = uuid.uuid4().hex
    temp_root = r"C:\Users\Administrator\AppData\Local\Temp"
    wrapper_path = rf"{temp_root}\bf_remote_exec_{token}.ps1"
    payload_path = rf"{temp_root}\bf_remote_payload_{token}.ps1" if args.script else None
    remote_paths = [wrapper_path]
    if payload_path:
        remote_paths.append(payload_path)

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
        sftp.close()

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
        _, stdout, stderr = client.exec_command(invocation, timeout=args.timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        if out:
            print(out, end="" if out.endswith("\n") else "\n")
        if err:
            print(err, file=sys.stderr, end="" if err.endswith("\n") else "\n")
        return stdout.channel.recv_exit_status()
    finally:
        if not args.keep_remote_script:
            sftp = client.open_sftp()
            try:
                for remote_path in remote_paths:
                    try:
                        sftp.remove(remote_path)
                    except OSError:
                        pass
            finally:
                sftp.close()


def main() -> int:
    args = parse_args()
    if args.upload_only and not args.upload:
        raise SystemExit("--upload-only 至少需要一个 --upload。")
    if not args.upload_only and not (args.script or args.python_args or args.command):
        raise SystemExit("必须提供 --command、--script 或 --python 之一。")
    client = connect(args)
    try:
        sftp = client.open_sftp()
        try:
            upload_files(sftp, args.upload)
        finally:
            sftp.close()

        if args.upload_only:
            print(f"[upload-only] {len(args.upload)} file(s) staged")
            return 0

        print(f"[remote] {args.user}@{args.host} cwd={args.workdir}")
        exit_code = run_powershell(client, args)
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
