$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$stage = 'C:\Users\Administrator\AppData\Local\Temp\abc33_action_first_basis_toggle'
$service8093 = 'BFV4PreviewProxy8093'
$asset = Join-Path $root '高炉前端数据\assets\abc-furnace-rules-production.js'
$page8093 = Join-Path $root '高炉前端数据\frontend_dashboard_v3.server.html'
$page8094 = Join-Path $root '高炉前端数据\frontend_dashboard_v3.8094_preview.server.html'
$stagedAsset = Join-Path $stage 'abc-furnace-rules-production.js'
$version = 'abc33-20260810-action-first-basis-toggle-r1'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backup = Join-Path $root "backups\abc33_action_first_basis_toggle_$stamp"

function Get-PortPid([int]$port) {
    $item = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($item) { return [int]$item.OwningProcess }
    return $null
}

function Wait-Port([int]$port, [bool]$expected, [int]$seconds) {
    $deadline = (Get-Date).AddSeconds($seconds)
    do {
        if (($null -ne (Get-PortPid $port)) -eq $expected) { return }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    throw "port $port did not reach listening=$expected"
}

function Update-8093PageVersion([string]$path) {
    $content = Get-Content -LiteralPath $path -Raw -Encoding UTF8
    $updated = [regex]::Replace(
        $content,
        'abc-furnace-rules-production\.js(?:\?v=[^"''<\s]+)?',
        "abc-furnace-rules-production.js?v=$version"
    )
    if (-not $updated.Contains("?v=$version")) {
        throw '8093 ABC33 asset version replacement failed'
    }
    Set-Content -LiteralPath "$path.next" -Value $updated -Encoding UTF8 -NoNewline
    Move-Item -LiteralPath "$path.next" -Destination $path -Force
}

$before = @{
    p8093 = Get-PortPid 8093
    p8094 = Get-PortPid 8094
    p8768 = Get-PortPid 8768
    p8770 = Get-PortPid 8770
    p11434 = Get-PortPid 11434
}
foreach ($name in 'p8093', 'p8094', 'p8768', 'p8770', 'p11434') {
    if (-not $before[$name]) { throw "missing protected listener: $name" }
}
foreach ($path in $asset, $page8093, $page8094, $stagedAsset) {
    if (-not (Test-Path -LiteralPath $path)) { throw "missing file: $path" }
}
if ((Get-Service -Name $service8093).Status -ne 'Running') {
    throw "$service8093 is not running before deployment"
}

$stagedContent = Get-Content -LiteralPath $stagedAsset -Raw -Encoding UTF8
foreach ($marker in "window.location.port!=='8093'", 'operator-first', 'abc33-basis-toggle', 'abc33-basis-content', 'operationPrinciple') {
    if (-not $stagedContent.Contains($marker)) { throw "staged asset missing marker: $marker" }
}

$page8094HashBefore = (Get-FileHash -LiteralPath $page8094 -Algorithm SHA256).Hash
New-Item -ItemType Directory -Path $backup -Force | Out-Null
Copy-Item -LiteralPath $asset -Destination (Join-Path $backup 'abc-furnace-rules-production.js') -Force
Copy-Item -LiteralPath $page8093 -Destination (Join-Path $backup 'frontend_dashboard_v3.server.html') -Force

$changed = $false
try {
    Stop-Service -Name $service8093 -Force
    Wait-Port 8093 $false 60
    $changed = $true

    Copy-Item -LiteralPath $stagedAsset -Destination "$asset.next" -Force
    Move-Item -LiteralPath "$asset.next" -Destination $asset -Force
    Update-8093PageVersion $page8093
} catch {
    if ($changed) {
        Copy-Item -LiteralPath (Join-Path $backup 'abc-furnace-rules-production.js') -Destination $asset -Force
        Copy-Item -LiteralPath (Join-Path $backup 'frontend_dashboard_v3.server.html') -Destination $page8093 -Force
    }
    throw
} finally {
    Start-Service -Name $service8093 -ErrorAction SilentlyContinue
    Wait-Port 8093 $true 120
}

$after = @{
    p8093 = Get-PortPid 8093
    p8094 = Get-PortPid 8094
    p8768 = Get-PortPid 8768
    p8770 = Get-PortPid 8770
    p11434 = Get-PortPid 11434
}
foreach ($name in 'p8094', 'p8768', 'p8770', 'p11434') {
    if ($after[$name] -ne $before[$name]) { throw "protected PID changed: $name" }
}

$page = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/?cb=$version#optimization" -TimeoutSec 30
$assetResponse = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/assets/abc-furnace-rules-production.js?v=$version" -TimeoutSec 30
$detail = Invoke-RestMethod -Uri 'http://127.0.0.1:8093/api/furnace-rules/B4/detail' -TimeoutSec 60
$page8094HashAfter = (Get-FileHash -LiteralPath $page8094 -Algorithm SHA256).Hash
if ($page.StatusCode -ne 200 -or -not $page.Content.Contains("?v=$version")) {
    throw '8093 page version verification failed'
}
foreach ($marker in 'operator-first', 'abc33-basis-toggle', 'abc33-basis-content') {
    if (-not $assetResponse.Content.Contains($marker)) { throw "8093 asset verification failed: $marker" }
}
if (-not $detail.detail.principle -or [int]$detail.detail.intervention_order.Count -ne 5) {
    throw '8093 B4 detail guidance contract verification failed'
}
if ($page8094HashAfter -ne $page8094HashBefore) {
    throw '8094 page changed unexpectedly'
}

[ordered]@{
    ok = $true
    backup = $backup
    guard_paused = $true
    guard_restored = ((Get-Service -Name $service8093).Status -eq 'Running')
    before = $before
    after = $after
    page_version = $version
    http8093 = [int]$page.StatusCode
    detail_rule = $detail.detail.rule_id
    detail_steps = [int]$detail.detail.intervention_order.Count
    page8094_unchanged = $true
    asset_sha256 = (Get-FileHash -LiteralPath $asset -Algorithm SHA256).Hash
    page8093_sha256 = (Get-FileHash -LiteralPath $page8093 -Algorithm SHA256).Hash
} | ConvertTo-Json -Depth 6
