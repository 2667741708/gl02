$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$OutputEncoding = [Text.UTF8Encoding]::new($false)

$projectRoot = 'F:\高炉炼铁项目-real-sensor-v2_V3'
$mainRoot = Join-Path $projectRoot '数据库同步和存取'
$mirrorRoot = Join-Path $projectRoot 'db_sync_storage'
$stage = 'C:\Users\Administrator\AppData\Local\Temp\foreman_points_coal_20260806'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { $python = 'C:\Program Files\Python311\python.exe' }

$files = @(
    @{ Relative = 'run_realtime_sync_pg_bg.ps1'; Candidate = 'run_realtime_sync_pg_bg.ps1' },
    @{ Relative = 'config\sync_config.json'; Candidate = 'sync_config.json' },
    @{ Relative = 'config\点位清单.tsv'; Candidate = '点位清单.tsv' },
    @{ Relative = 'schema\postgresql_required_points.sql'; Candidate = 'postgresql_required_points.sql' },
    @{ Relative = 'src\sync_from_243_pg.py'; Candidate = 'sync_from_243_pg.py' },
    @{ Relative = 'src\coal_hourly.py'; Candidate = 'coal_hourly.py' },
    @{ Relative = 'src\init_foreman_points_pg_light.py'; Candidate = 'init_foreman_points_pg_light.py' }
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
        ($_.CommandLine -match 'run_realtime_sync_pg_bg\.ps1|sync_from_243_pg\.py|run_sync_watchdog\.ps1|sync_watchdog\.py')
    })
}

function Start-SyncTasks([bool]$StartWatchdog) {
    Start-ScheduledTask -TaskPath '\' -TaskName 'BlastFurnaceV3PgContinuousSync30s'
    if ($StartWatchdog) {
        Start-ScheduledTask -TaskPath '\GL02SensorSync\' -TaskName 'Watchdog'
    }
}

foreach ($name in 'PSPACE_SERVER', 'PSPACE_PORT', 'PSPACE_USER', 'PSPACE_PASSWORD', 'PSPACE_SDK_ROOT', 'GL02_PGHOST', 'GL02_PGPORT', 'GL02_PGDATABASE', 'GL02_PGUSER', 'GL02_PGPASSWORD') {
    $value = [Environment]::GetEnvironmentVariable($name, 'Machine')
    if (-not $value) { $value = [Environment]::GetEnvironmentVariable($name, 'User') }
    if ($value) { Set-Item -Path "Env:$name" -Value $value }
}

foreach ($path in @($projectRoot, $mainRoot, $mirrorRoot, $stage, $python)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Missing required path: $path" }
}
foreach ($item in $files) {
    $candidate = Join-Path $stage $item.Candidate
    if (-not (Test-Path -LiteralPath $candidate)) { throw "Missing candidate: $candidate" }
}
foreach ($candidate in 'sync_from_243_pg.py', 'coal_hourly.py', 'init_foreman_points_pg_light.py', 'refresh_foreman_coal_hourly_once.py', 'verify_foreman_coal_hourly_db.py') {
    & $python -m py_compile (Join-Path $stage $candidate)
    if ($LASTEXITCODE -ne 0) { throw "Python validation failed: $candidate" }
}
$catalogText = Get-Content -LiteralPath (Join-Path $stage '点位清单.tsv') -Raw -Encoding UTF8
$schemaText = Get-Content -LiteralPath (Join-Path $stage 'postgresql_required_points.sql') -Raw -Encoding UTF8
if (-not $catalogText.Contains('SIO_GL02_PC_T0004') -or -not $catalogText.Contains('PCI_current_hour')) { throw 'Point catalog markers missing' }
foreach ($marker in 'SIO_CC_GF2_T0111', 'SIO_CC_GF2_T0112', 'SIO_CC_GF2_T0113', 'SIO_GL02_BT_T0133', 'SIO_GL02_BT_T0134', 'SIO_GL02_BT_T0136') {
    if (-not $catalogText.Contains($marker)) { throw "Point catalog marker missing: $marker" }
}
if (-not $schemaText.Contains('bf_sensor.coal_injection_hourly')) { throw 'Hourly schema marker missing' }

$protectedPorts = @(8093, 8094, 8768, 8770)
$protectedBefore = @{}
foreach ($port in $protectedPorts) {
    $pidValue = Get-ListenerPid $port
    if ($pidValue -le 0 -and $port -ne 8094) { throw "Protected listener missing before deployment: $port" }
    $protectedBefore[[string]$port] = $pidValue
}
$legacy = Get-ScheduledTask -TaskPath '\GL02SensorSync\' -TaskName 'Realtime'
if ($legacy.State -ne 'Disabled') { throw 'Legacy Realtime task must remain disabled' }
$watchdog = Get-ScheduledTask -TaskPath '\GL02SensorSync\' -TaskName 'Watchdog'
$restartWatchdog = $watchdog.State -eq 'Running'

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backup = Join-Path $projectRoot "logs\deploy_backups\foreman_points_coal_$stamp"
foreach ($rootName in 'main', 'mirror') {
    New-Item -ItemType Directory -Force -Path (Join-Path $backup $rootName) | Out-Null
}
foreach ($item in $files) {
    foreach ($rootInfo in @(@{ Name = 'main'; Root = $mainRoot }, @{ Name = 'mirror'; Root = $mirrorRoot })) {
        $target = Join-Path $rootInfo.Root $item.Relative
        if (Test-Path -LiteralPath $target) {
            $destination = Join-Path (Join-Path $backup $rootInfo.Name) $item.Relative
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
            Copy-Item -LiteralPath $target -Destination $destination -Force
        }
    }
}

