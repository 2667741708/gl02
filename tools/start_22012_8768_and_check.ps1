$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$ErrorActionPreference = "Continue"

$taskPath = "\BlastFurnaceServices\"
$taskName = "V4PreviewWs8768"

Write-Host "=== REMOTE_NOW ==="
Get-Date -Format "yyyy-MM-dd HH:mm:ss"

Write-Host "=== START_TASK ==="
try {
  Start-ScheduledTask -TaskPath $taskPath -TaskName $taskName
  Write-Host "Start-ScheduledTask submitted"
} catch {
  Write-Host ("Start-ScheduledTask failed: " + $_.Exception.Message)
}

Start-Sleep -Seconds 10

Write-Host "=== TASK_STATE ==="
try {
  Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName |
    Select-Object TaskPath,TaskName,State |
    Format-List
  Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName |
    Get-ScheduledTaskInfo |
    Select-Object LastRunTime,LastTaskResult,NextRunTime,NumberOfMissedRuns |
    Format-List
} catch {
  Write-Host ("Task query failed: " + $_.Exception.Message)
}

Write-Host "=== PORT_8768 ==="
$listeners = Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue
if ($listeners) {
  $listeners | Select-Object LocalAddress,LocalPort,OwningProcess | Format-Table -AutoSize
  foreach ($listener in $listeners) {
    Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue |
      Select-Object Id,ProcessName,Path,StartTime |
      Format-List
  }
} else {
  Write-Host "NO_LISTENER_8768"
}

Write-Host "=== RECENT_LOGS ==="
$logDir = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs"
foreach ($name in @("ws_8768.guard.log", "ws_8768.out.log", "ws_8768.err.log")) {
  $path = Join-Path $logDir $name
  Write-Host "--- $name ---"
  if (Test-Path -LiteralPath $path) {
    Get-Item -LiteralPath $path | Select-Object FullName,Length,LastWriteTime | Format-List
    Get-Content -LiteralPath $path -Tail 20 -ErrorAction SilentlyContinue
  } else {
    Write-Host "MISSING"
  }
}
