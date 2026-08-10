$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$standalone = Join-Path $root 'standalone_heat_dashboard_8891'
$taskPath = '\BlastFurnaceServices\'
$taskName = 'HeatPerformanceQualitySync'

function Get-ListenerPid([int]$Port) {
    $line = @(netstat.exe -ano | Where-Object {
        $_ -match ":$Port\s" -and $_ -match 'LISTENING\s+(\d+)\s*$'
    })[0]
    if (-not $line) { return $null }
    [void]($line -match 'LISTENING\s+(\d+)\s*$')
    return [int]$matches[1]
}

$paths = [ordered]@{
    root_store = Join-Path $root '高炉前端数据\智能助手\backend\heat_performance_quality.py'
    standalone_store = Join-Path $standalone '高炉前端数据\智能助手\backend\heat_performance_quality.py'
    standalone_sync = Join-Path $standalone 'tools\sync_22012_heat_performance_quality.py'
    scheduled_runner = Join-Path $standalone 'tools\run_22012_heat_performance_sync.ps1'
}
$hashes = [ordered]@{}
foreach ($entry in $paths.GetEnumerator()) {
    $hashes[$entry.Key] = (Get-FileHash -LiteralPath $entry.Value -Algorithm SHA256).Hash
}
$task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName
$taskInfo = Get-ScheduledTaskInfo -TaskPath $taskPath -TaskName $taskName
if ($taskInfo.LastTaskResult -ne 0) { throw 'Scheduled sync last result is not zero' }

$heat089 = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/heat-performance-quality?meltno=2%2320260806-089&limit=5&include_future=1' -TimeoutSec 30
$heat090 = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/heat-performance-quality?meltno=2%2320260806-090&limit=5&include_future=1' -TimeoutSec 30
if (-not $heat089.ok -or @($heat089.items).Count -ne 1) { throw 'Exact heat 089 lookup failed' }
if (-not $heat090.ok -or @($heat090.items).Count -ne 1) { throw 'Exact heat 090 lookup failed' }
$row089 = @($heat089.items)[0]
$row090 = @($heat090.items)[0]

[ordered]@{
    schema = 'ops.8093.heat-quality-closed-loop.final-audit.v2'
    audited_at = (Get-Date).ToString('o')
    services = [ordered]@{
        BFV4PreviewProxy8093 = (Get-Service -Name 'BFV4PreviewProxy8093').Status.ToString()
        BFV4PreviewWs8768 = (Get-Service -Name 'BFV4PreviewWs8768').Status.ToString()
    }
    listeners = [ordered]@{
        port_8093 = Get-ListenerPid 8093
        port_8768 = Get-ListenerPid 8768
        port_8094 = Get-ListenerPid 8094
        port_8770 = Get-ListenerPid 8770
    }
    guard_task_state = (Get-ScheduledTask -TaskPath $taskPath -TaskName 'BFV4PreviewProxy8093HealthCheck').State.ToString()
    scheduled_sync = [ordered]@{
        state = $task.State.ToString()
        last_run_time = $taskInfo.LastRunTime.ToString('o')
        last_task_result = $taskInfo.LastTaskResult
        next_run_time = $taskInfo.NextRunTime.ToString('o')
    }
    hashes = $hashes
    heat_089 = [ordered]@{
        meltno = $row089.meltno
        work_date = $row089.work_date
        open_ts = $row089.open_ts
        close_ts = $row089.close_ts
        raw_open_ts = $row089.raw_open_ts
        raw_close_ts = $row089.raw_close_ts
        repaired_open_ts = $row089.repaired_open_ts
        repaired_close_ts = $row089.repaired_close_ts
        source_status = $row089.source_status
        reasons = $row089.time_anomaly_reasons
        future_pending = $row089.future_pending
        si_avg = $row089.si_avg
    }
    heat_090 = [ordered]@{
        meltno = $row090.meltno
        work_date = $row090.work_date
        open_ts = $row090.open_ts
        close_ts = $row090.close_ts
        raw_open_ts = $row090.raw_open_ts
        raw_close_ts = $row090.raw_close_ts
        repaired_open_ts = $row090.repaired_open_ts
        repaired_close_ts = $row090.repaired_close_ts
        source_status = $row090.source_status
        reasons = $row090.time_anomaly_reasons
        future_pending = $row090.future_pending
        si_avg = $row090.si_avg
    }
} | ConvertTo-Json -Depth 8
