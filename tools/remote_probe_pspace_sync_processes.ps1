$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$ErrorActionPreference = 'Stop'

$projectRoot = 'F:\高炉炼铁项目-real-sensor-v2_V3'
$roots = @(
    Join-Path $projectRoot '数据库同步和存取'
    Join-Path $projectRoot 'db_sync_storage'
)

Write-Host '===== PROCESS_TREE ====='
$allProcesses = Get-CimInstance Win32_Process
$syncProcesses = @($allProcesses | Where-Object {
    $_.CommandLine -and (
        $_.CommandLine -match 'run_realtime_sync_pg_bg\.ps1' -or
        $_.CommandLine -match 'sync_from_243_pg\.py'
    )
})
$rows = foreach ($process in $syncProcesses) {
    $parent = $allProcesses | Where-Object { $_.ProcessId -eq $process.ParentProcessId } | Select-Object -First 1
    [PSCustomObject]@{
        ProcessId = $process.ProcessId
        ParentProcessId = $process.ParentProcessId
        CreationDate = $process.CreationDate
        Name = $process.Name
        CommandLine = $process.CommandLine
        ParentName = $parent.Name
        ParentCommandLine = $parent.CommandLine
    }
}
$rows | ConvertTo-Json -Depth 4

Write-Host '===== FILE_HASHES ====='
$relativeFiles = @(
    'config\sync_config.json',
    'schema\postgresql_required_points.sql',
    'src\sync_from_243_pg.py',
    'src\pg_store.py',
    'run_realtime_sync_pg_bg.ps1',
    'run_22012_continuous_sync.ps1',
    'src\sync_watchdog.py'
)
$hashRows = foreach ($root in $roots) {
    foreach ($relative in $relativeFiles) {
        $path = Join-Path $root $relative
        [PSCustomObject]@{
            Root = $root
            RelativePath = $relative
            Exists = Test-Path -LiteralPath $path
            Sha256 = if (Test-Path -LiteralPath $path) { (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash } else { $null }
        }
    }
}
$hashRows | ConvertTo-Json -Depth 4

Write-Host '===== RECENT_LOGS ====='
$logRows = foreach ($root in $roots) {
    $logDir = Join-Path $root 'logs'
    if (-not (Test-Path -LiteralPath $logDir)) {
        continue
    }
    Get-ChildItem -LiteralPath $logDir -Filter 'continuous_sync_pg_*.log' -File |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 3 |
        ForEach-Object {
            [PSCustomObject]@{
                Root = $root
                Name = $_.Name
                LastWriteTime = $_.LastWriteTime
                Length = $_.Length
                Tail = @(Get-Content -LiteralPath $_.FullName -Encoding UTF8 -Tail 8)
            }
        }
}
$logRows | ConvertTo-Json -Depth 5
