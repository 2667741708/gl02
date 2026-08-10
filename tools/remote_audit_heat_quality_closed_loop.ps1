$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$standalone = Join-Path $root 'standalone_heat_dashboard_8891'
$psql = 'C:\Program Files\PostgreSQL\16\bin\psql.exe'
$taskPath = '\BlastFurnaceServices\'

function Get-ListenerPid([int]$Port) {
    $line = @(netstat.exe -ano | Where-Object {
        $_ -match ":$Port\s" -and $_ -match 'LISTENING\s+(\d+)\s*$'
    })[0]
    if (-not $line) { return $null }
    [void]($line -match 'LISTENING\s+(\d+)\s*$')
    return [int]$matches[1]
}

function Get-FileEvidence([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return [ordered]@{ path = $Path; exists = $false }
    }
    $markers = [ordered]@{}
    foreach ($marker in @(
        'heat-performance-quality.v2',
        'time_anomaly_reasons',
        'future_pending',
        'existing_mirror_lineage',
        'build_gap_audit',
        'include_future'
    )) {
        $markers[$marker] = [bool](Select-String -LiteralPath $Path -SimpleMatch $marker -Quiet)
    }
    return [ordered]@{
        path = $Path
        exists = $true
        length = (Get-Item -LiteralPath $Path).Length
        sha256 = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
        markers = $markers
    }
}

function Invoke-PgQuery([string]$Sql) {
    if (-not (Test-Path -LiteralPath $psql -PathType Leaf)) {
        return [ordered]@{ ok = $false; error = 'PSQL_NOT_FOUND' }
    }
    $env:PGHOST = [Environment]::GetEnvironmentVariable('GL02_PGHOST', 'Machine')
    $env:PGPORT = [Environment]::GetEnvironmentVariable('GL02_PGPORT', 'Machine')
    $env:PGDATABASE = [Environment]::GetEnvironmentVariable('GL02_PGDATABASE', 'Machine')
    $env:PGUSER = [Environment]::GetEnvironmentVariable('GL02_PGUSER', 'Machine')
    $env:PGPASSWORD = [Environment]::GetEnvironmentVariable('GL02_PGPASSWORD', 'Machine')
    $env:PGOPTIONS = '-c default_transaction_read_only=on -c statement_timeout=15000'
    $lines = @(& $psql -X -q -t -A -v ON_ERROR_STOP=1 -c $Sql 2>&1)
    $exitCode = $LASTEXITCODE
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    if ($exitCode -ne 0) {
        return [ordered]@{ ok = $false; error = 'PG_QUERY_FAILED'; detail = ($lines -join ' ') }
    }
    return [ordered]@{ ok = $true; rows = @($lines | Where-Object { $_ -ne '' }) }
}

$files = [ordered]@{
    root_store = Get-FileEvidence (Join-Path $root '高炉前端数据\智能助手\backend\heat_performance_quality.py')
    root_proxy = Get-FileEvidence (Join-Path $root '高炉前端数据\智能助手\backend\ollama_proxy_server.py')
    standalone_store = Get-FileEvidence (Join-Path $standalone '高炉前端数据\智能助手\backend\heat_performance_quality.py')
    standalone_sync = Get-FileEvidence (Join-Path $standalone 'tools\sync_22012_heat_performance_quality.py')
}

$api = try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8093/api/heat-performance-quality?limit=1' -TimeoutSec 10
    [ordered]@{ ok = $true; status = [int]$response.StatusCode; body = $response.Content }
} catch {
    [ordered]@{
        ok = $false
        message = $_.Exception.Message
        body = $_.ErrorDetails.Message
    }
}

$syncTask = Get-ScheduledTask -TaskPath $taskPath -TaskName 'HeatPerformanceQualitySync' -ErrorAction SilentlyContinue
$syncInfo = if ($syncTask) {
    $info = Get-ScheduledTaskInfo -TaskPath $taskPath -TaskName 'HeatPerformanceQualitySync'
    [ordered]@{
        state = $syncTask.State.ToString()
        action_execute = $syncTask.Actions[0].Execute
        action_arguments = $syncTask.Actions[0].Arguments
        last_run_time = $info.LastRunTime.ToString('o')
        last_task_result = $info.LastTaskResult
        next_run_time = $info.NextRunTime.ToString('o')
    }
} else { $null }

$columnSql = @"
SELECT column_name || ':' || data_type
FROM information_schema.columns
WHERE table_schema='bf_assistant'
  AND table_name='heat_performance_quality_summary'
  AND column_name IN (
    'raw_open_ts','raw_close_ts','repaired_open_ts','repaired_close_ts',
    'time_anomaly_reasons','repair_checked_at','future_pending'
  )
ORDER BY column_name
"@

$statusSql = @"
SELECT source_status || '|' || count(*)::text
FROM bf_assistant.heat_performance_quality_summary
GROUP BY source_status
ORDER BY source_status
"@

$latestSql = @"
SELECT meltno || '|' || COALESCE(work_date::text,'') || '|' ||
       COALESCE(open_ts::text,'') || '|' || COALESCE(close_ts::text,'') || '|' ||
       source_status || '|' || COALESCE(future_pending::text,'')
FROM bf_assistant.heat_performance_quality_summary
ORDER BY open_ts DESC NULLS LAST
LIMIT 5
"@

[ordered]@{
    schema = 'audit.heat-quality-closed-loop.v1'
    checked_at = (Get-Date).ToString('o')
    services = [ordered]@{
        BFV4PreviewProxy8093 = (Get-Service 'BFV4PreviewProxy8093').Status.ToString()
        BFV4PreviewWs8768 = (Get-Service 'BFV4PreviewWs8768').Status.ToString()
    }
    ports = [ordered]@{
        p8093 = Get-ListenerPid 8093
        p8768 = Get-ListenerPid 8768
        p8094 = Get-ListenerPid 8094
        p8770 = Get-ListenerPid 8770
        p8891 = Get-ListenerPid 8891
    }
    sync_task = $syncInfo
    files = $files
    api = $api
    database = [ordered]@{
        columns = Invoke-PgQuery $columnSql
        statuses = Invoke-PgQuery $statusSql
        latest = Invoke-PgQuery $latestSql
    }
} | ConvertTo-Json -Depth 10
