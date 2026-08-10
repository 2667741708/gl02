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
    $row = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($row) { return [int]$row.OwningProcess }
    return 0
}

function Install-Atomic([string]$Source, [string]$Target) {
    $temporary = "$Target.foreman.new"
    Copy-Item -LiteralPath $Source -Destination $temporary -Force
    Move-Item -LiteralPath $temporary -Destination $Target -Force
    if ((Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash -ne (Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash) {
        throw "Hash mismatch: $Target"
    }
}

foreach ($required in @($projectRoot, $mainRoot, $mirrorRoot, $stage, $python)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Missing required path: $required" }
}
foreach ($item in $files) {
    if (-not (Test-Path -LiteralPath (Join-Path $stage $item.Candidate))) { throw "Missing candidate: $($item.Candidate)" }
}
$catalogText = Get-Content -LiteralPath (Join-Path $stage '点位清单.tsv') -Raw -Encoding UTF8
foreach ($marker in 'SIO_CC_GF2_T0111', 'SIO_CC_GF2_T0112', 'SIO_CC_GF2_T0113', 'SIO_GL02_BT_T0133', 'SIO_GL02_BT_T0134', 'SIO_GL02_BT_T0136') {
    if (-not $catalogText.Contains($marker)) { throw "Point catalog marker missing: $marker" }
}
foreach ($candidate in 'sync_from_243_pg.py', 'coal_hourly.py', 'init_foreman_points_pg_light.py', 'refresh_foreman_coal_hourly_once.py') {
    & $python -m py_compile (Join-Path $stage $candidate)
    if ($LASTEXITCODE -ne 0) { throw "Python validation failed: $candidate" }
}

$protectedPorts = @(8093, 8094, 8768, 8770)
$protectedBefore = @{}
foreach ($port in $protectedPorts) {
    $pidValue = Get-ListenerPid $port
    if ($pidValue -le 0 -and $port -ne 8094) { throw "Protected listener missing: $port" }
    $protectedBefore[[string]$port] = $pidValue
}

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backup = Join-Path $projectRoot "logs\deploy_backups\foreman_points_coal_hot_$stamp"
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
try {
    foreach ($item in $files) {
        $candidate = Join-Path $stage $item.Candidate
        foreach ($root in @($mainRoot, $mirrorRoot)) {
            $target = Join-Path $root $item.Relative
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
            Install-Atomic -Source $candidate -Target $target
        }
    }

    $registryOutput = (& $python -X utf8 (Join-Path $stage 'init_foreman_points_pg_light.py') --root $mainRoot | Out-String)
    if ($LASTEXITCODE -ne 0) { throw 'Light schema/registry initialization failed' }
    $registryResult = $registryOutput | ConvertFrom-Json
    if (-not $registryResult.ok -or [int]$registryResult.confirmed_foreman_points -ne 19) {
        throw "sensor_registry registration incomplete: $registryOutput"
    }
    & $python -X utf8 (Join-Path $stage 'refresh_foreman_coal_hourly_once.py') --root $mainRoot --hours 3
    if ($LASTEXITCODE -ne 0) { throw 'Initial hourly coal refresh failed' }

    $continuous = Get-ScheduledTask -TaskPath '\' -TaskName 'BlastFurnaceV3PgContinuousSync30s'
    if ($continuous.State -ne 'Running') { Start-ScheduledTask -InputObject $continuous }
    $deadline = (Get-Date).AddSeconds(25)
    do {
        Start-Sleep -Milliseconds 500
        $continuous = Get-ScheduledTask -TaskPath '\' -TaskName 'BlastFurnaceV3PgContinuousSync30s'
    } while ($continuous.State -ne 'Running' -and (Get-Date) -lt $deadline)
    if ($continuous.State -ne 'Running') { throw 'Existing continuous sync task did not stay Running' }

    foreach ($port in $protectedPorts) {
        if ((Get-ListenerPid $port) -ne $protectedBefore[[string]$port]) { throw "Protected listener changed: $port" }
    }
    if ((Get-ScheduledTask -TaskPath '\GL02SensorSync\' -TaskName 'Realtime').State -ne 'Disabled') { throw 'Legacy realtime task changed state' }
    $deployed = $true
}
catch {
    foreach ($item in $files) {
        foreach ($rootInfo in @(@{ Name = 'main'; Root = $mainRoot }, @{ Name = 'mirror'; Root = $mirrorRoot })) {
            $source = Join-Path (Join-Path $backup $rootInfo.Name) $item.Relative
            $target = Join-Path $rootInfo.Root $item.Relative
            if (Test-Path -LiteralPath $source) { Install-Atomic -Source $source -Target $target }
            elseif (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Force }
        }
    }
    throw
}

[ordered]@{
    deployed = $deployed
    backup = $backup
    continuous_task = [string](Get-ScheduledTask -TaskPath '\' -TaskName 'BlastFurnaceV3PgContinuousSync30s').State
    watchdog_task = [string](Get-ScheduledTask -TaskPath '\GL02SensorSync\' -TaskName 'Watchdog').State
    legacy_task = [string](Get-ScheduledTask -TaskPath '\GL02SensorSync\' -TaskName 'Realtime').State
    protected_before = $protectedBefore
    protected_after = [ordered]@{
        8093 = Get-ListenerPid 8093
        8094 = Get-ListenerPid 8094
        8768 = Get-ListenerPid 8768
        8770 = Get-ListenerPid 8770
    }
    catalog_sha256 = (Get-FileHash -LiteralPath (Join-Path $mainRoot 'config\点位清单.tsv') -Algorithm SHA256).Hash
    sync_sha256 = (Get-FileHash -LiteralPath (Join-Path $mainRoot 'src\sync_from_243_pg.py') -Algorithm SHA256).Hash
} | ConvertTo-Json -Depth 6
