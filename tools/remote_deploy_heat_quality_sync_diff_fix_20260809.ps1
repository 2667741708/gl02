$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$standalone = Join-Path $root 'standalone_heat_dashboard_8891'
$target = Join-Path $standalone 'tools\sync_22012_heat_performance_quality.py'
$stage = 'C:\Users\Administrator\AppData\Local\Temp\sync_22012_heat_performance_quality.diff_fix.py'
$expectedHash = '30D8A8E8FB8508EFF6787DD76CB4AC005984412564FCC6EF44F9F4727489CABE'
$python = 'C:\Program Files\Python311\python.exe'
$taskPath = '\BlastFurnaceServices\'
$taskName = 'HeatPerformanceQualitySync'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupRoot = Join-Path $root "logs\deploy_backups\heat_quality_sync_diff_fix_$stamp"
$backup = Join-Path $backupRoot 'sync_22012_heat_performance_quality.py.bak'

function Get-ListenerPid([int]$Port) {
    $line = @(netstat.exe -ano | Where-Object {
        $_ -match ":$Port\s" -and $_ -match 'LISTENING\s+(\d+)\s*$'
    })[0]
    if (-not $line) { return $null }
    [void]($line -match 'LISTENING\s+(\d+)\s*$')
    return [int]$matches[1]
}

if ((Get-FileHash -LiteralPath $stage -Algorithm SHA256).Hash -ne $expectedHash) {
    throw 'Staged sync hash mismatch'
}
& $python -m py_compile $stage
if ($LASTEXITCODE -ne 0) { throw 'Staged sync compile failed' }
$pidsBefore = @{}
foreach ($port in @(8093, 8768, 8094, 8770)) {
    $pidsBefore[$port] = Get-ListenerPid $port
    if (-not $pidsBefore[$port]) { throw "Port $port is not listening" }
}
$task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName
$wasEnabled = $task.State.ToString() -ne 'Disabled'
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
Copy-Item -LiteralPath $target -Destination $backup -Force
try {
    Disable-ScheduledTask -TaskPath $taskPath -TaskName $taskName | Out-Null
    Stop-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
    $temporary = "$target.deploy_$stamp"
    Copy-Item -LiteralPath $stage -Destination $temporary -Force
    Move-Item -LiteralPath $temporary -Destination $target -Force
    & $python -m py_compile $target
    if ($LASTEXITCODE -ne 0) { throw 'Deployed sync compile failed' }
    if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $expectedHash) {
        throw 'Deployed sync hash mismatch'
    }
} catch {
    Copy-Item -LiteralPath $backup -Destination $target -Force
    throw
} finally {
    if ($wasEnabled) {
        Enable-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue | Out-Null
    }
}
foreach ($port in @(8093, 8768, 8094, 8770)) {
    if ((Get-ListenerPid $port) -ne $pidsBefore[$port]) { throw "PID changed on port $port" }
}

[ordered]@{
    deployed = $true
    backup_root = $backupRoot
    sync_hash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
    task_state = (Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName).State.ToString()
    pids = [ordered]@{
        port_8093 = $pidsBefore[8093]
        port_8768 = $pidsBefore[8768]
        port_8094 = $pidsBefore[8094]
        port_8770 = $pidsBefore[8770]
    }
} | ConvertTo-Json -Depth 5
