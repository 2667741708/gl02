$ErrorActionPreference = "Continue"

$taskName = "StandaloneNginxDirectRelay"
$taskPath = "\BlastFurnaceServices\"
$psExe = "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
$runnerDir = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\standalone_nginx_direct_relay"
$nginxExe = "C:\Users\Administrator\Desktop\nginx-1.29.3\nginx.exe"
$nginxDir = "C:\Users\Administrator\Desktop\nginx-1.29.3"

Write-Output "=== Setup Nginx Daemon ==="

# Create runner directory
New-Item -ItemType Directory -Force -Path $runnerDir, "$runnerDir\logs" | Out-Null

# Write the runner script
$runnerScript = @'
$ErrorActionPreference = "Continue"
$logDir = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\standalone_nginx_direct_relay\logs"
$log = "$logDir\nginx_direct_relay.log"
$nginxExe = "C:\Users\Administrator\Desktop\nginx-1.29.3\nginx.exe"
$nginxDir = "C:\Users\Administrator\Desktop\nginx-1.29.3"

# Ensure netsh portproxy rules (idempotent)
netsh interface portproxy add v4tov4 listenaddress=10.30.220.12 listenport=15433 connectaddress=10.10.181.195 connectport=5432 2>$null
netsh interface portproxy add v4tov4 listenaddress=10.30.220.12 listenport=18889 connectaddress=10.22.181.243 connectport=8889 2>$null

while ($true) {
    $startedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $log -Encoding UTF8 -Value "$startedAt starting nginx direct relay"
    Set-Location -LiteralPath $nginxDir
    & $nginxExe
    $exitedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $log -Encoding UTF8 -Value "$exitedAt nginx exited $LASTEXITCODE; restart in 5s"
    Start-Sleep -Seconds 5
}
'@
$runnerPath = "$runnerDir\run_nginx_direct_relay.ps1"
[IO.File]::WriteAllText($runnerPath, $runnerScript, [Text.UTF8Encoding]::new($false))
Write-Output "Runner written: $runnerPath"

# Remove old task if exists
$old = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
if ($old) {
    Stop-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
    Start-Sleep 1
    Unregister-ScheduledTask -TaskPath $taskPath -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Output "Removed old task"
}

# Create scheduled task
$action = New-ScheduledTaskAction -Execute $psExe -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runnerPath`""
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskPath $taskPath -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null

# Start it now
Start-ScheduledTask -TaskPath $taskPath -TaskName $taskName
Start-Sleep 4

$t = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName
Write-Output "Task: $($t.TaskName)  State: $($t.State)"

# Verify ports
Write-Output ""
Write-Output "=== Port Verification ==="
foreach ($port in @(18080, 15433, 18889)) {
    $l = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
    $status = if ($l) { "LISTENING PID $($l.OwningProcess)" } else { "NOT LISTENING" }
    Write-Output "Port $port : $status"
}

# Show all tasks for these relays
Write-Output ""
Write-Output "=== Relay Tasks in BlastFurnaceServices ==="
Get-ScheduledTask -TaskPath "\BlastFurnaceServices\*" -ErrorAction SilentlyContinue |
    Where-Object { $_.TaskName -match "Nginx|Heat|Foreman" } |
    Select-Object TaskName, State |
    Format-Table -AutoSize
