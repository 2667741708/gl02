$ErrorActionPreference = 'Stop'
$ProjectRoot = 'F:\高炉炼铁项目-real-sensor-v2_V3'
$Port = 8778
$ChronosUrl = 'http://127.0.0.1:8777'
$taskPath = '\BlastFurnaceServices\'
$taskName = 'TimeSeriesBenchmark8778'
$serviceScript = Join-Path $ProjectRoot 'tools\timeseries_sidecar_service.py'
$modelDir = Join-Path $ProjectRoot 'PT\时间序列预测评测\models'
$logFile = Join-Path $ProjectRoot 'logs\timeseries_sidecar_8778.log'

if (-not (Test-Path -LiteralPath $serviceScript)) {
  throw "Sidecar service script is missing: $serviceScript"
}

$chronosBefore = @(Get-NetTCPConnection -LocalPort 8777 -State Listen -ErrorAction SilentlyContinue)
if ($chronosBefore.Count -ne 1) {
  throw 'Protected Chronos port 8777 is not listening exactly once.'
}
$chronosPid = $chronosBefore[0].OwningProcess

$pythonCandidates = @(
  'C:\Python311\python.exe',
  'C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe'
)
$python = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $python) {
  $python = (Get-Command python.exe -ErrorAction Stop).Source
}

New-Item -ItemType Directory -Path $modelDir -Force | Out-Null
New-Item -ItemType Directory -Path (Split-Path -Parent $logFile) -Force | Out-Null

$existing = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
foreach ($listener in $existing) {
  $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
  if (-not $process.CommandLine.Contains('timeseries_sidecar_service.py')) {
    throw "Port $Port belongs to an unrelated process: $($listener.OwningProcess)"
  }
  Stop-Process -Id $listener.OwningProcess -Force
}

$oldTask = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
if ($oldTask) {
  Stop-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
}

$arguments = '"{0}" --host 0.0.0.0 --port {1} --chronos-url "{2}" --default-model last_value --model-dir "{3}" --log-file "{4}"' -f $serviceScript, $Port, $ChronosUrl, $modelDir, $logFile
$action = New-ScheduledTaskAction -Execute $python -Argument $arguments -WorkingDirectory $ProjectRoot
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 365)
Register-ScheduledTask -TaskPath $taskPath -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskPath $taskPath -TaskName $taskName

$deadline = (Get-Date).AddSeconds(60)
do {
  Start-Sleep -Milliseconds 500
  $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
} while (-not $listener -and (Get-Date) -lt $deadline)
if (-not $listener) {
  throw "Sidecar port $Port did not start."
}

$status = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/timeseries/status" -TimeoutSec 8
if (-not $status.ok) {
  throw 'Sidecar status did not report ok.'
}
$chronosAfter = @(Get-NetTCPConnection -LocalPort 8777 -State Listen -ErrorAction SilentlyContinue)
if ($chronosAfter.Count -ne 1 -or $chronosAfter[0].OwningProcess -ne $chronosPid) {
  throw 'Protected Chronos port 8777 changed while starting sidecar.'
}

[pscustomobject]@{
  sidecar_port = $Port
  sidecar_pid = $listener.OwningProcess
  sidecar_ok = $status.ok
  trained_model_count = $status.trained_model_count
  chronos_8777_pid_unchanged = $true
  task = "$taskPath$taskName"
} | ConvertTo-Json -Depth 5
