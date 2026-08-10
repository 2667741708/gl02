from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import paramiko


ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "AGENTS.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Register the authorized pSpace account in 220.12 machine environment.")
    parser.add_argument("--host", default="10.30.220.12")
    parser.add_argument("--user", default="administrator")
    parser.add_argument("--server", default="10.22.181.243")
    parser.add_argument("--port", default="8889")
    parser.add_argument("--sdk-root", default=r"F:\高炉炼铁项目-real-sensor-v2_V3\pythonSDK(1)")
    return parser.parse_args()


def read_authorized_pspace_account() -> tuple[str, str]:
    text = AGENTS.read_text(encoding="utf-8")
    line = next((item for item in text.splitlines() if "pSpace/PythonAPI 示例账号" in item), None)
    if line is None:
        raise RuntimeError("authorized pSpace example account entry not found")
    tokens = re.findall(r"`([^`]*)`", line)
    if len(tokens) < 2 or not tokens[0] or not tokens[1]:
        raise RuntimeError("authorized pSpace account entry is incomplete")
    return tokens[0], tokens[1]


def read_ssh_password() -> str:
    text = AGENTS.read_text(encoding="utf-8")
    match = re.search(r"SSH 密码：([^\r\n]+)", text)
    if match is None:
        raise RuntimeError("220.12 SSH password entry not found")
    return match.group(1).strip()


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def build_script(values: dict[str, str]) -> str:
    assignments = "\n".join(
        f"[Environment]::SetEnvironmentVariable({ps_quote(name)}, {ps_quote(value)}, 'Machine')"
        for name, value in values.items()
    )
    names = ", ".join(ps_quote(name) for name in values)
    return f"""
$ErrorActionPreference = 'Stop'
{assignments}
$result = foreach ($name in @({names})) {{
    $value = [Environment]::GetEnvironmentVariable($name, 'Machine')
    [pscustomobject]@{{ Name = $name; Present = -not [string]::IsNullOrWhiteSpace($value) }}
}}
$result | ConvertTo-Json -Compress
exit 0
""".strip()


def main() -> int:
    args = parse_args()
    username, password = read_authorized_pspace_account()
    values = {
        "PSPACE_SERVER": args.server,
        "PSPACE_PORT": args.port,
        "PSPACE_USER": username,
        "PSPACE_PASSWORD": password,
        "PSPACE_SDK_ROOT": args.sdk_root,
    }
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=args.host,
        username=args.user,
        password=read_ssh_password(),
        timeout=15,
        banner_timeout=15,
        auth_timeout=15,
        look_for_keys=False,
        allow_agent=False,
    )
    try:
        stdin, stdout, stderr = client.exec_command(
            "powershell.exe -NoProfile -ExecutionPolicy Bypass -Command -", timeout=30
        )
        stdin.write(build_script(values))
        stdin.flush()
        stdin.channel.shutdown_write()
        out = stdout.read().decode("utf-8", errors="replace").strip()
        err = stderr.read().decode("utf-8", errors="replace").strip()
        code = stdout.channel.recv_exit_status()
    finally:
        client.close()
    if err:
        print(err, file=sys.stderr)
    if code != 0:
        return code
    print("registered_machine_environment=true")
    if out:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
