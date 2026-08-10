$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$stage = "C:\Users\Administrator\AppData\Local\Temp"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $root "backups\abc_heat_cooling_$stamp"
$service = "BFV4PreviewWs8768"
$files = @(
    @{relative="自动诊断服务\baseline_maintainer.py"; staged="abc_once_baseline_maintainer.py"},
    @{relative="自动诊断服务\store.py"; staged="abc_once_store.py"},
    @{relative="自动诊断服务\abc_feature_builder.py"; staged="abc_once_feature_builder.py"},
    @{relative="自动诊断服务\abc_rule_catalog.py"; staged="abc_once_rule_catalog.py"},
    @{relative="自动诊断服务\abc_rule_engine.py"; staged="abc_once_rule_engine.py"},
    @{relative="自动诊断服务\diagnosis_scheduler.py"; staged="abc_once_diagnosis_scheduler.py"},
    @{relative="自动诊断服务\local_pg_ws_bridge.py"; staged="abc_once_ws_bridge.py"},
    @{relative="自动诊断服务\config\abc_furnace_rules.v1.json"; staged="abc_once_rules_config.json"}
)

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

$before = @{p8093=Get-PortPid 8093; p8094=Get-PortPid 8094; p8768=Get-PortPid 8768; p8770=Get-PortPid 8770; p11434=Get-PortPid 11434}
if (-not $before.p8093 -or -not $before.p8094 -or -not $before.p8768 -or -not $before.p8770 -or -not $before.p11434) { throw "protected listener precondition failed" }
New-Item -ItemType Directory -Force -Path $backup | Out-Null
foreach ($entry in $files) {
    $relative = $entry.relative
    $source = Join-Path $stage $entry.staged
    $target = Join-Path $root $relative
    if (-not (Test-Path -LiteralPath $source)) { throw "missing staged file: $relative" }
    $backupTarget = Join-Path $backup $relative
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $backupTarget) | Out-Null
    Copy-Item -LiteralPath $target -Destination $backupTarget -Force
}

$stopped = $false
$deployed = $false
try {
    Stop-Service -Name $service -Force
    $stopped = $true
    Wait-Port 8768 $false 90
    foreach ($entry in $files) {
        $relative = $entry.relative
        $source = Join-Path $stage $entry.staged
        $target = Join-Path $root $relative
        $pending = "$target.pending"
        Copy-Item -LiteralPath $source -Destination $pending -Force
        Move-Item -LiteralPath $pending -Destination $target -Force
    }
    $deployed = $true
    Push-Location $root
    try {
        & python ".\自动诊断服务\baseline_maintainer.py" --build-day 2026-08-08 --baseline-days 30 --derived-only --write | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "derived baseline backfill failed" }
        & python ".\自动诊断服务\baseline_maintainer.py" --build-day 2026-08-08 --baseline-days 30 --cooling-only --write | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "cooling baseline backfill failed" }
    } finally {
        Pop-Location
    }
    Start-Service -Name $service
    $stopped = $false
    Wait-Port 8768 $true 150
} catch {
    if ($deployed) {
        foreach ($entry in $files) {
            $relative = $entry.relative
            $saved = Join-Path $backup $relative
            $target = Join-Path $root $relative
            if (Test-Path -LiteralPath $saved) { Copy-Item -LiteralPath $saved -Destination $target -Force }
        }
    }
    if ((Get-Service -Name $service).Status -ne "Running") { Start-Service -Name $service -ErrorAction SilentlyContinue }
    throw
}

$after = @{p8093=Get-PortPid 8093; p8094=Get-PortPid 8094; p8768=Get-PortPid 8768; p8770=Get-PortPid 8770; p11434=Get-PortPid 11434}
if ($after.p8093 -ne $before.p8093 -or $after.p8094 -ne $before.p8094 -or $after.p8770 -ne $before.p8770 -or $after.p11434 -ne $before.p11434) { throw "protected PID changed" }
$http = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8094/" -TimeoutSec 30
if ([int]$http.StatusCode -ne 200) { throw "8094 HTTP failed" }
$hashes = foreach ($entry in $files) {
    $relative = $entry.relative
    $item = Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $root $relative)
    [ordered]@{file=$relative; sha256=$item.Hash}
}
[ordered]@{ok=$true; backup=$backup; before=$before; after=$after; http8094=[int]$http.StatusCode; hashes=$hashes} | ConvertTo-Json -Depth 6
