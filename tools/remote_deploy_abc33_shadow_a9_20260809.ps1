$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$builderFile = Get-ChildItem -LiteralPath "F:\" -Recurse -Filter "abc_feature_builder.py" -File -ErrorAction SilentlyContinue | Where-Object { $_.FullName -match 'V4_8093_PREVIEW' -and $_.FullName -notmatch '\\backups\\' } | Select-Object -First 1
$serviceDir = if ($builderFile) { $builderFile.DirectoryName } else { $null }
if (-not $serviceDir) { throw "ABC service directory not found" }
$root = Split-Path -Parent $serviceDir
$configDir = Join-Path $serviceDir "config"
$stage = "C:\Users\Administrator\AppData\Local\Temp"
$service = "BFV4PreviewWs8768"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $root "backups\abc33_shadow_a9_20260809\$stamp"
$files = @(
    @{name="baseline_maintainer.py"; target=(Join-Path $serviceDir "baseline_maintainer.py"); staged="abc33_a9_baseline_maintainer.py"},
    @{name="store.py"; target=(Join-Path $serviceDir "store.py"); staged="abc33_a9_store.py"},
    @{name="abc_feature_builder.py"; target=(Join-Path $serviceDir "abc_feature_builder.py"); staged="abc33_a9_feature_builder.py"},
    @{name="abc_rule_catalog.py"; target=(Join-Path $serviceDir "abc_rule_catalog.py"); staged="abc33_a9_rule_catalog.py"},
    @{name="abc_rule_engine.py"; target=(Join-Path $serviceDir "abc_rule_engine.py"); staged="abc33_a9_rule_engine.py"},
    @{name="diagnosis_scheduler.py"; target=(Join-Path $serviceDir "diagnosis_scheduler.py"); staged="abc33_a9_diagnosis_scheduler.py"},
    @{name="local_pg_ws_bridge.py"; target=(Join-Path $serviceDir "local_pg_ws_bridge.py"); staged="abc33_a9_ws_bridge.py"},
    @{name="abc_furnace_rules.v1.json"; target=(Join-Path $configDir "abc_furnace_rules.v1.json"); staged="abc33_a9_rules_config.json"}
)

function Get-PortPid([int]$port) {
    $row = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($row) { return [int]$row.OwningProcess }
    return $null
}

function Wait-Port([int]$port, [bool]$listening, [int]$seconds) {
    $deadline = (Get-Date).AddSeconds($seconds)
    do {
        if (($null -ne (Get-PortPid $port)) -eq $listening) { return }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)
    throw "Port $port did not reach listening=$listening"
}

$before = [ordered]@{
    p8093 = Get-PortPid 8093
    p8094 = Get-PortPid 8094
    p8768 = Get-PortPid 8768
    p8770 = Get-PortPid 8770
    p11434 = Get-PortPid 11434
}
foreach ($protected in @("p8093","p8094","p8768","p8770","p11434")) {
    if (-not $before[$protected]) { throw "Missing protected listener: $protected" }
}
if ((Get-Service -Name $service).Status -ne "Running") { throw "$service is not running" }

New-Item -ItemType Directory -Force -Path $backup | Out-Null
foreach ($entry in $files) {
    $source = Join-Path $stage $entry.staged
    $target = $entry.target
    if (-not (Test-Path -LiteralPath $source)) { throw "Missing staged file: $source" }
    if (-not (Test-Path -LiteralPath $target)) { throw "Missing target file: $target" }
    $saved = Join-Path $backup $entry.name
    Copy-Item -LiteralPath $target -Destination $saved -Force
}

$deployed = $false
$serviceStopped = $false
try {
    Stop-Service -Name $service -Force
    $serviceStopped = $true
    Wait-Port 8768 $false 90

    foreach ($entry in $files) {
        $source = Join-Path $stage $entry.staged
        $target = $entry.target
        $pending = "$target.pending"
        Copy-Item -LiteralPath $source -Destination $pending -Force
        Move-Item -LiteralPath $pending -Destination $target -Force
    }
    $deployed = $true

    $python = "C:\Program Files\Python311\python.exe"
    foreach ($entry in $files | Where-Object { $_.name.EndsWith('.py') }) {
        $target = $entry.target
        & $python -m py_compile $target
        if ($LASTEXITCODE -ne 0) { throw "py_compile failed: $($entry.name)" }
    }
    $configPath = Join-Path $configDir "abc_furnace_rules.v1.json"
    Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json | Out-Null

    try {
        Start-Service -Name $service -ErrorAction Stop
    } catch {
        Write-Output ('START_SERVICE_WARNING=' + $_.Exception.Message)
    }
    Wait-Port 8768 $true 150
    $serviceStopped = $false

    foreach ($entry in $files) {
        $source = Join-Path $stage $entry.staged
        $target = $entry.target
        $sourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $source).Hash
        $targetHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $target).Hash
        if ($sourceHash -ne $targetHash) { throw "Hash mismatch: $($entry.name)" }
    }

    $after = [ordered]@{
        p8093 = Get-PortPid 8093
        p8094 = Get-PortPid 8094
        p8768 = Get-PortPid 8768
        p8770 = Get-PortPid 8770
        p11434 = Get-PortPid 11434
    }
    foreach ($protected in @("p8093","p8094","p8770","p11434")) {
        if ($after[$protected] -ne $before[$protected]) { throw "Protected PID changed: $protected" }
    }
    if ($after.p8768 -eq $before.p8768) { throw "8768 PID did not change" }

    $http8093 = (Invoke-WebRequest -UseBasicParsing -TimeoutSec 20 -Uri "http://127.0.0.1:8093/?cb=abc33-a9-$stamp").StatusCode
    $http8094 = (Invoke-WebRequest -UseBasicParsing -TimeoutSec 20 -Uri "http://127.0.0.1:8094/?cb=abc33-a9-$stamp").StatusCode
    if ($http8093 -ne 200 -or $http8094 -ne 200) { throw "HTTP verification failed" }

    [pscustomobject]@{
        ok = $true
        rollback = $false
        backup = $backup
        before = $before
        after = $after
        http8093 = $http8093
        http8094 = $http8094
        release_mode = (Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json).release_control.mode
        deployed_files = @($files.name)
    } | ConvertTo-Json -Depth 6
} catch {
    $failure = $_.Exception.Message
    if ($deployed) {
        foreach ($entry in $files) {
            $saved = Join-Path $backup $entry.name
            $target = $entry.target
            if (Test-Path -LiteralPath $saved) { Copy-Item -LiteralPath $saved -Destination $target -Force }
        }
    }
    if ((Get-Service -Name $service).Status -ne "Running") { Start-Service -Name $service }
    Wait-Port 8768 $true 150
    [pscustomobject]@{ok=$false;rollback=$deployed;backup=$backup;error=$failure} | ConvertTo-Json -Depth 4
    throw
} finally {
    if ($serviceStopped -and (Get-Service -Name $service).Status -ne "Running") {
        Start-Service -Name $service -ErrorAction SilentlyContinue
    }
}
