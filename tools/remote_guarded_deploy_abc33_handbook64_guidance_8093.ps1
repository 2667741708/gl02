$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$stage = 'C:\Users\Administrator\AppData\Local\Temp\abc33_handbook64_guidance'
$service = 'BFV4PreviewProxy8093'
$manager = Join-Path $root 'tools\manage_22012_managed_services.ps1'
$serviceConfig = Join-Path $root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$asset = Join-Path $root '高炉前端数据\assets\abc-furnace-rules-production.js'
$page8093 = Join-Path $root '高炉前端数据\frontend_dashboard_v3.server.html'
$page8094 = Join-Path $root '高炉前端数据\frontend_dashboard_v3.8094_preview.server.html'
$proxy = Join-Path $root '高炉前端数据\智能助手\backend\ollama_proxy_server.py'
$stagedAsset = Join-Path $stage 'abc-furnace-rules-production.js'
$expectedAssetHash = '976EB61B2E0F089AEE36E4ADC91B62C4D48AFBD78BAD59A8FDF8E3F822FF5FB1'
$version = 'abc33-20260810-handbook64-guidance-r1'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backup = Join-Path $root "backups\abc33_handbook64_guidance_8093_$stamp"

function Get-PortPid([int]$Port) {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($listener) { return [int]$listener.OwningProcess }
    return $null
}

function Wait-Port([int]$Port, [bool]$Expected, [int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    do {
        if (($null -ne (Get-PortPid $Port)) -eq $Expected) { return }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    throw "port $Port did not reach listening=$Expected"
}

function Update-PageVersion([string]$Path) {
    $content = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    $updated = [regex]::Replace(
        $content,
        'abc-furnace-rules-production\.js(?:\?v=[^"''<\s]+)?',
        "abc-furnace-rules-production.js?v=$version"
    )
    if (-not $updated.Contains("?v=$version")) { throw 'page version replacement failed' }
    Set-Content -LiteralPath "$Path.next" -Value $updated -Encoding UTF8 -NoNewline
    Move-Item -LiteralPath "$Path.next" -Destination $Path -Force
}

foreach ($path in $manager, $serviceConfig, $asset, $page8093, $page8094, $proxy, $stagedAsset) {
    if (-not (Test-Path -LiteralPath $path)) { throw "missing file: $path" }
}
$stagedHash = (Get-FileHash -LiteralPath $stagedAsset -Algorithm SHA256).Hash
if ($stagedHash -ne $expectedAssetHash) { throw 'staged asset hash mismatch' }
$stagedText = Get-Content -LiteralPath $stagedAsset -Raw -Encoding UTF8
foreach ($marker in '炉况形成原理', '五步干预处置流程', 'abc33-guidance') {
    if (-not $stagedText.Contains($marker)) { throw "staged asset missing marker: $marker" }
}

$before = [ordered]@{}
foreach ($port in 8093, 8094, 8768, 8770, 11434) {
    $before["p$port"] = Get-PortPid $port
    if (-not $before["p$port"]) { throw "missing protected listener: $port" }
}
$protectedHashes = [ordered]@{
    page8094 = (Get-FileHash -LiteralPath $page8094 -Algorithm SHA256).Hash
    proxy = (Get-FileHash -LiteralPath $proxy -Algorithm SHA256).Hash
}

New-Item -ItemType Directory -Path $backup -Force | Out-Null
Copy-Item -LiteralPath $asset -Destination (Join-Path $backup 'abc-furnace-rules-production.js') -Force
Copy-Item -LiteralPath $page8093 -Destination (Join-Path $backup 'frontend_dashboard_v3.server.html') -Force

$guardPaused = $false
$deploymentStarted = $false
$deploymentSucceeded = $false
try {
    & $manager -Action stop -ConfigPath $serviceConfig
    $guardPaused = $true
    Wait-Port 8093 $false 90
    $deploymentStarted = $true
    Copy-Item -LiteralPath $stagedAsset -Destination "$asset.next" -Force
    Move-Item -LiteralPath "$asset.next" -Destination $asset -Force
    Update-PageVersion $page8093
    $deploymentSucceeded = $true
} catch {
    if ($deploymentStarted) {
        Copy-Item -LiteralPath (Join-Path $backup 'abc-furnace-rules-production.js') -Destination $asset -Force
        Copy-Item -LiteralPath (Join-Path $backup 'frontend_dashboard_v3.server.html') -Destination $page8093 -Force
    }
    throw
} finally {
    & $manager -Action start -ConfigPath $serviceConfig
    Wait-Port 8093 $true 150
}

if (-not $deploymentSucceeded) { throw '8093 deployment did not complete' }
$after = [ordered]@{}
foreach ($port in 8093, 8094, 8768, 8770, 11434) {
    $after["p$port"] = Get-PortPid $port
}
foreach ($port in 8094, 8768, 8770, 11434) {
    if ($after["p$port"] -ne $before["p$port"]) { throw "protected PID changed: $port" }
}
if ($after.p8093 -eq $before.p8093) { throw '8093 listener PID did not change' }
if ((Get-Service -Name $service).Status -ne 'Running') { throw '8093 guard is not running' }
if ((Get-FileHash -LiteralPath $asset -Algorithm SHA256).Hash -ne $expectedAssetHash) {
    throw 'deployed asset hash mismatch'
}
if ((Get-FileHash -LiteralPath $page8094 -Algorithm SHA256).Hash -ne $protectedHashes.page8094) {
    throw '8094 page hash changed'
}
if ((Get-FileHash -LiteralPath $proxy -Algorithm SHA256).Hash -ne $protectedHashes.proxy) {
    throw '8093 proxy hash changed'
}

$page = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/?cb=$version#optimization" -TimeoutSec 45
$assetResponse = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/assets/abc-furnace-rules-production.js?v=$version" -TimeoutSec 45
if ($page.StatusCode -ne 200 -or -not $page.Content.Contains("?v=$version")) {
    throw '8093 page version verification failed'
}
if ($assetResponse.StatusCode -ne 200 -or -not $assetResponse.Content.Contains('五步干预处置流程')) {
    throw '8093 asset verification failed'
}

[ordered]@{
    ok = $true
    backup = $backup
    guard_paused = $guardPaused
    guard_restored = ((Get-Service -Name $service).Status -eq 'Running')
    before = $before
    after = $after
    http8093 = [int]$page.StatusCode
    page_version = $version
    asset_sha256 = (Get-FileHash -LiteralPath $asset -Algorithm SHA256).Hash
    page8093_sha256 = (Get-FileHash -LiteralPath $page8093 -Algorithm SHA256).Hash
    protected_hashes = $protectedHashes
}|ConvertTo-Json -Depth 7
