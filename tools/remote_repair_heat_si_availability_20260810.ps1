$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) {
    throw 'This repair must run under PowerShell 7 Core.'
}

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$standalone = Join-Path $root 'standalone_heat_dashboard_8891'
$taskPath = '\BlastFurnaceServices\'
$taskName = 'HeatPerformanceQualitySync'
$pwsh = 'C:\Program Files\PowerShell\7\pwsh.exe'
$python = 'C:\Program Files\Python311\python.exe'
$runner = Join-Path $standalone 'tools\run_22012_heat_performance_sync.ps1'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupRoot = Join-Path $root "logs\deploy_backups\heat_si_availability_$stamp"
$stageRoot = 'C:\Users\Administrator\AppData\Local\Temp'

$files = @(
    [pscustomobject]@{
        Stage = Join-Path $stageRoot 'heat_si_availability_heat_performance_quality.py'
        Target = Join-Path $standalone '高炉前端数据\智能助手\backend\heat_performance_quality.py'
        Hash = 'DA64B4B993C1E7210FBDAE018E8BCEA43622B228F6237F560D2F38D5725B89A4'
        Backup = 'heat_performance_quality.py.bak'
    },
    [pscustomobject]@{
        Stage = Join-Path $stageRoot 'heat_si_availability_sync.py'
        Target = Join-Path $standalone 'tools\sync_22012_heat_performance_quality.py'
        Hash = '30D8A8E8FB8508EFF6787DD76CB4AC005984412564FCC6EF44F9F4727489CABE'
        Backup = 'sync_22012_heat_performance_quality.py.bak'
    },
    [pscustomobject]@{
        Stage = Join-Path $stageRoot 'heat_si_availability_runner.ps1'
        Target = $runner
        Hash = 'CBB1D9CC166669E72FC47AE0498595ED0E8FB3F2C32E5C8A6B702D62F1D20AA1'
        Backup = 'run_22012_heat_performance_sync.ps1.bak'
    }
)

function Get-ListenerPid([int]$Port) {
    $line = @(netstat.exe -ano | Where-Object {
        $_ -match ":$Port\s" -and $_ -match 'LISTENING\s+(\d+)\s*$'
    })[0]
    if (-not $line) { return $null }
    [void]($line -match 'LISTENING\s+(\d+)\s*$')
    return [int]$matches[1]
}

function Install-StagedFile($Item) {
    $temporary = "$($Item.Target).deploy_$stamp"
    Copy-Item -LiteralPath $Item.Stage -Destination $temporary -Force
    Move-Item -LiteralPath $temporary -Destination $Item.Target -Force
}

foreach ($required in @($standalone, $pwsh, $python, $runner)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Missing required path: $required" }
}
foreach ($item in $files) {
    if (-not (Test-Path -LiteralPath $item.Stage -PathType Leaf)) {
        throw "Missing staged file: $($item.Stage)"
    }
    $actual = (Get-FileHash -LiteralPath $item.Stage -Algorithm SHA256).Hash
    if ($actual -ne $item.Hash) { throw "Staged hash mismatch: $($item.Stage)" }
}

& $python -X utf8 -m py_compile $files[0].Stage $files[1].Stage
if ($LASTEXITCODE -ne 0) { throw 'Staged Python compile failed.' }

$protectedBefore = @{}
foreach ($port in @(8093, 8094, 8768, 8770, 5432)) {
    $protectedBefore[$port] = Get-ListenerPid $port
    if (-not $protectedBefore[$port]) { throw "Protected port $port is not listening." }
}

$task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
$taskWasEnabled = [int]$task.State -ne 1
$oldAction = $task.Actions[0]

New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
foreach ($item in $files) {
    Copy-Item -LiteralPath $item.Target -Destination (Join-Path $backupRoot $item.Backup) -Force
}
Export-ScheduledTask -TaskPath $taskPath -TaskName $taskName |
    Set-Content -LiteralPath (Join-Path $backupRoot 'HeatPerformanceQualitySync.xml') -Encoding UTF8

$deployed = $false
$rollbackApplied = $false
try {
    Disable-ScheduledTask -TaskPath $taskPath -TaskName $taskName | Out-Null
    Stop-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue

    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    while ([int](Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName).State -eq 4) {
        if ([DateTime]::UtcNow -ge $deadline) { throw 'HeatPerformanceQualitySync did not stop.' }
        Start-Sleep -Milliseconds 250
    }

    foreach ($item in $files) { Install-StagedFile $item }
    $deployed = $true

    & $python -X utf8 -m py_compile $files[0].Target $files[1].Target
    if ($LASTEXITCODE -ne 0) { throw 'Deployed Python compile failed.' }

    $newAction = New-ScheduledTaskAction -Execute $pwsh -Argument (
        '-NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $runner
    )
    Set-ScheduledTask -TaskPath $taskPath -TaskName $taskName -Action $newAction | Out-Null
    Enable-ScheduledTask -TaskPath $taskPath -TaskName $taskName | Out-Null

    & $pwsh -NoProfile -ExecutionPolicy Bypass -File $runner
    if ($LASTEXITCODE -ne 0) { throw "Manual HeatPerformanceQualitySync failed with exit code $LASTEXITCODE." }
} catch {
    $repairError = $_
    try {
        Stop-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue
        foreach ($item in $files) {
            $backup = Join-Path $backupRoot $item.Backup
            if (Test-Path -LiteralPath $backup) {
                Copy-Item -LiteralPath $backup -Destination $item.Target -Force
            }
        }
        Set-ScheduledTask -TaskPath $taskPath -TaskName $taskName -Action $oldAction | Out-Null
        $rollbackApplied = $true
    } finally {
        if ($taskWasEnabled) {
            Enable-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction SilentlyContinue | Out-Null
        }
    }
    throw $repairError
}

foreach ($item in $files) {
    $actual = (Get-FileHash -LiteralPath $item.Target -Algorithm SHA256).Hash
    if ($actual -ne $item.Hash) { throw "Deployed hash mismatch: $($item.Target)" }
}

$protectedAfter = @{}
foreach ($port in @(8093, 8094, 8768, 8770, 5432)) {
    $protectedAfter[$port] = Get-ListenerPid $port
    if ($protectedAfter[$port] -ne $protectedBefore[$port]) {
        throw "Protected PID changed on port $port."
    }
}

$finalTask = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName
$finalAction = $finalTask.Actions[0]
$api8093 = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/si-v20/status' -TimeoutSec 30
$api8094 = Invoke-RestMethod -Uri 'http://127.0.0.1:8094/api/si-v20/status' -TimeoutSec 30
if (-not $api8093.ok -or -not $api8094.ok) { throw 'V20 status API verification failed.' }

[ordered]@{
    schema = 'ops.heat-si-availability-repair.v1'
    repaired_at = (Get-Date).ToString('o')
    backup_root = $backupRoot
    deployed = $deployed
    rollback_applied = $rollbackApplied
    task_state = [int]$finalTask.State
    task_execute = $finalAction.Execute
    task_arguments = $finalAction.Arguments
    powershell_edition = $PSVersionTable.PSEdition
    powershell_version = $PSVersionTable.PSVersion.ToString()
    api_8093_ok = [bool]$api8093.ok
    api_8094_ok = [bool]$api8094.ok
    protected_pids = [ordered]@{
        port_8093 = $protectedAfter[8093]
        port_8094 = $protectedAfter[8094]
        port_8768 = $protectedAfter[8768]
        port_8770 = $protectedAfter[8770]
        port_5432 = $protectedAfter[5432]
    }
} | ConvertTo-Json -Depth 6
