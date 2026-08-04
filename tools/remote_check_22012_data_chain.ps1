$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$ErrorActionPreference = "Continue"

function Write-Section {
  param([string]$Name)
  Write-Host ""
  Write-Host ("===== {0} =====" -f $Name)
}

function Get-HttpSummary {
  param([string]$Name, [string]$Url)
  Write-Host ("--- {0} ---" -f $Name)
  try {
    $content = (Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 15).Content
    if ($Name -eq "8093_automation") {
      $data = $content | ConvertFrom-Json
      [PSCustomObject]@{
        ok = $data.ok
        database_ok = $data.database_ok
        latest_data_ts = $data.latest_data_ts
        latest_diagnosis_ts = $data.latest.diagnosis_ts
        source_lag_seconds = $data.latest.source_lag_seconds
        quality_status = $data.latest_quality.status
      } | Format-List
    } elseif ($Name -eq "8092_ollama") {
      $data = $content | ConvertFrom-Json
      [PSCustomObject]@{
        ok = $data.ok
        proxy_ok = $data.proxy_ok
        model_ok = $data.model_ok
        model_name = $data.model_name
        error = $data.error
      } | Format-List
    } elseif ($Name -eq "8777_chronos") {
      $data = $content | ConvertFrom-Json
      [PSCustomObject]@{
        ok = $data.ok
        service = $data.service
        engine = $data.engine
        errors = ($data.errors -join "; ")
      } | Format-List
    } else {
      [PSCustomObject]@{ ok = $true; bytes = $content.Length } | Format-List
    }
  } catch {
    [PSCustomObject]@{ ok = $false; error = $_.Exception.Message } | Format-List
  }
}

Write-Section "NOW"
[PSCustomObject]@{
  now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  computer = $env:COMPUTERNAME
  user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
  last_boot = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime
} | Format-List

Write-Section "PORTS"
$ports = @(5432,8092,8093,8767,8768,8777,11434)
$listeners = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
  Where-Object { $ports -contains $_.LocalPort } |
  Select-Object LocalAddress,LocalPort,OwningProcess
$listeners | Sort-Object LocalPort | Format-Table -AutoSize

Write-Section "PORT_OWNERS"
$pids = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
if ($pids.Count -gt 0) {
  Get-CimInstance Win32_Process |
    Where-Object { $pids -contains $_.ProcessId } |
    Select-Object ProcessId,Name,CreationDate,CommandLine |
    Sort-Object ProcessId |
    Format-List
}

Write-Section "TASKS"
foreach ($spec in @(
  @{ Path = "\BlastFurnaceServices\"; Name = "V4PreviewWs8768" },
  @{ Path = "\BlastFurnaceServices\"; Name = "V4PreviewProxy8093" },
  @{ Path = "\GL02SensorSync\"; Name = "Watchdog" },
  @{ Path = "\GL02AutoDiagnosis\"; Name = "RunOnce" },
  @{ Path = "\BlastFurnaceServices\"; Name = "BaselineProxy8092" },
  @{ Path = "\"; Name = "BlastFurnaceV3Pspace8767" }
)) {
  $task = Get-ScheduledTask -TaskPath $spec.Path -TaskName $spec.Name -ErrorAction SilentlyContinue
  if (-not $task) {
    [PSCustomObject]@{ Task = $spec.Path + $spec.Name; Exists = $false } | Format-List
    continue
  }
  $info = $task | Get-ScheduledTaskInfo
  [PSCustomObject]@{
    Task = $spec.Path + $spec.Name
    Exists = $true
    State = $task.State
    Enabled = $task.Settings.Enabled
    LastRunTime = $info.LastRunTime
    LastTaskResult = $info.LastTaskResult
    NextRunTime = $info.NextRunTime
  } | Format-List
}

Write-Section "HTTP"
Get-HttpSummary -Name "8093_automation" -Url "http://127.0.0.1:8093/api/automation/status"
Get-HttpSummary -Name "8092_ollama" -Url "http://127.0.0.1:8092/api/ollama/status"
Get-HttpSummary -Name "8777_chronos" -Url "http://127.0.0.1:8777/api/chronos/status"
Get-HttpSummary -Name "11434_ollama" -Url "http://127.0.0.1:11434/api/tags"

Write-Section "POSTGRES_FRESHNESS"
$psql = "F:\PostgreSQL\16\bin\psql.exe"
if (-not (Test-Path -LiteralPath $psql)) {
  Write-Host "PSQL_NOT_FOUND"
} else {
  $env:PGPASSWORD = [Environment]::GetEnvironmentVariable("GL02_PGPASSWORD", "Machine")
  if (-not $env:PGPASSWORD) { $env:PGPASSWORD = [Environment]::GetEnvironmentVariable("GL02_PGPASSWORD", "User") }
  if (-not $env:PGPASSWORD) { $env:PGPASSWORD = $env:GL02_PGPASSWORD }
  $pgUser = [Environment]::GetEnvironmentVariable("GL02_PGUSER", "Machine")
  if (-not $pgUser) { $pgUser = [Environment]::GetEnvironmentVariable("GL02_PGUSER", "User") }
  if (-not $pgUser) { $pgUser = $env:GL02_PGUSER }
  if (-not $pgUser) { $pgUser = "gl02_sync" }
  $sql = "SELECT max(ts) AS max_ts, localtimestamp AS db_now, round(extract(epoch from (localtimestamp - max(ts)))::numeric/60, 3) AS lag_min, count(DISTINCT tag_long_name) FILTER (WHERE ts >= (SELECT max(ts)-interval '10 minutes' FROM bf_sensor.one_minute_values)) AS tags_latest_10m FROM bf_sensor.one_minute_values;"
  & $psql -h 127.0.0.1 -p 5432 -U $pgUser -d bf_trend -v ON_ERROR_STOP=0 -c $sql
}
