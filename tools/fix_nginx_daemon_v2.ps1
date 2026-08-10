$ErrorActionPreference = "Continue"
$taskName = "StandaloneNginxDirectRelay"
$taskPath = "\BlastFurnaceServices\"
$nginxExe = "C:\Users\Administrator\Desktop\nginx-1.29.3\nginx.exe"
$nginxDir = "C:\Users\Administrator\Desktop\nginx-1.29.3"
$runnerDir = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\standalone_nginx_direct_relay"

Write-Output "=== Fix Nginx Daemon v2 ==="

# 1. Remove broken old task
Write-Output "[1] Removing old task..."
$old = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
if ($old) {
    Stop-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
    Start-Sleep 1
    Unregister-ScheduledTask -TaskPath $taskPath -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Output "  Removed old task"
}

# 2. Write simpler runner (no here-string nesting issues)
Write-Output "[2] Writing runner..."
New-Item -ItemType Directory -Force -Path $runnerDir, "$runnerDir\logs" | Out-Null

$runnerLines = @(
    '$ErrorActionPreference = "Continue"',
    '$log = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\standalone_nginx_direct_relay\logs\nginx_direct_relay.log"',
    'while ($true) {',
    '  $msg = "$(Get-Date -Format ''yyyy-MM-dd HH:mm:ss'') starting nginx"',
    '  Add-Content -LiteralPath $log -Encoding UTF8 -Value $msg',
    '  Set-Location -LiteralPath "C:\Users\Administrator\Desktop\nginx-1.29.3"',
    '  & "C:\Users\Administrator\Desktop\nginx-1.29.3\nginx.exe" *>> $log',
    '  $msg2 = "$(Get-Date -Format ''yyyy-MM-dd HH:mm:ss'') nginx exited $LASTEXITCODE; restart in 5s"',
    '  Add-Content -LiteralPath $log -Encoding UTF8 -Value $msg2',
    '  Start-Sleep -Seconds 5',
    '}'
)
$runnerPath = "$runnerDir\run_nginx.ps1"
[IO.File]::WriteAllLines($runnerPath, $runnerLines, [Text.UTF8Encoding]::new($false))
Write-Output "  Written: $runnerPath"

# 3. Create scheduled task
Write-Output "[3] Creating task..."
$psExe = "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
$action = New-ScheduledTaskAction -Execute $psExe -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runnerPath`""
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskPath $taskPath -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null

# 4. Verify task registration
$t = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName
$triggers = ($t.Triggers | ForEach-Object { $_.TriggerType }) -join ','
Write-Output "  Task: $($t.State) | Triggers: $triggers | Principal: $($t.Principal.UserId)"

# 5. Start it now
Write-Output "[4] Starting task..."
Start-ScheduledTask -TaskPath $taskPath -TaskName $taskName
Start-Sleep 5

$t2 = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName
$info = Get-ScheduledTaskInfo -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
Write-Output "  State: $($t2.State)"
Write-Output "  LastRun: $($info.LastRunTime)  Result: $($info.LastTaskResult)"

# 6. Log check
Write-Output "[5] Checking log..."
if (Test-Path "$runnerDir\logs\nginx_direct_relay.log") {
    $logContent = Get-Content -Tail 5 "$runnerDir\logs\nginx_direct_relay.log"
    Write-Output $logContent
} else {
    Write-Output "  No log file yet (runner may still be starting)"
}

# 7. Port verification
Write-Output "[6] Port verification..."
foreach ($port in @(18080, 15433, 18889)) {
    $l = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($l) {
        $procName = (Get-Process -Id $l.OwningProcess -ErrorAction SilentlyContinue).ProcessName
        Write-Output "  Port $port : LISTENING PID $($l.OwningProcess) ($procName)"
    } else {
        Write-Output "  Port $port : NOT LISTENING"
    }
}

Write-Output "=== Done ==="
