"""Fix: restart both dashboard services + update scheduled task triggers."""
import base64, re, paramiko
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read_pwd():
    m = re.search(r"SSH 密码：([^\r\n]+)", (ROOT / "AGENTS.md").read_text(encoding="utf-8", errors="ignore"))
    return m.group(1).strip()

def run_ps(client, cmd, timeout=60):
    b64 = base64.b64encode(cmd.encode("utf-16-le")).decode()
    stdin, stdout, stderr = client.exec_command(
        f"powershell -NoProfile -EncodedCommand {b64}", timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    rc = stdout.channel.recv_exit_status()
    print(out.strip())
    if rc: print(f"[RC={rc}] {err[-300:]}" if err else "")
    return rc == 0

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("10.30.220.12", username="administrator", password=read_pwd(),
               timeout=15, look_for_keys=False, allow_agent=False)

# 1. Restart BOTH services via their runner scripts directly
print("=== Restarting services ===")
run_ps(client, r"""
$ErrorActionPreference = "Continue"

# Kill any existing python processes for both services
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
    Where-Object { $_.CommandLine -and ($_.CommandLine -like '*db_dashboard*server.py*' -or $_.CommandLine -like '*foreman_trend_server*') } |
    ForEach-Object { Stop-Process -Id ([int]$_.ProcessId) -Force -ErrorAction SilentlyContinue; Write-Output "KILLED $($_.ProcessId)" }

Start-Sleep 2

# Start heat dashboard (8891)
$heatRunner = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\standalone_heat_dashboard_8891\run_22012_heat_dashboard_8891.ps1'
if (Test-Path $heatRunner) {
    Start-Process -FilePath 'powershell.exe' -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',$heatRunner -WindowStyle Hidden
    Write-Output "HEAT: started"
} else { Write-Output "HEAT: runner missing" }

# Start foreman trend (8892)
$trendRunner = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\standalone_foreman_trend_8892\run_22012_foreman_trend_8892.ps1'
if (Test-Path $trendRunner) {
    Start-Process -FilePath 'powershell.exe' -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',$trendRunner -WindowStyle Hidden
    Write-Output "TREND: started"
} else { Write-Output "TREND: runner missing" }

Write-Output "Waiting 8 seconds..."
Start-Sleep 8
""", timeout=30)

# 2. Verify ports
print("\n=== Port status ===")
run_ps(client, r"""
foreach ($port in @(8891, 8892)) {
    $l = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
    Write-Output "PORT $port : $(if($l){'LISTEN PID '+$l.OwningProcess}else{'NOT LISTENING'})"
}
""", timeout=15)

# 3. Update scheduled tasks: add daily trigger for on-demand start
print("\n=== Update task triggers ===")
run_ps(client, r"""
$ErrorActionPreference = "Continue"

# Heat dashboard
$heatTask = Get-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName 'StandaloneHeatDashboard8891' -ErrorAction SilentlyContinue
if ($heatTask) {
    # Add a daily trigger at 00:05 so it can be started manually
    $ht = $heatTask.Triggers
    $hasDaily = ($ht | Where-Object { $_.TriggerType -eq 'Daily' }).Count -gt 0
    if (-not $hasDaily) {
        $newTrigger = New-ScheduledTaskTrigger -Daily -At '00:05'
        $heatTask.Triggers += $newTrigger
        Set-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName 'StandaloneHeatDashboard8891' -Trigger $heatTask.Triggers
        Write-Output "HEAT: daily trigger added"
    } else { Write-Output "HEAT: daily trigger exists" }
}

# Foreman trend
$trendTask = Get-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName 'StandaloneForemanTrend8892' -ErrorAction SilentlyContinue
if ($trendTask) {
    $tt = $trendTask.Triggers
    $hasDaily = ($tt | Where-Object { $_.TriggerType -eq 'Daily' }).Count -gt 0
    if (-not $hasDaily) {
        $newTrigger = New-ScheduledTaskTrigger -Daily -At '00:05'
        $trendTask.Triggers += $newTrigger
        Set-ScheduledTask -TaskPath '\BlastFurnaceServices\' -TaskName 'StandaloneForemanTrend8892' -Trigger $trendTask.Triggers
        Write-Output "TREND: daily trigger added"
    } else { Write-Output "TREND: daily trigger exists" }
}

# Show final task status
Get-ScheduledTask -TaskPath '\BlastFurnaceServices\*' | Where-Object { $_.TaskName -like '*8891*' -or $_.TaskName -like '*8892*' } | ForEach-Object {
    Write-Output "TASK $($_.TaskName): $($_.State) | Triggers: $(($_.Triggers | ForEach-Object { $_.TriggerType }) -join ',')"
}
""", timeout=30)

# 4. HTTP verification
print("\n=== HTTP check ===")
run_ps(client, r"""
try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8891/api/overview' -TimeoutSec 8; Write-Output "8891: HTTP $($r.StatusCode)" } catch { Write-Output "8891: FAIL" }
try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8892/foreman_trend_preview.html' -TimeoutSec 8; Write-Output "8892: HTTP $($r.StatusCode) $($r.RawContentLength)B" } catch { Write-Output "8892: FAIL" }
""", timeout=25)

client.close()
print("\n=== Done ===")
