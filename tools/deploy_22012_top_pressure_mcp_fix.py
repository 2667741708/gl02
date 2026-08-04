"""Deploy the top-pressure MCP colloquial fix to the shared 8093/8094 backend.

Only the two QA proxy processes are restarted. The 8768 and 8770 data services
are treated as protected dependencies and must keep the same process IDs.

Requirement: BUG-8093-MCP-TOP-PRESSURE-HOW-20260726
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path

import paramiko


ROOT = Path(__file__).resolve().parents[1]
SSH_CONFIG = Path.home() / ".ssh" / "jngt_ssh_config"
HOST = "10.30.220.12"
USER = "administrator"
REMOTE_ROOT = "/F:/高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
REMOTE_BACKEND = f"{REMOTE_ROOT}/高炉前端数据/智能助手/backend/ollama_proxy_server.py"
REMOTE_MCP = f"{REMOTE_ROOT}/高炉前端数据/智能助手/mcp/bf_data_mcp_server.py"
REMOTE_POLICY = f"{REMOTE_ROOT}/高炉前端数据/智能助手/backend/mcp_tool_policy.py"
REMOTE_CONTEXT = f"{REMOTE_ROOT}/高炉前端数据/智能助手/backend/mcp_conversation_context.py"
REMOTE_BUSINESS_CATALOG = f"{REMOTE_ROOT}/高炉前端数据/智能助手/mcp/business_object_catalog.py"
REMOTE_CATALOG_DIR = f"{REMOTE_ROOT}/高炉前端数据/智能助手/mcp/catalog"
LOCAL_BACKEND = ROOT / "高炉前端数据" / "智能助手" / "backend" / "ollama_proxy_server.py"
LOCAL_MCP = ROOT / "高炉前端数据" / "智能助手" / "mcp" / "bf_data_mcp_server.py"
LOCAL_POLICY = ROOT / "高炉前端数据" / "智能助手" / "backend" / "mcp_tool_policy.py"
LOCAL_CONTEXT = ROOT / "高炉前端数据" / "智能助手" / "backend" / "mcp_conversation_context.py"
LOCAL_BUSINESS_CATALOG = ROOT / "高炉前端数据" / "智能助手" / "mcp" / "business_object_catalog.py"
LOCAL_CATALOG_DIR = ROOT / "高炉前端数据" / "智能助手" / "mcp" / "catalog"
CATALOG_FILENAMES = (
    "business_object.schema.json",
    "catalog_manifest.json",
    "sensors.json",
    "heat_analysis.json",
    "calculation_tools.json",
    "chart_capabilities.json",
    "knowledge_assets.json",
)
TEMP_BACKEND = "/C:/Windows/Temp/codex_top_pressure_backend.py"
TEMP_MCP = "/C:/Windows/Temp/codex_top_pressure_mcp.py"
TEMP_POLICY = "/C:/Windows/Temp/codex_mcp_tool_policy.py"
TEMP_CONTEXT = "/C:/Windows/Temp/mcp_conversation_context.py"
TEMP_BUSINESS_CATALOG = "/C:/Windows/Temp/business_object_catalog.py"


def password_from_config() -> str:
    text = SSH_CONFIG.read_text(encoding="utf-8")
    match = re.search(r"^#\s*SSH password:\s*(.+)$", text, re.MULTILINE)
    if not match:
        raise RuntimeError("SSH password entry is missing from the local private SSH config")
    return match.group(1).strip()


def run(ssh: paramiko.SSHClient, command: str, timeout: int = 90) -> tuple[int, str, str]:
    _, stdout, stderr = ssh.exec_command(command, timeout=timeout)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    return stdout.channel.recv_exit_status(), out, err


def powershell(ssh: paramiko.SSHClient, command: str, timeout: int = 90) -> str:
    encoded = __import__("base64").b64encode(command.encode("utf-16le")).decode("ascii")
    code, out, err = run(
        ssh,
        f"powershell.exe -NoProfile -ExecutionPolicy Bypass -EncodedCommand {encoded}",
        timeout,
    )
    if code:
        raise RuntimeError(f"remote PowerShell failed ({code}): {err or out}")
    return out


def port_state(ssh: paramiko.SSHClient) -> dict[str, int | None]:
    command = """
