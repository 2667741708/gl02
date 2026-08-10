# -*- coding: utf-8 -*-
"""一键部署脚本：把热仪表盘修复 + 工长趋势部署到 220.12 并持久化。

使用方式（本机执行）：
    python tools/deploy_all_to_22012.py

前提：
    - SSLVPN 已连接（能访问 10.30.220.12）
    - Python 环境有 paramiko（pip install paramiko）
"""

from __future__ import annotations

import os, re, sys, time
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
REMOTE_ROOT = r"F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
HOST = "10.30.220.12"
USER = "administrator"

# --- Files to upload: local -> remote ---
UPLOADS = [
    # Foreman trend frontend assets
    ("高炉前端数据/foreman_trend_preview.html",
     f"{REMOTE_ROOT}\\高炉前端数据\\foreman_trend_preview.html"),
    ("高炉前端数据/assets/foreman-trend-preview.css",
     f"{REMOTE_ROOT}\\高炉前端数据\\assets\\foreman-trend-preview.css"),
    ("高炉前端数据/assets/foreman-trend-preview.js",
     f"{REMOTE_ROOT}\\高炉前端数据\\assets\\foreman-trend-preview.js"),
    # Foreman trend server + runner
    ("tools/foreman_trend_server.py",
     f"{REMOTE_ROOT}\\standalone_foreman_trend_8892\\tools\\foreman_trend_server.py"),
    ("tools/run_22012_foreman_trend_8892.ps1",
     f"{REMOTE_ROOT}\\standalone_foreman_trend_8892\\run_22012_foreman_trend_8892.ps1"),
    # Deploy script (for reference)
    ("tools/deploy_22012_dashboard_suite.ps1",
     f"{REMOTE_ROOT}\\tools\\deploy_22012_dashboard_suite.ps1"),
]


def read_password() -> str:
    agents = ROOT / "AGENTS.md"
    if agents.exists():
        text = agents.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"SSH 密码：([^\r\n]+)", text)
        if m:
            return m.group(1).strip()
    raise SystemExit("Cannot find SSH password in AGENTS.md")


def sftp_mkdirs(sftp: paramiko.SFTPClient, remote_path: str) -> None:
    normalized = remote_path.replace("\\", "/")
    parts = normalized.split("/")
    if re.match(r"^[A-Za-z]:$", parts[0]):
        current = parts[0] + "/"
        parts = parts[1:]
    else:
        current = "/"
    for part in parts:
        current = current.rstrip("/") + "/" + part
        try:
            sftp.stat(current)
        except IOError:
            try:
                sftp.mkdir(current)
            except IOError:
                pass


def upload_files(sftp, uploads):
    for local_rel, remote in uploads:
        local = ROOT / local_rel
        if not local.exists():
            print(f"  MISSING: {local}")
            continue
        sftp_mkdirs(sftp, str(Path(remote).parent))
        sftp.put(str(local), remote)
        print(f"  [OK] {local_rel} -> {remote}")


