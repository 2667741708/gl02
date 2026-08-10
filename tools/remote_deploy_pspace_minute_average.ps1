$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$ErrorActionPreference = 'Stop'

$projectRoot = 'F:\高炉炼铁项目-real-sensor-v2_V3'
$mainRoot = Join-Path $projectRoot '数据库同步和存取'
$mirrorRoot = Join-Path $projectRoot 'db_sync_storage'
$stageRoot = 'C:\Users\Administrator\AppData\Local\Temp\pspace_minute_average_20260805'
$backupRoot = Join-Path $projectRoot ('logs\deploy_backups\pspace_minute_average_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
$latestMarker = Join-Path $projectRoot 'logs\deploy_backups\pspace_minute_average_latest.txt'

$files = @(
    @{ Relative = 'config\sync_config.json'; Candidate = 'sync_config.json'; Prefix = '0EAB74' },
    @{ Relative = 'schema\postgresql_required_points.sql'; Candidate = 'postgresql_required_points.sql'; Prefix = 'EA44AB' },
    @{ Relative = 'src\sync_from_243_pg.py'; Candidate = 'sync_from_243_pg.py'; Prefix = '05C761' },
    @{ Relative = 'src\pg_store.py'; Candidate = 'pg_store.py'; Prefix = '83B454' },
    @{ Relative = 'run_realtime_sync_pg_bg.ps1'; Candidate = 'run_realtime_sync_pg_bg.ps1'; Prefix = 'B05B89' },
    @{ Relative = 'run_22012_continuous_sync.ps1'; Candidate = 'run_22012_continuous_sync.ps1'; Prefix = 'A0A464' },
    @{ Relative = 'src\raw_minute_pipeline.py'; Candidate = 'raw_minute_pipeline.py'; Prefix = $null }
)

function Get-ListenerPid([int]$Port) {
    $row = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Sort-Object OwningProcess |
        Select-Object -First 1
    if ($row) { return [int]$row.OwningProcess }
    return 0
}

function Get-SyncProcesses {
    return @(Get-CimInstance -ClassName Win32_Process | Where-Object {
        $_.CommandLine -and
        $_.CommandLine.IndexOf($projectRoot, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        ($_.CommandLine -match 'run_realtime_sync_pg_bg\.ps1|sync_from_243_pg\.py')
    })
}

function Start-ExpectedTasks([bool]$StartWatchdog) {
    Start-ScheduledTask -TaskPath '\' -TaskName 'BlastFurnaceV3PgContinuousSync30s'
    $deadline = (Get-Date).AddSeconds(20)
    do {
        Start-Sleep -Milliseconds 500
        $wrappers = @(Get-SyncProcesses | Where-Object { $_.CommandLine -match 'run_realtime_sync_pg_bg\.ps1' })
    } while ($wrappers.Count -lt 1 -and (Get-Date) -lt $deadline)
    if ($StartWatchdog) {
        Start-ScheduledTask -TaskPath '\GL02SensorSync\' -TaskName 'Watchdog'
    }
}

$protectedPorts = @(8093, 8094, 8768, 8770)
$protectedBefore = @{}
foreach ($port in $protectedPorts) {
    $pidValue = Get-ListenerPid $port
    if ($pidValue -le 0) { throw "protected listener missing before deployment: $port" }
    $protectedBefore[[string]$port] = $pidValue
}

foreach ($name in 'PSPACE_SERVER', 'PSPACE_PORT', 'PSPACE_USER', 'PSPACE_PASSWORD', 'PSPACE_SDK_ROOT', 'GL02_PGHOST', 'GL02_PGPORT', 'GL02_PGDATABASE', 'GL02_PGUSER', 'GL02_PGPASSWORD') {
    $value = [Environment]::GetEnvironmentVariable($name, 'Machine')
    if (-not $value) { $value = [Environment]::GetEnvironmentVariable($name, 'User') }
    if ($value) { Set-Item -Path "Env:$name" -Value $value }
}
if (-not $env:PSPACE_USER -or -not $env:PSPACE_PASSWORD) {
    throw 'pSpace machine credentials are unavailable'
}

$oldRealtime = Get-ScheduledTask -TaskPath '\GL02SensorSync\' -TaskName 'Realtime'
if ($oldRealtime.State -ne 'Disabled') {
    throw 'legacy Realtime task must remain disabled'
}
$watchdogTask = Get-ScheduledTask -TaskPath '\GL02SensorSync\' -TaskName 'Watchdog'
$restartWatchdog = $watchdogTask.State -eq 'Running'

foreach ($item in $files) {
    $candidate = Join-Path $stageRoot $item.Candidate
    if (-not (Test-Path -LiteralPath $candidate)) { throw "candidate missing: $candidate" }
    foreach ($root in @($mainRoot, $mirrorRoot)) {
        $target = Join-Path $root $item.Relative
        if ($item.Prefix) {
            if (-not (Test-Path -LiteralPath $target)) { throw "existing target missing: $target" }
            $hash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
            if (-not $hash.StartsWith($item.Prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "unexpected pre-deploy hash: $target"
            }
        }
        elseif (Test-Path -LiteralPath $target) {
            throw "new target already exists before deployment: $target"
        }
    }
    $mainTarget = Join-Path $mainRoot $item.Relative
    $mirrorTarget = Join-Path $mirrorRoot $item.Relative
    if ($item.Prefix) {
        $mainHash = (Get-FileHash -LiteralPath $mainTarget -Algorithm SHA256).Hash
        $mirrorHash = (Get-FileHash -LiteralPath $mirrorTarget -Algorithm SHA256).Hash
        if ($mainHash -ne $mirrorHash) { throw "main/mirror differ before deployment: $($item.Relative)" }
    }
}

$null = Get-Content -LiteralPath (Join-Path $stageRoot 'sync_config.json') -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($candidateName in 'run_realtime_sync_pg_bg.ps1', 'run_22012_continuous_sync.ps1') {
    $candidatePath = Join-Path $stageRoot $candidateName
    $tokens = $null
    $parseErrors = $null
    [System.Management.Automation.Language.Parser]::ParseFile($candidatePath, [ref]$tokens, [ref]$parseErrors) | Out-Null
    if ($parseErrors.Count -gt 0) { throw "PowerShell candidate syntax failed: $candidateName" }
}

New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
foreach ($rootName in 'main', 'mirror') {
    New-Item -ItemType Directory -Force -Path (Join-Path $backupRoot $rootName) | Out-Null
}
foreach ($item in $files | Where-Object { $_.Prefix }) {
    $mainBackup = Join-Path (Join-Path $backupRoot 'main') $item.Relative
    $mirrorBackup = Join-Path (Join-Path $backupRoot 'mirror') $item.Relative
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $mainBackup) | Out-Null
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $mirrorBackup) | Out-Null
    Copy-Item -LiteralPath (Join-Path $mainRoot $item.Relative) -Destination $mainBackup -Force
    Copy-Item -LiteralPath (Join-Path $mirrorRoot $item.Relative) -Destination $mirrorBackup -Force
}
Set-Content -LiteralPath $latestMarker -Value $backupRoot -Encoding UTF8

$stoppedProcessIds = @()
$deployed = $false
try {
    Stop-ScheduledTask -TaskPath '\' -TaskName 'BlastFurnaceV3PgContinuousSync30s' -ErrorAction SilentlyContinue
    Stop-ScheduledTask -TaskPath '\GL02SensorSync\' -TaskName 'Watchdog' -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2

    $syncProcesses = @(Get-SyncProcesses)
    foreach ($process in $syncProcesses | Sort-Object ProcessId -Descending) {
        $stoppedProcessIds += [int]$process.ProcessId
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
    if ((Get-SyncProcesses).Count -ne 0) { throw 'sync processes remain after targeted stop' }

    foreach ($oldLock in @(
        (Join-Path $mainRoot 'logs\realtime_sync_pg.lock'),
        (Join-Path $mirrorRoot 'logs\realtime_sync_pg.lock'),
        (Join-Path $projectRoot 'logs\realtime_sync_pg.lock')
    )) {
        Remove-Item -LiteralPath $oldLock -Force -ErrorAction SilentlyContinue
    }

    foreach ($item in $files) {
        $candidate = Join-Path $stageRoot $item.Candidate
        foreach ($root in @($mainRoot, $mirrorRoot)) {
            $target = Join-Path $root $item.Relative
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
            Copy-Item -LiteralPath $candidate -Destination $target -Force
            $candidateHash = (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash
            $targetHash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
            if ($candidateHash -ne $targetHash) { throw "post-copy hash mismatch: $target" }
        }
    }

    $python = Join-Path $projectRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) { $python = 'C:\Program Files\Python311\python.exe' }
    & $python -X utf8 (Join-Path $mainRoot 'src\init_pg.py') --skip-retention
    if ($LASTEXITCODE -ne 0) { throw "schema migration failed with exit code $LASTEXITCODE" }

    Start-ExpectedTasks -StartWatchdog:$restartWatchdog
    Start-Sleep -Seconds 5
    $wrappers = @(Get-SyncProcesses | Where-Object { $_.CommandLine -match 'run_realtime_sync_pg_bg\.ps1' })
    if ($wrappers.Count -ne 1) { throw "expected one realtime wrapper after deployment, found $($wrappers.Count)" }

    foreach ($port in $protectedPorts) {
        $afterPid = Get-ListenerPid $port
        if ($afterPid -ne $protectedBefore[[string]$port]) {
            throw "protected listener changed: $port before=$($protectedBefore[[string]$port]) after=$afterPid"
        }
    }
    if ((Get-ScheduledTask -TaskPath '\GL02SensorSync\' -TaskName 'Realtime').State -ne 'Disabled') {
        throw 'legacy Realtime task changed state'
    }
    $deployed = $true
}
catch {
    Stop-ScheduledTask -TaskPath '\' -TaskName 'BlastFurnaceV3PgContinuousSync30s' -ErrorAction SilentlyContinue
    Stop-ScheduledTask -TaskPath '\GL02SensorSync\' -TaskName 'Watchdog' -ErrorAction SilentlyContinue
    foreach ($process in @(Get-SyncProcesses)) {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }
    foreach ($item in $files | Where-Object { $_.Prefix }) {
        Copy-Item -LiteralPath (Join-Path (Join-Path $backupRoot 'main') $item.Relative) -Destination (Join-Path $mainRoot $item.Relative) -Force
        Copy-Item -LiteralPath (Join-Path (Join-Path $backupRoot 'mirror') $item.Relative) -Destination (Join-Path $mirrorRoot $item.Relative) -Force
    }
    foreach ($root in @($mainRoot, $mirrorRoot)) {
        Remove-Item -LiteralPath (Join-Path $root 'src\raw_minute_pipeline.py') -Force -ErrorAction SilentlyContinue
    }
    Start-ExpectedTasks -StartWatchdog:$restartWatchdog
    throw
}

$protectedAfter = @{}
foreach ($port in $protectedPorts) { $protectedAfter[[string]$port] = Get-ListenerPid $port }
$result = [pscustomobject]@{
    deployed = $deployed
    backup = $backupRoot
    stopped_process_ids = @($stoppedProcessIds)
    wrapper_count = @(Get-SyncProcesses | Where-Object { $_.CommandLine -match 'run_realtime_sync_pg_bg\.ps1' }).Count
    protected_before = $protectedBefore
    protected_after = $protectedAfter
    main_task_state = [string](Get-ScheduledTask -TaskPath '\' -TaskName 'BlastFurnaceV3PgContinuousSync30s').State
    watchdog_task_state = [string](Get-ScheduledTask -TaskPath '\GL02SensorSync\' -TaskName 'Watchdog').State
    legacy_task_state = [string](Get-ScheduledTask -TaskPath '\GL02SensorSync\' -TaskName 'Realtime').State
}
$result | ConvertTo-Json -Depth 6