$deployed = $false
$stoppedProcessIds = @()
try {
    Stop-ScheduledTask -TaskPath '\' -TaskName 'BlastFurnaceV3PgContinuousSync30s' -ErrorAction SilentlyContinue
    Stop-ScheduledTask -TaskPath '\GL02SensorSync\' -TaskName 'Watchdog' -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    for ($attempt = 0; $attempt -lt 3; $attempt++) {
        foreach ($process in @(Get-SyncProcesses | Sort-Object ProcessId -Descending)) {
            if ($stoppedProcessIds -notcontains [int]$process.ProcessId) {
                $stoppedProcessIds += [int]$process.ProcessId
            }
            Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds 1
        if ((Get-SyncProcesses).Count -eq 0) { break }
    }
    if ((Get-SyncProcesses).Count -ne 0) { throw 'Sync processes remain after targeted stop' }
    foreach ($oldLock in @(
        (Join-Path $mainRoot 'logs\realtime_sync_pg.lock'),
        (Join-Path $mirrorRoot 'logs\realtime_sync_pg.lock'),
        (Join-Path $projectRoot 'logs\realtime_sync_pg.lock')
    )) {
        Remove-Item -LiteralPath $oldLock -Force -ErrorAction SilentlyContinue
    }

    foreach ($item in $files) {
        $candidate = Join-Path $stage $item.Candidate
        foreach ($root in @($mainRoot, $mirrorRoot)) {
            $target = Join-Path $root $item.Relative
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
            Copy-Item -LiteralPath $candidate -Destination $target -Force
            if ((Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash) {
                throw "Candidate hash mismatch: $target"
            }
        }
    }

    $registryOutput = (& $python -X utf8 (Join-Path $stage 'init_foreman_points_pg_light.py') --root $mainRoot | Out-String)
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL schema/registry initialization failed' }
    $registryResult = $registryOutput | ConvertFrom-Json
    if (-not $registryResult.ok -or [int]$registryResult.confirmed_foreman_points -ne 19) {
        throw "sensor_registry registration incomplete: $registryOutput"
    }
    & $python -X utf8 (Join-Path $stage 'refresh_foreman_coal_hourly_once.py') --root $mainRoot --hours 3
    if ($LASTEXITCODE -ne 0) { throw 'Initial hourly coal refresh failed' }

    Start-SyncTasks -StartWatchdog:$restartWatchdog
    $deadline = (Get-Date).AddSeconds(25)
    do {
        Start-Sleep -Milliseconds 500
        $wrappers = @(Get-SyncProcesses | Where-Object { $_.CommandLine -match 'run_realtime_sync_pg_bg\.ps1' })
    } while ($wrappers.Count -ne 1 -and (Get-Date) -lt $deadline)
    if ($wrappers.Count -ne 1) { throw "Expected one realtime wrapper, found $($wrappers.Count)" }

    foreach ($port in $protectedPorts) {
        if ((Get-ListenerPid $port) -ne $protectedBefore[[string]$port]) { throw "Protected listener changed: $port" }
    }
    if ((Get-ScheduledTask -TaskPath '\GL02SensorSync\' -TaskName 'Realtime').State -ne 'Disabled') { throw 'Legacy Realtime task changed state' }
    $deployed = $true
}
catch {
    Stop-ScheduledTask -TaskPath '\' -TaskName 'BlastFurnaceV3PgContinuousSync30s' -ErrorAction SilentlyContinue
    Stop-ScheduledTask -TaskPath '\GL02SensorSync\' -TaskName 'Watchdog' -ErrorAction SilentlyContinue
    foreach ($process in @(Get-SyncProcesses)) { Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue }
    foreach ($item in $files) {
        foreach ($rootInfo in @(@{ Name = 'main'; Root = $mainRoot }, @{ Name = 'mirror'; Root = $mirrorRoot })) {
            $source = Join-Path (Join-Path $backup $rootInfo.Name) $item.Relative
            $target = Join-Path $rootInfo.Root $item.Relative
            if (Test-Path -LiteralPath $source) {
                Copy-Item -LiteralPath $source -Destination $target -Force
            }
            elseif (Test-Path -LiteralPath $target) {
                Remove-Item -LiteralPath $target -Force
            }
        }
    }
    Start-SyncTasks -StartWatchdog:$restartWatchdog
    throw
}

$protectedBeforeJson = [ordered]@{}
foreach ($key in $protectedBefore.Keys) {
    $protectedBeforeJson[[string]$key] = [int]$protectedBefore[$key]
}
[ordered]@{
    deployed = $deployed
    backup = $backup
    stopped_process_ids = @($stoppedProcessIds)
    wrapper_count = @(Get-SyncProcesses | Where-Object { $_.CommandLine -match 'run_realtime_sync_pg_bg\.ps1' }).Count
    protected_before = $protectedBeforeJson
    protected_after = [ordered]@{
        '8093' = Get-ListenerPid 8093
        '8094' = Get-ListenerPid 8094
        '8768' = Get-ListenerPid 8768
        '8770' = Get-ListenerPid 8770
    }
    continuous_task = [string](Get-ScheduledTask -TaskPath '\' -TaskName 'BlastFurnaceV3PgContinuousSync30s').State
    watchdog_task = [string](Get-ScheduledTask -TaskPath '\GL02SensorSync\' -TaskName 'Watchdog').State
    legacy_task = [string](Get-ScheduledTask -TaskPath '\GL02SensorSync\' -TaskName 'Realtime').State
} | ConvertTo-Json -Depth 6