def run_ps(client, cmd, timeout=60):
    """Run a PowerShell command using base64 encoding to avoid escaping issues."""
    import base64
    # Convert PowerShell script to UTF-16LE then base64 (required by -EncodedCommand)
    utf16 = cmd.encode("utf-16-le")
    b64 = base64.b64encode(utf16).decode()
    wrapped = f'powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand {b64}'
    stdin, stdout, stderr = client.exec_command(wrapped, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    rc = stdout.channel.recv_exit_status()
    if rc != 0:
        print(f"  [RC={rc}] {err[-300:] if err else ''}")
    return out, rc


def main():
    password = read_password()
    print(f"Connecting to {USER}@{HOST}...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=HOST, username=USER, password=password,
                   timeout=15, look_for_keys=False, allow_agent=False)
    sftp = client.open_sftp()

    # === Phase 1: Upload all files ===
    print("\n[Phase 1] Uploading files...")
    upload_files(sftp, UPLOADS)

    # Also copy echarts from existing location on server
    print("\n[Phase 1b] Copying echarts on server...")
    out, _ = run_ps(client, "Copy-Item 'F:/高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW/高炉前端数据/libs/echarts.min.js' 'F:/高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW/standalone_foreman_trend_8892/高炉前端数据/libs/echarts.min.js' -Force -ErrorAction SilentlyContinue; echo DONE")
    print(f"  echarts: {'DONE' if 'DONE' in out else 'skipped'}")

    # === Phase 2: Patch heat dashboard ===
    print("\n[Phase 2] Patching heat dashboard (8891)...")
    patch_cmd = r"""
$hs = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\standalone_heat_dashboard_8891\db_dashboard\heat_service.py'
if (Test-Path $hs) {
    $c = Get-Content -LiteralPath $hs -Raw -Encoding UTF8
    if ($c -match '_setting\("IMES_OPS_DB_USER"') {
        $c = $c -replace '_setting\("IMES_OPS_DB_USER", file_values\)', 'os.getenv("IMES_OPS_DB_USER") or file_values.get("IMES_OPS_DB_USER") or file_values.get("IMES_DB_USER")'
        $c = $c -replace '_setting\("IMES_OPS_DB_PASSWORD", file_values\)', 'os.getenv("IMES_OPS_DB_PASSWORD") or file_values.get("IMES_OPS_DB_PASSWORD") or file_values.get("IMES_DB_PASSWORD")'
        [IO.File]::WriteAllText($hs, $c, [Text.UTF8Encoding]::new($false))
        Write-Output 'PATCHED'
    } else { Write-Output 'SKIP' }
} else { Write-Output 'MISSING' }
"""
    out, _ = run_ps(client, patch_cmd, timeout=15)
    print(f"  heat_service.py: {out.strip()}")

    # === Phase 3: Firewall rules ===
    print("\n[Phase 3] Firewall rules...")
    for port, name in [(8891, "BlastFurnaceStandaloneHeatDashboard8891"),
                        (8892, "BlastFurnaceForemanTrend8892")]:
        run_ps(client, f"if (-not (Get-NetFirewallRule -Name '{name}' -ErrorAction SilentlyContinue)) {{ New-NetFirewallRule -Name '{name}' -DisplayName '{name}' -Direction Inbound -Action Allow -Protocol TCP -LocalPort {port} -Profile Domain,Private | Out-Null; Write-Output 'CREATED {port}' }} else {{ Write-Output 'EXISTS {port}' }}", timeout=10)
        print(f"  Port {port}: done")

    # === Phase 4: Scheduled task for foreman trend ===
    print("\n[Phase 4] Scheduled task for foreman trend (8892)...")
    task_cmd = r"""
$taskName = 'StandaloneForemanTrend8892'
$taskPath = '\BlastFurnaceServices\'
$runner = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\standalone_foreman_trend_8892\run_22012_foreman_trend_8892.ps1'
$psExe = 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue | ForEach-Object { Stop-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue; Start-Sleep 1; Unregister-ScheduledTask -TaskPath $taskPath -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue }
$action = New-ScheduledTaskAction -Execute $psExe -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runner`""
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskPath $taskPath -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskPath $taskPath -TaskName $taskName
$t = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName
Write-Output "TASK: $($t.State)"
"""
    out, _ = run_ps(client, task_cmd, timeout=60)
    print(f"  {out.strip()}")

    # === Phase 5: Restart heat dashboard ===
    print("\n[Phase 5] Restarting heat dashboard...")
    restart_cmd = r"""
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object { $_.CommandLine -and $_.CommandLine -like '*db_dashboard*server.py*' } | ForEach-Object { Stop-Process -Id ([int]$_.ProcessId) -Force -ErrorAction SilentlyContinue; Write-Output "KILLED $($_.ProcessId)" }
Start-Sleep 2
$ht = Get-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName 'StandaloneHeatDashboard8891' -ErrorAction SilentlyContinue
if ($ht -and $ht.State -ne 'Running') { Start-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName 'StandaloneHeatDashboard8891'; Write-Output 'STARTED' } else { Write-Output "STATE: $($ht.State)" }
"""
    out, _ = run_ps(client, restart_cmd, timeout=15)
    print(f"  {out.strip()}")

    # === Phase 6: Verify ===
    print("\n[Phase 6] Verification...")
    time.sleep(6)
    verify_cmd = r"""
foreach ($port in @(8891, 8892)) {
    $l = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
    Write-Output "PORT $port : $(if($l){'LISTEN PID '+$l.OwningProcess}else{'NOT LISTENING'})"
}
try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8891/api/overview' -TimeoutSec 5; Write-Output "8891 HTTP: $($r.StatusCode)" } catch { Write-Output "8891 HTTP: FAIL" }
try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8892/foreman_trend_preview.html' -TimeoutSec 5; Write-Output "8892 HTTP: $($r.StatusCode) $($r.RawContentLength)B" } catch { Write-Output "8892 HTTP: FAIL" }
"""
    out, _ = run_ps(client, verify_cmd, timeout=20)
    print(out.strip())

    sftp.close()
    client.close()

    print("\n=== Deployment Complete ===")
    print("Heat Dashboard : http://10.30.220.12:8891/")
    print("Foreman Trend  : http://10.30.220.12:8892/foreman_trend_preview.html?ws_port=8768")


if __name__ == "__main__":
    main()
