$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$v4Root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$frontend = Join-Path $v4Root "高炉前端数据"
$stageRoot = Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "Temp\bf_heat_dashboard_link"
$stageHtml = Join-Path $stageRoot "frontend_dashboard_v3.8094.preview.patched.html"
$stageAsset = Join-Path $stageRoot "bf-heat-dashboard-link.js"
$targetHtml = Join-Path $frontend "frontend_dashboard_v3.8094_preview.server.html"
$targetAsset = Join-Path $frontend "assets\bf-heat-dashboard-link.js"
$expectedBeforeHash = "04E93D22E9B2650721265DDBB376FE81A9E39B3851BB5FC672BF72DB5A9B6CBB"
$taskPath = "\BlastFurnaceServices\"
$taskName = "V3AutoPreviewProxy8094"

foreach ($path in @($stageHtml, $stageAsset, $targetHtml)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Required path is missing: $path"
    }
}

$beforeHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $targetHtml).Hash
if ($beforeHash -ne $expectedBeforeHash) {
    throw "8094 HTML changed after staging. Expected $expectedBeforeHash, got $beforeHash"
}

$stageHtmlText = Get-Content -LiteralPath $stageHtml -Raw -Encoding UTF8
$stageAssetText = Get-Content -LiteralPath $stageAsset -Raw -Encoding UTF8
foreach ($marker in @(
    "topbar branded-topbar",
    "bf3d-furnace-body-billboard-adapter.js?v=20260726-pspace-live-r3",
    "bf3d-internal-simulation.js",
    "bf-heat-dashboard-link.js?v=20260726-r1",
    'data-url="http://127.0.0.1:8890/heat"',
    '<link rel="icon" href="data:,">'
)) {
    if (-not $stageHtmlText.Contains($marker)) {
        throw "Staged 8094 HTML marker is missing: $marker"
    }
}
foreach ($marker in @(
    "REQ-8094-HEAT-DASHBOARD-LINK-20260726",
    "heat-dashboard-link",
    "http://127.0.0.1:8890/heat",
    "noopener noreferrer"
)) {
    if (-not $stageAssetText.Contains($marker)) {
        throw "Staged heat-dashboard asset marker is missing: $marker"
    }
}

$task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
$listener8094 = Get-NetTCPConnection -LocalPort 8094 -State Listen -ErrorAction Stop |
    Select-Object -First 1
$listener8093 = Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction Stop |
    Select-Object -First 1
$listener8768 = Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction Stop |
    Select-Object -First 1
if ($task.State -ne "Running" -or -not $listener8094 -or -not $listener8093 -or -not $listener8768) {
    throw "8094/8093/8768 preflight is not healthy"
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $v4Root "backups\8094_heat_dashboard_link_$stamp"
New-Item -ItemType Directory -Path $backup -Force | Out-Null
Copy-Item -LiteralPath $targetHtml -Destination (Join-Path $backup "frontend_dashboard_v3.8094_preview.server.html") -Force
$assetExisted = Test-Path -LiteralPath $targetAsset
if ($assetExisted) {
    Copy-Item -LiteralPath $targetAsset -Destination (Join-Path $backup "bf-heat-dashboard-link.js") -Force
}
@{
    requirement = "REQ-8094-HEAT-DASHBOARD-LINK-20260726"
    target_html = $targetHtml
    target_asset = $targetAsset
    before_hash = $beforeHash
    asset_existed = $assetExisted
    created_at = (Get-Date).ToString("s")
} | ConvertTo-Json -Depth 4 |
    Set-Content -LiteralPath (Join-Path $backup "deployment_metadata.json") -Encoding UTF8

try {
    Copy-Item -LiteralPath $stageAsset -Destination $targetAsset -Force
    Copy-Item -LiteralPath $stageHtml -Destination $targetHtml -Force

    $cacheBust = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $pageResponse = Invoke-WebRequest -UseBasicParsing -TimeoutSec 60 `
        -Uri "http://127.0.0.1:8094/?heat_link=$cacheBust#overview"
    $assetResponse = Invoke-WebRequest -UseBasicParsing -TimeoutSec 60 `
        -Uri "http://127.0.0.1:8094/assets/bf-heat-dashboard-link.js?v=20260726-r1-$cacheBust"
    if ($pageResponse.StatusCode -ne 200 -or
        -not $pageResponse.Content.Contains("bf-heat-dashboard-link.js?v=20260726-r1")) {
        throw "8094 HTML HTTP verification failed"
    }
    if ($assetResponse.StatusCode -ne 200 -or
        -not $assetResponse.Content.Contains("REQ-8094-HEAT-DASHBOARD-LINK-20260726")) {
        throw "8094 heat-dashboard asset HTTP verification failed"
    }

    $taskAfter = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
    $portsAfter = [ordered]@{}
    foreach ($port in 8093, 8094, 8768) {
        $portsAfter[[string]$port] = [bool](
            Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
                Select-Object -First 1
        )
    }
    if ($taskAfter.State -ne "Running" -or $portsAfter.Values -contains $false) {
        throw "Service or port health changed after deployment"
    }

    [ordered]@{
        ok = $true
        requirement = "REQ-8094-HEAT-DASHBOARD-LINK-20260726"
        backup = $backup
        before_hash = $beforeHash
        after_hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $targetHtml).Hash
        asset_hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $targetAsset).Hash
        task8094 = $taskAfter.State.ToString()
        ports = $portsAfter
        page_http = $pageResponse.StatusCode
        asset_http = $assetResponse.StatusCode
        restart_performed = $false
    } | ConvertTo-Json -Depth 5
}
catch {
    Copy-Item -LiteralPath (Join-Path $backup "frontend_dashboard_v3.8094_preview.server.html") `
        -Destination $targetHtml -Force
    if ($assetExisted) {
        Copy-Item -LiteralPath (Join-Path $backup "bf-heat-dashboard-link.js") `
            -Destination $targetAsset -Force
    }
    elseif (Test-Path -LiteralPath $targetAsset) {
        Remove-Item -LiteralPath $targetAsset -Force
    }
    throw
}
