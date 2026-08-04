$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$ErrorActionPreference = "Continue"

function Write-Section {
  param([string]$Name)
  Write-Host ""
  Write-Host ("===== {0} =====" -f $Name)
}

function Invoke-HttpJson {
  param(
    [string]$Name,
    [string]$Url,
    [int]$TimeoutSec = 8
  )
  Write-Host ("--- {0} {1} ---" -f $Name, $Url)
  try {
    $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec
    $content = $response.Content
    if ($content.Length -gt 1200) {
      $content = $content.Substring(0, 1200) + "...<truncated>"
    }
    [PSCustomObject]@{
      ok = $true
      status_code = [int]$response.StatusCode
      bytes = $response.RawContentLength
      sample = $content
    } | ConvertTo-Json -Depth 4
  } catch {
    [PSCustomObject]@{
      ok = $false
      error = $_.Exception.Message
    } | ConvertTo-Json -Depth 4
  }
}

Write-Section "NOW_BOOT"
$os = Get-CimInstance Win32_OperatingSystem
[PSCustomObject]@{
  now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  computer = $env:COMPUTERNAME
  user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
  last_boot = $os.LastBootUpTime
} | Format-List

Write-Section "SCHEDULED_TASKS"
$taskSpecs = @(
  @{ Path = "\BlastFurnaceServices\"; Name = "V4PreviewProxy8093" },
  @{ Path = "\BlastFurnaceServices\"; Name = "V4PreviewWs8768" },
  @{ Path = "\BlastFurnaceServices\"; Name = "BaselineProxy8092" },
  @{ Path = "\"; Name = "BlastFurnaceV3Proxy8092" },
  @{ Path = "\"; Name = "BlastFurnaceV3Pspace8767" },
  @{ Path = "\"; Name = "BlastFurnaceV3Pspace8768" },
  @{ Path = "\GL02SensorSync\"; Name = "Watchdog" },
  @{ Path = "\GL02AutoDiagnosis\"; Name = "RunOnce" }
)
foreach ($spec in $taskSpecs) {
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
    Action = (($task.Actions | ForEach-Object { ($_.Execute + " " + $_.Arguments).Trim() }) -join " || ")
  } | Format-List
}

Write-Section "PORTS_AND_PROCESSES"
$ports = @(5432, 8092, 8093, 8767, 8768, 8777, 11434)
$listeners = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
  Where-Object { $ports -contains $_.LocalPort } |
  Select-Object LocalAddress,LocalPort,OwningProcess
$listeners | Sort-Object LocalPort | Format-Table -AutoSize
$listenerPids = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
if ($listenerPids.Count -gt 0) {
  Get-CimInstance Win32_Process |
    Where-Object { $listenerPids -contains $_.ProcessId } |
    Select-Object ProcessId,Name,CreationDate,CommandLine |
    Sort-Object ProcessId |
    Format-List
}

Write-Section "HTTP_HEALTH"
Invoke-HttpJson -Name "8092_ollama_status" -Url "http://127.0.0.1:8092/api/ollama/status"
Invoke-HttpJson -Name "8093_automation_status" -Url "http://127.0.0.1:8093/api/automation/status"
Invoke-HttpJson -Name "8777_chronos_status" -Url "http://127.0.0.1:8777/api/chronos/status"
Invoke-HttpJson -Name "11434_ollama_tags" -Url "http://127.0.0.1:11434/api/tags"

Write-Section "LOAD"
try {
  $samples = Get-Counter '\Processor(_Total)\% Processor Time' -SampleInterval 1 -MaxSamples 3
  $cpuAvg = ($samples.CounterSamples | Measure-Object -Property CookedValue -Average).Average
} catch {
  $cpuAvg = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
}
$os = Get-CimInstance Win32_OperatingSystem
$totalMemGb = [math]::Round($os.TotalVisibleMemorySize / 1MB, 2)
$freeMemGb = [math]::Round($os.FreePhysicalMemory / 1MB, 2)
$usedMemPct = if ($totalMemGb -gt 0) { [math]::Round((($totalMemGb - $freeMemGb) / $totalMemGb) * 100, 1) } else { $null }
[PSCustomObject]@{
  cpu_percent_avg_3s = [math]::Round([double]$cpuAvg, 1)
  memory_total_gb = $totalMemGb
  memory_free_gb = $freeMemGb
  memory_used_percent = $usedMemPct
} | Format-List

Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" |
  Where-Object { $_.DeviceID -in @("C:", "D:", "F:") } |
  Select-Object DeviceID,
    @{Name="SizeGB";Expression={[math]::Round($_.Size / 1GB, 1)}},
    @{Name="FreeGB";Expression={[math]::Round($_.FreeSpace / 1GB, 1)}},
    @{Name="FreePercent";Expression={if ($_.Size) { [math]::Round($_.FreeSpace * 100 / $_.Size, 1) } else { $null }}} |
  Format-Table -AutoSize

Write-Section "TOP_PROCESSES"
Get-Process |
  Sort-Object WorkingSet64 -Descending |
  Select-Object -First 12 Id,ProcessName,
    @{Name="WorkingSetMB";Expression={[math]::Round($_.WorkingSet64 / 1MB, 1)}},
    @{Name="CPUSeconds";Expression={if ($_.CPU) { [math]::Round($_.CPU, 1) } else { 0 }}} |
  Format-Table -AutoSize

Write-Section "POSTGRES_SIZE_AND_FRESHNESS"
$psql = $null
foreach ($candidate in @(
  "psql",
  "C:\Program Files\PostgreSQL\16\bin\psql.exe",
  "C:\Program Files\PostgreSQL\15\bin\psql.exe",
  "C:\Program Files\PostgreSQL\14\bin\psql.exe"
)) {
  $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
  if ($cmd) {
    $psql = $cmd.Source
    break
  }
}
if (-not $psql) {
  Write-Host "PSQL_NOT_FOUND"
} else {
  Write-Host ("psql={0}" -f $psql)
  $env:PGPASSWORD = [Environment]::GetEnvironmentVariable("GL02_PGPASSWORD", "Machine")
  if (-not $env:PGPASSWORD) { $env:PGPASSWORD = [Environment]::GetEnvironmentVariable("GL02_PGPASSWORD", "User") }
  if (-not $env:PGPASSWORD) { $env:PGPASSWORD = $env:GL02_PGPASSWORD }
  $pgUser = [Environment]::GetEnvironmentVariable("GL02_PGUSER", "Machine")
  if (-not $pgUser) { $pgUser = [Environment]::GetEnvironmentVariable("GL02_PGUSER", "User") }
  if (-not $pgUser) { $pgUser = $env:GL02_PGUSER }
  if (-not $pgUser) { $pgUser = "gl02_sync" }

  $sql = @"
\pset pager off
SELECT current_database() AS database, pg_size_pretty(pg_database_size(current_database())) AS database_size;
SELECT max(ts) AS one_minute_max_ts,
       localtimestamp AS db_now,
       round(extract(epoch from (localtimestamp - max(ts)))::numeric / 60, 3) AS lag_min,
       count(DISTINCT tag_long_name) FILTER (WHERE ts >= (SELECT max(ts)-interval '10 minutes' FROM bf_sensor.one_minute_values)) AS tags_latest_10m
FROM bf_sensor.one_minute_values;
WITH rels AS (
  SELECT *
  FROM (VALUES
    ('bf_sensor.one_minute_values'::regclass),
    ('bf_sensor.raw_5s_values'::regclass),
    ('bf_sensor.daily_baselines'::regclass),
    ('bf_sensor.diagnosis_snapshots'::regclass),
    ('bf_sensor.data_quality_checks'::regclass),
    ('bf_sensor.automation_runs'::regclass),
    ('bf_sensor.diagnosis_queue'::regclass),
    ('bf_sensor.short_window_summaries'::regclass),
    ('bf_sensor.zero_value_audits'::regclass)
  ) AS v(rel)
)
SELECT rel::text AS table_name,
       pg_size_pretty(pg_total_relation_size(rel)) AS total_size,
       COALESCE((xpath('/row/c/text()', query_to_xml(format('SELECT count(*) AS c FROM %s', rel), false, true, '')))[1]::text::bigint, 0) AS estimated_rows
FROM rels
ORDER BY pg_total_relation_size(rel) DESC;
"@
  $tmp = Join-Path $env:TEMP ("bf_runtime_db_{0}.sql" -f ([guid]::NewGuid().ToString("N")))
  Set-Content -LiteralPath $tmp -Value $sql -Encoding UTF8
  & $psql -h 127.0.0.1 -p 5432 -U $pgUser -d bf_trend -v ON_ERROR_STOP=0 -f $tmp
  Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
}
