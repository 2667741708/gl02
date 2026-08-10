$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$stage = "C:\Users\Administrator\AppData\Local\Temp"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $root "backups\abc_pspace_heat_cooling_$stamp"
$service = "BFV4PreviewWs8768"
$runtimeFiles = @(
    @{relative="自动诊断服务\baseline_maintainer.py"; staged="abc_final_baseline_maintainer.py"},
    @{relative="自动诊断服务\store.py"; staged="abc_final_store.py"},
    @{relative="自动诊断服务\abc_feature_builder.py"; staged="abc_final_feature_builder.py"},
    @{relative="自动诊断服务\abc_rule_catalog.py"; staged="abc_final_rule_catalog.py"},
    @{relative="自动诊断服务\abc_rule_engine.py"; staged="abc_final_rule_engine.py"},
    @{relative="自动诊断服务\diagnosis_scheduler.py"; staged="abc_final_diagnosis_scheduler.py"},
    @{relative="自动诊断服务\local_pg_ws_bridge.py"; staged="abc_final_ws_bridge.py"},
    @{relative="自动诊断服务\config\abc_furnace_rules.v1.json"; staged="abc_final_rules_config.json"}
)
$syncRoot = "F:\高炉炼铁项目-real-sensor-v2_V3\db_sync_storage"
$syncTarget = Join-Path $syncRoot "src\sync_from_243_pg.py"
$syncBackup = Join-Path $backup "sync_from_243_pg.py"
$syncStage = Join-Path $stage "abc_final_sync_from_243_pg.py"
$variables = "Q_soft_water,P_soft_water,Q_high_pressure_water,P_high_pressure_water,P_medium_pressure_water,ExpansionTankLevel"

function Get-PortPid([int]$port) {
    $item = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($item) { return [int]$item.OwningProcess }
    return $null
}
function Wait-Port([int]$port, [bool]$expected, [int]$seconds) {
    $deadline = (Get-Date).AddSeconds($seconds)
    do {
        if (($null -ne (Get-PortPid $port)) -eq $expected) { return }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)
    throw "port $port did not reach listening=$expected"
}
function Start-8768WithRetry {
    for ($attempt=1; $attempt -le 3; $attempt++) {
        Start-Service -Name $service -ErrorAction SilentlyContinue
        try { Wait-Port 8768 $true 60; return } catch { Start-Sleep -Seconds 5 }
    }
    throw "8768 failed to start after three attempts"
}
function Backup-One([string]$relative) {
    $source = Join-Path $root $relative
    $target = Join-Path $backup $relative
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
    Copy-Item -LiteralPath $source -Destination $target -Force
}
function Restore-One([string]$relative) {
    $source = Join-Path $backup $relative
    $target = Join-Path $root $relative
    if (Test-Path -LiteralPath $source) { Copy-Item -LiteralPath $source -Destination $target -Force }
}

$before = @{p8093=Get-PortPid 8093; p8094=Get-PortPid 8094; p8768=Get-PortPid 8768; p8770=Get-PortPid 8770; p11434=Get-PortPid 11434}
if (-not $before.p8093 -or -not $before.p8094 -or -not $before.p8768 -or -not $before.p8770 -or -not $before.p11434) { throw "protected listener precondition failed" }
New-Item -ItemType Directory -Force -Path $backup | Out-Null
Copy-Item -LiteralPath $syncTarget -Destination $syncBackup -Force
foreach ($entry in $runtimeFiles) { Backup-One $entry.relative }
if (-not (Test-Path -LiteralPath $syncStage)) { throw "missing staged sync script" }
foreach ($entry in $runtimeFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $stage $entry.staged))) { throw ("missing staged runtime file: " + $entry.staged) }
}

Copy-Item -LiteralPath $syncStage -Destination "$syncTarget.pending" -Force
Move-Item -LiteralPath "$syncTarget.pending" -Destination $syncTarget -Force
Push-Location $syncRoot
try {
    & python ".\src\sync_from_243_pg.py" --days 90 --chunk-hours 12 --batch-size 6 --max-workers 1 --source-mode processed --source-aggregate average --target-aggregate PS_HIS_AVERAGE --target-interval-seconds 60 --no-persist-raw-5s --variables $variables --skip-retention
    if ($LASTEXITCODE -ne 0) { throw "pSpace 90-day cooling backfill failed" }
} catch {
    Copy-Item -LiteralPath $syncBackup -Destination $syncTarget -Force
    Pop-Location
    throw
}
Pop-Location

$stopped = $false
$activated = $false
try {
    Stop-Service -Name $service -Force
    $stopped = $true
    Wait-Port 8768 $false 90
    foreach ($entry in $runtimeFiles) {
        $source = Join-Path $stage $entry.staged
        $target = Join-Path $root $entry.relative
        Copy-Item -LiteralPath $source -Destination "$target.pending" -Force
        Move-Item -LiteralPath "$target.pending" -Destination $target -Force
    }
    $activated = $true
    Push-Location $root
    try {
        & python ".\自动诊断服务\baseline_maintainer.py" --build-day 2026-08-08 --baseline-days 30 --derived-only --write | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "derived baseline build failed" }
        & python ".\自动诊断服务\baseline_maintainer.py" --build-day 2026-08-08 --baseline-days 30 --cooling-only --write | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "cooling baseline build failed" }
    } finally { Pop-Location }
    Start-8768WithRetry
    $stopped = $false
} catch {
    if ($activated) { foreach ($entry in $runtimeFiles) { Restore-One $entry.relative } }
    if (-not (Get-PortPid 8768)) { Start-8768WithRetry }
    throw
}

$after = @{p8093=Get-PortPid 8093; p8094=Get-PortPid 8094; p8768=Get-PortPid 8768; p8770=Get-PortPid 8770; p11434=Get-PortPid 11434}
if ($after.p8093 -ne $before.p8093 -or $after.p8094 -ne $before.p8094 -or $after.p8770 -ne $before.p8770 -or $after.p11434 -ne $before.p11434) { throw "protected PID changed" }
$http = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8094/" -TimeoutSec 30
if ([int]$http.StatusCode -ne 200) { throw "8094 HTTP failed" }
[ordered]@{ok=$true; backup=$backup; variables=$variables; before=$before; after=$after; http8094=[int]$http.StatusCode} | ConvertTo-Json -Depth 5
