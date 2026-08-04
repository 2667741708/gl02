from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
import winreg

import paramiko


ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "AGENTS.md"


def read_agents_password() -> str:
    text = AGENTS.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"SSH 密码：([^\r\n]+)", text)
    if not match:
        raise SystemExit("Cannot find SSH password in AGENTS.md.")
    return match.group(1).strip()


def read_remote_reader_password() -> str:
    script = """
$v = [Environment]::GetEnvironmentVariable('GL02_READER_PASSWORD', 'Machine')
if (-not $v) { $v = [Environment]::GetEnvironmentVariable('GL02_READER_PASSWORD', 'User') }
if (-not $v) { throw 'GL02_READER_PASSWORD is missing on 220.12' }
[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($v))
""".strip()
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=os.getenv("BF_22012_HOST", "10.30.220.12"),
        username=os.getenv("BF_22012_USER", "administrator"),
        password=os.getenv("BF_22012_SSH_PASSWORD") or read_agents_password(),
        timeout=30,
        banner_timeout=60,
        auth_timeout=30,
        look_for_keys=False,
        allow_agent=False,
    )
    try:
        _, stdout, stderr = client.exec_command(
            f"powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand {encoded}",
            timeout=60,
        )
        out = stdout.read().decode("utf-8", errors="replace").strip()
        err = stderr.read().decode("utf-8", errors="replace").strip()
        code = stdout.channel.recv_exit_status()
        if code != 0:
            raise RuntimeError(err or out or f"remote reader password read failed: {code}")
        return base64.b64decode(out).decode("utf-8")
    finally:
        client.close()


def set_user_env(name: str, value: str) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
    os.environ[name] = value


def main() -> int:
    password = read_remote_reader_password()
    values = {
        "GL02_PGHOST": "10.30.220.12",
        "GL02_PGPORT": "5432",
        "GL02_PGDATABASE": "bf_trend",
        "GL02_PGUSER": "gl02_reader",
        "GL02_PGPASSWORD": password,
        "DB_CLIENT_CIDR": "10.30.200.18/32",
    }
    for name, value in values.items():
        set_user_env(name, value)
    print(json.dumps({"ok": True, "configured": {name: len(value) for name, value in values.items()}}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
