$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$OutputEncoding = [Text.UTF8Encoding]::new($false)

$projectRoot = 'F:\高炉炼铁项目-real-sensor-v2_V3'
$mainRoot = Join-Path $projectRoot '数据库同步和存取'
$mirrorRoot = Join-Path $projectRoot 'db_sync_storage'

function Get-ListenerPid([int]$Port) {
    $row = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($row) { return [int]$row.OwningProcess }
    return 0
}

$processes = @(Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -and (
        $_.CommandLine -match 'foreman_points_coal|run_realtime_sync_pg_bg\.ps1|sync_from_243_pg\.py|run_sync_watchdog\.ps1|sync_watchdog\.py'
    )
} | Select-Object ProcessId, ParentProcessId, Name, CreationDate, CommandLine)

$files = foreach ($root in @($mainRoot, $mirrorRoot)) {
    foreach ($relative in 'config\点位清单.tsv', 'schema\postgresql_required_points.sql', 'src\sync_from_243_pg.py', 'src\coal_hourly.py') {
        $path = Join-Path $root $relative
        $text = if (Test-Path -LiteralPath $path) { Get-Content -LiteralPath $path -Raw -Encoding UTF8 } else { '' }
        [ordered]@{
            root = $root
            relative = $relative
            exists = Test-Path -LiteralPath $path
            sha256 = if (Test-Path -LiteralPath $path) { (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash } else { $null }
            point_marker = $text.Contains('SIO_GL02_PC_T0004')
            schema_marker = $text.Contains('bf_sensor.coal_injection_hourly')
            sync_marker = $text.Contains('FOREMAN-COAL-HOURLY-20260806-BEGIN')
        }
    }
}

[ordered]@{
    tasks = [ordered]@{
        continuous = [string](Get-ScheduledTask -TaskPath '\' -TaskName 'BlastFurnaceV3PgContinuousSync30s').State
        watchdog = [string](Get-ScheduledTask -TaskPath '\GL02SensorSync\' -TaskName 'Watchdog').State
        legacy = [string](Get-ScheduledTask -TaskPath '\GL02SensorSync\' -TaskName 'Realtime').State
    }
    listeners = [ordered]@{
        8093 = Get-ListenerPid 8093
        8094 = Get-ListenerPid 8094
        8768 = Get-ListenerPid 8768
        8770 = Get-ListenerPid 8770
    }
    processes = $processes
    files = $files
} | ConvertTo-Json -Depth 6