$ports=8093,8094,8768,8770
$result=@{}
foreach($port in $ports){
  $row=Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  $result[[string]$port]=if($row){[int]$row.OwningProcess}else{$null}
}
$result | ConvertTo-Json -Compress
"""
    return json.loads(powershell(ssh, command))


def wait_ports(ssh: paramiko.SSHClient, expected: dict[str, bool], timeout: int = 120) -> dict[str, int | None]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = port_state(ssh)
        if all(bool(state.get(port)) is listening for port, listening in expected.items()):
            return state
        time.sleep(1)
    raise RuntimeError(f"ports did not reach expected state: expected={expected}, actual={port_state(ssh)}")


def main() -> int:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backend_backup = f"{REMOTE_BACKEND}.bak_top_pressure_how_{stamp}"
    mcp_backup = f"{REMOTE_MCP}.bak_top_pressure_how_{stamp}"
    policy_backup = f"{REMOTE_POLICY}.bak_agent_orchestration_{stamp}"
    context_backup = f"{REMOTE_CONTEXT}.bak_conversation_context_{stamp}"
    business_catalog_backup = f"{REMOTE_BUSINESS_CATALOG}.bak_business_catalog_{stamp}"
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
    ssh.load_system_host_keys()
    ssh.connect(HOST, username=USER, password=password_from_config(), timeout=15)
    sftp = ssh.open_sftp()
    backed_up = False
    policy_existed = False
    context_existed = False
    business_catalog_existed = False
    catalog_existed: dict[str, bool] = {}
    before = port_state(ssh)
    if not all(before.get(port) for port in ("8093", "8094", "8768", "8770")):
        raise RuntimeError(f"required listeners are not all available: {before}")
    protected = {port: before[port] for port in ("8768", "8770")}
    try:
        sftp.put(str(LOCAL_BACKEND), TEMP_BACKEND)
        sftp.put(str(LOCAL_MCP), TEMP_MCP)
        sftp.put(str(LOCAL_POLICY), TEMP_POLICY)
        sftp.put(str(LOCAL_CONTEXT), TEMP_CONTEXT)
        sftp.put(str(LOCAL_BUSINESS_CATALOG), TEMP_BUSINESS_CATALOG)
        code, _, err = run(
            ssh,
            '& "C:\\Program Files\\Python311\\python.exe" -m py_compile '
            'C:\\Windows\\Temp\\codex_top_pressure_backend.py '
            'C:\\Windows\\Temp\\codex_top_pressure_mcp.py '
            'C:\\Windows\\Temp\\codex_mcp_tool_policy.py '
            'C:\\Windows\\Temp\\mcp_conversation_context.py '
            'C:\\Windows\\Temp\\business_object_catalog.py',
        )
        if code:
            raise RuntimeError(f"remote staged py_compile failed: {err}")

        powershell(
            ssh,
            """
Stop-ScheduledTask -TaskPath '\\BlastFurnaceServices\\' -TaskName 'V3AutoPreviewProxy8094' -ErrorAction SilentlyContinue
Stop-Service -Name 'BFV4PreviewProxy8093' -Force -ErrorAction Stop
Start-Sleep -Seconds 2
$p8094=Get-NetTCPConnection -LocalPort 8094 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if($p8094){Stop-Process -Id $p8094.OwningProcess -Force}
""",
        )
        wait_ports(ssh, {"8093": False, "8094": False})
        sftp.rename(REMOTE_BACKEND, backend_backup)
        sftp.rename(REMOTE_MCP, mcp_backup)
        try:
            sftp.stat(REMOTE_POLICY)
            policy_existed = True
            sftp.rename(REMOTE_POLICY, policy_backup)
        except OSError:
            policy_existed = False
        try:
            sftp.stat(REMOTE_CONTEXT)
            context_existed = True
            sftp.rename(REMOTE_CONTEXT, context_backup)
        except OSError:
            context_existed = False
        backed_up = True
        try:
            sftp.stat(REMOTE_BUSINESS_CATALOG)
            business_catalog_existed = True
            sftp.rename(REMOTE_BUSINESS_CATALOG, business_catalog_backup)
        except OSError:
            business_catalog_existed = False
        try:
            sftp.stat(REMOTE_CATALOG_DIR)
        except OSError:
            sftp.mkdir(REMOTE_CATALOG_DIR)
        for filename in CATALOG_FILENAMES:
            remote_path = f"{REMOTE_CATALOG_DIR}/{filename}"
            backup_path = f"{remote_path}.bak_business_catalog_{stamp}"
            try:
                sftp.stat(remote_path)
                catalog_existed[filename] = True
                sftp.rename(remote_path, backup_path)
            except OSError:
                catalog_existed[filename] = False
        sftp.put(str(LOCAL_BACKEND), REMOTE_BACKEND)
        sftp.put(str(LOCAL_MCP), REMOTE_MCP)
        sftp.put(str(LOCAL_POLICY), REMOTE_POLICY)
        sftp.put(str(LOCAL_CONTEXT), REMOTE_CONTEXT)
        sftp.put(str(LOCAL_BUSINESS_CATALOG), REMOTE_BUSINESS_CATALOG)
        for filename in CATALOG_FILENAMES:
            sftp.put(str(LOCAL_CATALOG_DIR / filename), f"{REMOTE_CATALOG_DIR}/{filename}")

        powershell(
            ssh,
            """
