$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$ErrorActionPreference = 'Stop'

function Get-MachineOrUserEnvironmentValue {
    param([Parameter(Mandatory = $true)][string]$Name)
    $value = [Environment]::GetEnvironmentVariable($Name, 'Machine')
    if (-not $value) {
        $value = [Environment]::GetEnvironmentVariable($Name, 'User')
    }
    if (-not $value) {
        $value = [Environment]::GetEnvironmentVariable($Name, 'Process')
    }
    return $value
}

function Get-TaskSnapshot {
    param(
        [Parameter(Mandatory = $true)][string]$TaskPath,
        [Parameter(Mandatory = $true)][string]$TaskName
    )
    $task = Get-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $task) {
        return [PSCustomObject]@{ Path = $TaskPath; Name = $TaskName; Exists = $false }
    }
    $info = Get-ScheduledTaskInfo -TaskPath $TaskPath -TaskName $TaskName
    return [PSCustomObject]@{
        Path = $TaskPath
        Name = $TaskName
        Exists = $true
        State = $task.State.ToString()
        Enabled = [bool]$task.Settings.Enabled
        LastRunTime = $info.LastRunTime
        LastTaskResult = $info.LastTaskResult
        Actions = @($task.Actions | ForEach-Object { "{0} {1}" -f $_.Execute, $_.Arguments })
    }
}

$projectRoot = 'F:\高炉炼铁项目-real-sensor-v2_V3'
$syncRoot = Join-Path $projectRoot '数据库同步和存取'
$mirrorRoot = Join-Path $projectRoot 'db_sync_storage'
$configPath = Join-Path $syncRoot 'config\sync_config.json'

$psqlCandidates = @(
    'F:\PostgreSQL\16\bin\psql.exe',
    'C:\Program Files\PostgreSQL\16\bin\psql.exe',
    'F:\PostgreSQL\15\bin\psql.exe',
    'C:\Program Files\PostgreSQL\15\bin\psql.exe'
)
$psql = $psqlCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $psql) {
    throw 'PostgreSQL psql executable was not found.'
}

$env:PGPASSWORD = Get-MachineOrUserEnvironmentValue -Name 'GL02_PGPASSWORD'
$pgUser = Get-MachineOrUserEnvironmentValue -Name 'GL02_PGUSER'
if (-not $pgUser) {
    $pgUser = 'gl02_sync'
}

$sql = @'
\pset pager off
SELECT current_database() AS database,
       pg_size_pretty(pg_database_size(current_database())) AS database_size,
       localtimestamp AS db_now;
SELECT aggregate,
       interval_seconds,
       min(ts) AS min_ts,
       max(ts) AS max_ts,
       count(*) AS rows
FROM bf_sensor.one_minute_values
GROUP BY aggregate, interval_seconds
ORDER BY min_ts;
SELECT aggregate,
       count(*) AS rows_24h,
       min(ts) AS min_ts_24h,
       max(ts) AS max_ts_24h
FROM bf_sensor.one_minute_values
WHERE ts >= localtimestamp - interval '24 hours'
GROUP BY aggregate
ORDER BY aggregate;
SELECT max(ts) AS max_ts,
       round(extract(epoch FROM (localtimestamp - max(ts)))::numeric / 60, 3) AS lag_min,
       count(DISTINCT tag_long_name) FILTER (
           WHERE ts >= (SELECT max(ts) - interval '10 minutes' FROM bf_sensor.one_minute_values)
       ) AS tags_latest_10m
FROM bf_sensor.one_minute_values;
SELECT min(ts) AS raw_min_ts,
       max(ts) AS raw_max_ts,
       count(*) AS raw_rows,
       count(DISTINCT tag_long_name) AS raw_tags,
       pg_size_pretty(pg_total_relation_size('bf_sensor.raw_5s_values')) AS raw_size
FROM bf_sensor.raw_5s_values;
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'bf_sensor'
  AND table_name = 'one_minute_values'
ORDER BY ordinal_position;
SELECT id, started_at, finished_at, sync_mode, start_ts, end_ts,
       rows_written, tags_ok, tags_error, left(error, 200) AS error
FROM bf_sensor.sync_runs
ORDER BY id DESC
LIMIT 8;
'@

$sqlPath = Join-Path $env:TEMP ("pspace_minute_audit_{0}.sql" -f [guid]::NewGuid().ToString('N'))
try {
    Set-Content -LiteralPath $sqlPath -Value $sql -Encoding UTF8

    Write-Host '===== PATHS ====='
    [PSCustomObject]@{
        ProjectRoot = $projectRoot
        SyncRootExists = Test-Path -LiteralPath $syncRoot
        MirrorRootExists = Test-Path -LiteralPath $mirrorRoot
        ConfigExists = Test-Path -LiteralPath $configPath
    } | Format-List

    Write-Host '===== DISK ====='
    Get-PSDrive -Name C, F -ErrorAction SilentlyContinue |
        Select-Object Name, Used, Free, @{Name = 'FreeGB'; Expression = { [math]::Round($_.Free / 1GB, 2) }} |
        Format-Table -AutoSize

    Write-Host '===== CONFIG ====='
    if (Test-Path -LiteralPath $configPath) {
        $config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
        [PSCustomObject]@{
            SourceMode = $config.source.source_mode
            SourceIntervalSeconds = $config.source.source_interval_seconds
            SourceAggregate = $config.source.source_aggregate
            TargetAggregate = $config.source.target_aggregate
            TargetIntervalSeconds = $config.source.target_interval_seconds
            ContinuousPollSeconds = $config.sync.continuous_poll_seconds
            LookbackMinutes = $config.sync.continuous_lookback_minutes
            RetentionYears = $config.sync.retention_years
        } | Format-List
    }

    Write-Host '===== TASKS ====='
    @(
        Get-TaskSnapshot -TaskPath '\' -TaskName 'BlastFurnaceV3PgContinuousSync30s'
        Get-TaskSnapshot -TaskPath '\GL02SensorSync\' -TaskName 'Watchdog'
        Get-TaskSnapshot -TaskPath '\GL02SensorSync\' -TaskName 'Realtime'
    ) | ConvertTo-Json -Depth 5

    Write-Host '===== SYNC_PROCESSES ====='
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.CommandLine -and (
                $_.CommandLine -match 'run_realtime_sync_pg_bg\.ps1' -or
                $_.CommandLine -match 'sync_from_243_pg\.py' -or
                $_.CommandLine -match 'sync_raw_5s_from_243_pg\.py'
            )
        } |
        Select-Object ProcessId, ParentProcessId, Name, CommandLine |
        ConvertTo-Json -Depth 4

    Write-Host '===== PROTECTED_PORTS ====='
    Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -in 8093, 8094, 8768, 8770 } |
        Select-Object LocalPort, OwningProcess |
        Sort-Object LocalPort |
        Format-Table -AutoSize

    Write-Host '===== SOURCE_CONNECTIVITY ====='
    $tcp = Test-NetConnection -ComputerName 10.22.181.243 -Port 8889 -WarningAction SilentlyContinue
    [PSCustomObject]@{ Remote = '10.22.181.243:8889'; TcpTestSucceeded = $tcp.TcpTestSucceeded } | Format-List

    Write-Host '===== DATABASE ====='
    & $psql -h 127.0.0.1 -p 5432 -U $pgUser -d bf_trend -v ON_ERROR_STOP=1 -f $sqlPath
    if ($LASTEXITCODE -ne 0) {
        throw "psql audit failed with exit code $LASTEXITCODE"
    }
}
finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $sqlPath -Force -ErrorAction SilentlyContinue
}
