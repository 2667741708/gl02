$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$ErrorActionPreference = "Continue"

function Write-Section {
  param([string]$Name)
  Write-Host ""
  Write-Host ("===== {0} =====" -f $Name)
}

function Ensure-TaskForPort {
  param(
    [string]$TaskPath,
    [string]$TaskName,
    [int]$Port,
    [int]$WaitSeconds = 10
  )

  Write-Section ("ENSURE {0} PORT {1}" -f ($TaskPath + $TaskName), $Port)
  $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  if ($listener) {
    Write-Host ("port {0} already listening; skip task start" -f $Port)
  } else {
    try {
      Start-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName
      Write-Host ("Start-ScheduledTask submitted for {0}{1}" -f $TaskPath, $TaskName)
    } catch {
      Write-Host ("Start-ScheduledTask failed for {0}{1}: {2}" -f $TaskPath, $TaskName, $_.Exception.Message)
    }
    Start-Sleep -Seconds $WaitSeconds
  }

  $task = Get-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -ErrorAction SilentlyContinue
  if ($task) {
    $info = $task | Get-ScheduledTaskInfo
    [PSCustomObject]@{
      Task = $TaskPath + $TaskName
      State = $task.State
      Enabled = $task.Settings.Enabled
      LastRunTime = $info.LastRunTime
      LastTaskResult = $info.LastTaskResult
      NextRunTime = $info.NextRunTime
    } | Format-List
  } else {
    Write-Host ("task missing: {0}{1}" -f $TaskPath, $TaskName)
  }

  $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  if ($listener) {
    $listener | Select-Object LocalAddress,LocalPort,OwningProcess | Format-Table -AutoSize
    foreach ($item in $listener) {
      Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f $item.OwningProcess) |
        Select-Object ProcessId,Name,CreationDate,CommandLine |
        Format-List
    }
  } else {
    Write-Host ("NO_LISTENER_{0}" -f $Port)
  }
}

Write-Section "REMOTE_NOW"
Get-Date -Format "yyyy-MM-dd HH:mm:ss"

# 8093 can be served by an already-running independent process while its scheduled
# task is Ready. Only start the proxy task if the port is actually down.
Ensure-TaskForPort -TaskPath "\BlastFurnaceServices\" -TaskName "V4PreviewProxy8093" -Port 8093 -WaitSeconds 12
Ensure-TaskForPort -TaskPath "\BlastFurnaceServices\" -TaskName "V4PreviewWs8768" -Port 8768 -WaitSeconds 12

Write-Section "8093_AUTOMATION_STATUS"
try {
  $status = (Invoke-WebRequest -Uri "http://127.0.0.1:8093/api/automation/status" -UseBasicParsing -TimeoutSec 20).Content | ConvertFrom-Json
  [PSCustomObject]@{
    ok = $status.ok
    database_ok = $status.database_ok
    latest_data_ts = $status.latest_data_ts
    latest_diagnosis_ts = $status.latest.diagnosis_ts
    source_lag_seconds = $status.latest.source_lag_seconds
    quality_status = $status.latest_quality.status
  } | Format-List
} catch {
  Write-Host ("8093 status failed: " + $_.Exception.Message)
}

Write-Section "8768_LOG_TAIL"
$logDir = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\logs"
foreach ($name in @("ws_8768.guard.log", "ws_8768.out.log", "ws_8768.err.log")) {
  $path = Join-Path $logDir $name
  Write-Host ("--- {0} ---" -f $name)
  if (Test-Path -LiteralPath $path) {
    Get-Item -LiteralPath $path | Select-Object FullName,Length,LastWriteTime | Format-List
    Get-Content -LiteralPath $path -Tail 12 -ErrorAction SilentlyContinue
  } else {
    Write-Host "MISSING"
  }
}