Start-Service -Name 'BFV4PreviewProxy8093' -ErrorAction SilentlyContinue
Start-ScheduledTask -TaskPath '\\BlastFurnaceServices\\' -TaskName 'V3AutoPreviewProxy8094'
""",
        )
        after = wait_ports(
            ssh,
            {"8093": True, "8094": True, "8768": True, "8770": True},
        )
        if any(after[port] != protected[port] for port in protected):
            raise RuntimeError(f"protected data-service PID changed: before={protected}, after={after}")
        print(
            json.dumps(
                {
                    "ok": True,
                    "deployed_at": stamp,
                    "before": before,
                    "after": after,
                    "backend_backup": backend_backup,
                    "mcp_backup": mcp_backup,
                    "policy_backup": policy_backup if policy_existed else None,
                    "context_backup": context_backup if context_existed else None,
                    "business_catalog_backup": business_catalog_backup if business_catalog_existed else None,
                    "catalog_files": list(CATALOG_FILENAMES),
                },
                ensure_ascii=False,
            )
        )
        return 0
    except Exception:
        if backed_up:
            try:
                powershell(
                    ssh,
                    """
Stop-ScheduledTask -TaskPath '\\BlastFurnaceServices\\' -TaskName 'V3AutoPreviewProxy8094' -ErrorAction SilentlyContinue
Stop-Service -Name 'BFV4PreviewProxy8093' -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
""",
                )
                for current, backup in (
                    (REMOTE_BACKEND, backend_backup),
                    (REMOTE_MCP, mcp_backup),
                ):
                    try:
                        sftp.remove(current)
                    except OSError:
                        pass
                    sftp.rename(backup, current)
                try:
                    sftp.remove(REMOTE_POLICY)
                except OSError:
                    pass
                if policy_existed:
                    sftp.rename(policy_backup, REMOTE_POLICY)
                try:
                    sftp.remove(REMOTE_CONTEXT)
                except OSError:
                    pass
                if context_existed:
                    sftp.rename(context_backup, REMOTE_CONTEXT)
                try:
                    sftp.remove(REMOTE_BUSINESS_CATALOG)
                except OSError:
                    pass
                if business_catalog_existed:
                    sftp.rename(business_catalog_backup, REMOTE_BUSINESS_CATALOG)
                for filename in CATALOG_FILENAMES:
                    remote_path = f"{REMOTE_CATALOG_DIR}/{filename}"
                    try:
                        sftp.remove(remote_path)
                    except OSError:
                        pass
                    if catalog_existed.get(filename):
                        sftp.rename(
                            f"{remote_path}.bak_business_catalog_{stamp}",
                            remote_path,
                        )
                powershell(
                    ssh,
                    """
Start-Service -Name 'BFV4PreviewProxy8093' -ErrorAction SilentlyContinue
Start-ScheduledTask -TaskPath '\\BlastFurnaceServices\\' -TaskName 'V3AutoPreviewProxy8094'
""",
                )
                restored = wait_ports(
                    ssh,
                    {"8093": True, "8094": True, "8768": True, "8770": True},
                )
                if any(restored[port] != protected[port] for port in protected):
                    raise RuntimeError(
                        f"rollback restored proxy services but protected PID changed: "
                        f"before={protected}, after={restored}"
                    )
            except Exception as rollback_error:
                raise RuntimeError(f"deployment failed and rollback also failed: {rollback_error}")
        raise
    finally:
        for path in (TEMP_BACKEND, TEMP_MCP, TEMP_POLICY, TEMP_CONTEXT, TEMP_BUSINESS_CATALOG):
            try:
                sftp.remove(path)
            except OSError:
                pass
        sftp.close()
        ssh.close()


if __name__ == "__main__":
    raise SystemExit(main())
