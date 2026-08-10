$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$standalone = Join-Path $root 'standalone_heat_dashboard_8891'
$target = Join-Path $standalone 'tools\run_22012_heat_performance_sync.ps1'
$stage = 'C:\Users\Administrator\AppData\Local\Temp\run_22012_heat_performance_sync.closed_loop.ps1'
$expectedHash = '42428FD1BC35294FAA1D8B24F0BCF563EC02E212DFE3AAA2E3E8C03776105EBC'
$taskPath = '\BlastFurnaceServices\'
$taskName = 'HeatPerformanceQualitySync'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupRoot = Join-Path $root "logs\deploy_backups\heat_quality_sync_runner_$stamp"
$backup = Join-Path $backupRoot 'run_22012_heat_performance_sync.ps1.bak'
$log = Join-Path $standalone 'logs\heat_performance_quality_sync.log'

function Get-ListenerPid([int]$Port) {
    $line = @(netstat.exe -ano | Where-Object {
        $_ -match ":$Port\s" -and $_ -match 'LISTENING\s+(\d+)\s*$'
    })[0]
    if (-not $line) { return $null }
    [void]($line -match 'LISTENING\s+(\d+)\s*$')
    return [int]$matches[1]
}

if (-not (Test-Path -LiteralPath $stage -PathType Leaf)) { throw 'Staged runner is missing' }
if ((Get-FileHash -LiteralPath $stage -Algorithm SHA256).Hash -ne $expectedHash) {
    throw 'Staged runner hash mismatch'
}
$tokens = $null
$parseErrors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile(
    $stage, [ref]$tokens, [ref]$parseErrors
)
if ($parseErrors.Count -gt 0) { throw 'Staged runner syntax validation failed' }

$pidsBefore = @{}
foreach ($port in @(8093, 8768, 8094, 8770)) {
    $pidsBefore[$port] = Get-ListenerPid $port
    if (-not $pidsBefore[$port]) { throw "Port $port is not listening" }
}
$task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName
$wasEnabled = $task.State.ToString() -ne 'Disabled'
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
Copy-Item -LiteralPath $target -Destination $backup -Force

$deployed = $false
try {
    Disable-ScheduledTask -TaskPath $taskPath -TaskName $taskName | Out-Null
    Stop-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
    $temporary = "$target.deploy_$stamp"
    Copy-Item -LiteralPath $stage -Destination $temporary -Force
    Move-Item -LiteralPath $temporary -Destination $target -Force
    $deployed = $true
    if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $expectedHash) {
        throw 'Deployed runner hash mismatch'
    }
    Enable-ScheduledTask -TaskPath $taskPath -TaskName $taskName | Out-Null
    $before = Get-ScheduledTaskInfo -TaskPath $taskPath -TaskName $taskName
    Start-ScheduledTask -TaskPath $taskPath -TaskName $taskName
    $deadline = [DateTime]::UtcNow.AddSeconds(90)
    do {
        Start-Sleep -Milliseconds 500
        $task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName
        $after = Get-ScheduledTaskInfo -TaskPath $taskPath -TaskName $taskName
        $newRunObserved = $after.LastRunTime -gt $before.LastRunTime
    } while ((-not $newRunObserved -or $task.State.ToString() -eq 'Running') -and [DateTime]::UtcNow -lt $deadline)
    if (-not $newRunObserved -or $task.State.ToString() -eq 'Running') {
        throw 'A new scheduled run did not complete in 90 seconds'
    }
    if ($after.LastTaskResult -ne 0) {
        throw "New scheduled runner returned $($after.LastTaskResult)"
    }
} catch {
    $deployError = $_
    if ($deployed) {
        Disable-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue | Out-Null
        Stop-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
        Copy-Item -LiteralPath $backup -Destination $target -Force
    }
    if ($wasEnabled) {
        Enable-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue | Out-Null
    }
    throw $deployError
}

$pidsAfter = @{}
foreach ($port in @(8093, 8768, 8094, 8770)) {
    $pidsAfter[$port] = Get-ListenerPid $port
    if ($pidsAfter[$port] -ne $pidsBefore[$port]) { throw "PID changed on port $port" }
}
$markers = @(Get-Content -LiteralPath $log -Tail 20 | Where-Object {
    $_ -match 'scheduled_sync_(start|end|wrapper_error)'
})

[ordered]@{
    schema = 'ops.8093.heat-quality-sync-runner.v2'
    deployed_at = (Get-Date).ToString('o')
    backup_root = $backupRoot
    runner_hash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
    task_state = (Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName).State.ToString()
    last_run_time = $after.LastRunTime.ToString('o')
    last_task_result = $after.LastTaskResult
    recent_run_markers = $markers
    pids = [ordered]@{
        port_8093_before = $pidsBefore[8093]; port_8093_after = $pidsAfter[8093]
        port_8768_before = $pidsBefore[8768]; port_8768_after = $pidsAfter[8768]
        port_8094_before = $pidsBefore[8094]; port_8094_after = $pidsAfter[8094]
        port_8770_before = $pidsBefore[8770]; port_8770_after = $pidsAfter[8770]
    }
} | ConvertTo-Json -Depth 8
