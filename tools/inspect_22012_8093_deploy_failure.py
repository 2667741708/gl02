"""Read-only diagnostics for BFV4PreviewProxy8093 deployment/start failures."""
from __future__ import annotations

import json

import paramiko

from deploy_22012_top_pressure_mcp_fix import (
    HOST,
    REMOTE_BACKEND,
    REMOTE_CONTEXT,
    REMOTE_MCP,
    USER,
    password_from_config,
    port_state,
    powershell,
    run,
)


def main() -> int:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    ssh.load_system_host_keys()
    ssh.connect(HOST, username=USER, password=password_from_config(), timeout=15)
    try:
        service_json = powershell(
            ssh,
            """
$service=Get-CimInstance Win32_Service -Filter "Name='BFV4PreviewProxy8093'"
$events=Get-WinEvent -FilterHashtable @{LogName='System';ProviderName='Service Control Manager';StartTime=(Get-Date).AddMinutes(-30)} -ErrorAction SilentlyContinue |
  Where-Object {$_.Message -match 'BFV4PreviewProxy8093|Blast Furnace V4 Preview Proxy 8093'} |
  Select-Object -First 12 TimeCreated,Id,LevelDisplayName,Message
$hashes=@{}
foreach($path in @(
  'F:\\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\\高炉前端数据\\智能助手\\backend\\ollama_proxy_server.py',
  'F:\\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\\高炉前端数据\\智能助手\\backend\\mcp_conversation_context.py',
  'F:\\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\\高炉前端数据\\智能助手\\mcp\\bf_data_mcp_server.py'
)){
  if(Test-Path -LiteralPath $path){$hashes[$path]=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash}
}
[pscustomobject]@{
  service=[pscustomobject]@{
    state=$service.State
    status=$service.Status
    processId=$service.ProcessId
    pathName=$service.PathName
    exitCode=$service.ExitCode
    serviceSpecificExitCode=$service.ServiceSpecificExitCode
  }
  events=@($events)
  hashes=$hashes
} | ConvertTo-Json -Depth 6 -Compress
""",
            timeout=120,
        )
        code, _, compile_err = run(
            ssh,
            '& "C:\\Program Files\\Python311\\python.exe" -m py_compile '
            f'"{REMOTE_BACKEND.lstrip("/").replace("/", chr(92))}" '
            f'"{REMOTE_CONTEXT.lstrip("/").replace("/", chr(92))}" '
            f'"{REMOTE_MCP.lstrip("/").replace("/", chr(92))}"',
            timeout=90,
        )
        print(
            json.dumps(
                {
                    "ports": port_state(ssh),
                    "service": json.loads(service_json),
                    "remote_py_compile": {"exit_code": code, "stderr": compile_err},
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    finally:
        ssh.close()


if __name__ == "__main__":
    raise SystemExit(main())
