# -*- coding: utf-8 -*-
"""Resume deployment from Phase 4 (scheduled task + restart + verify).
Run after deploy_all_to_22012.py if it timed out at Phase 4.
"""
from __future__ import annotations
import base64, os, re, sys, time
from pathlib import Path
import paramiko

ROOT = Path(__file__).resolve().parents[1]
HOST, USER = "10.30.220.12", "administrator"

def read_password():
    m = re.search(r"SSH 密码：([^\r\n]+)", (ROOT / "AGENTS.md").read_text(encoding="utf-8", errors="ignore"))
    if m: return m.group(1).strip()
    raise SystemExit("Cannot find SSH password")

def run_ps(client, cmd, timeout=60):
    utf16 = cmd.encode("utf-16-le")
    b64 = base64.b64encode(utf16).decode()
    stdin, stdout, stderr = client.exec_command(
        f'powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand {b64}', timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    rc = stdout.channel.recv_exit_status()
    if rc: print(f"  [RC={rc}] {err[-300:]}")
    return out, rc

def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=HOST, username=USER, password=read_password(),
                   timeout=15, look_for_keys=False, allow_agent=False)

    # Phase 4: Scheduled task for foreman trend (8892)
    print("[Phase 4] Scheduled task for foreman trend...")
    out, _ = run_ps(client, r"""
$ErrorActionPreference = "Continue"
$taskName = 'StandaloneForemanTrend8892'
$taskPath = '\BlastFurnaceServices\'
$runner = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\standalone_foreman_trend_8892\run_22012_foreman_trend_8892.ps1'
$psExe = 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'

Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue |
    ForEach-Object {
        Stop-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
        Start-Sleep 1
        Unregister-ScheduledTask -TaskPath $taskPath -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    }

$action = New-ScheduledTaskAction -Execute $psExe -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runner`""
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskPath $taskPath -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskPath $taskPath -TaskName $taskName
$t = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName
Write-Output "TASK: $($t.State)"
""", timeout=60)
    print(f"  {out.strip()}")

    # Phase 5: Restart heat dashboard
    print("[Phase 5] Restarting heat dashboard...")
    out, _ = run_ps(client, r"""
$ErrorActionPreference = "Continue"
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine -like '*db_dashboard*server.py*' } |
    ForEach-Object { Stop-Process -Id ([int]$_.ProcessId) -Force -ErrorAction SilentlyContinue; Write-Output "KILLED $($_.ProcessId)" }
Start-Sleep 2
$ht = Get-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName 'StandaloneHeatDashboard8891' -ErrorAction SilentlyContinue
if ($ht -and $ht.State -ne 'Running') { Start-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName 'StandaloneHeatDashboard8891'; Write-Output 'HEAT STARTED' } else { Write-Output "HEAT STATE: $($ht.State)" }
""", timeout=30)
    print(f"  {out.strip()}")

    # Phase 6: Verify
    print("[Phase 6] Verification...")
    time.sleep(8)
    out, _ = run_ps(client, r"""
foreach ($port in @(8891, 8892)) {
    $l = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
    Write-Output "PORT $port : $(if($l){'LISTEN PID '+$l.OwningProcess}else{'NOT LISTENING'})"
}
try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8891/api/overview' -TimeoutSec 5; Write-Output "8891 HTTP: $($r.StatusCode)" } catch { Write-Output "8891 HTTP: FAIL $_" }
try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8892/foreman_trend_preview.html' -TimeoutSec 5; Write-Output "8892 HTTP: $($r.StatusCode) $($r.RawContentLength)B" } catch { Write-Output "8892 HTTP: FAIL $_" }
""", timeout=30)
    print(out.strip())

    client.close()
    print("\n=== Done ===")
    print("Heat Dashboard : http://10.30.220.12:8891/")
    print("Foreman Trend  : http://10.30.220.12:8892/foreman_trend_preview.html?ws_port=8768")

if __name__ == "__main__":
    main()
