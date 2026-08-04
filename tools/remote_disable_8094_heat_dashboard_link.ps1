$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$v4Root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$frontend = Join-Path $v4Root "高炉前端数据"
$targetHtml = Join-Path $frontend "frontend_dashboard_v3.8094_preview.server.html"
$retainedAsset = Join-Path $frontend "assets\bf-heat-dashboard-link.js"
$stageRoot = Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "Temp\bf_heat_dashboard_link"
$stageHtml = Join-Path $stageRoot "frontend_dashboard_v3.8094.disabled.latest.html"
$expectedCurrentHash = "47A274C22D04C8D6EDE9546BE76CB196969F3056749FFA9E9A71593D3757DD74"
$taskPath = "\BlastFurnaceServices\"
$taskName = "V3AutoPreviewProxy8094"

foreach ($path in @($targetHtml, $stageHtml, $retainedAsset)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Required rollback path is missing: $path"
    }
}

$currentHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $targetHtml).Hash
if ($currentHash -ne $expectedCurrentHash) {
    throw "8094 HTML changed after latest staging. Expected $expectedCurrentHash, got $currentHash"
}
$stageText = Get-Content -LiteralPath $stageHtml -Raw -Encoding UTF8
if ($stageText.Contains("bf-heat-dashboard-link.js")) {
    throw "Staged HTML still loads the heat-dashboard link"
}
foreach ($marker in @(
    "const NAVS = [['overview', '总览', '▣'], ['diagnosis', '炉况诊断', '◴'], ['optimization', '参数优化建议', '☷'], ['trend', '趋势分析', '▟'], ['qa', '智能问答/知识助手', '☻']]",
    "bf3d-furnace-body-billboard-adapter.js?v=20260726-viewport-fit-r4",
    "bf3d-internal-simulation.js",
    "topbar branded-topbar"
)) {
    if (-not $stageText.Contains($marker)) {
        throw "Latest staged HTML marker is missing: $marker"
    }
}

$task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName -ErrorAction Stop
$portsBefore = [ordered]@{}
foreach ($port in 8093, 8094, 8768) {
    $portsBefore[[string]$port] = [bool](
        Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -First 1
    )
}
if ($task.State -ne "Running" -or $portsBefore.Values -contains $false) {
    throw "8094/8093/8768 preflight is not healthy"
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$disableBackup = Join-Path $v4Root "backups\8094_heat_dashboard_link_disabled_$stamp"
New-Item -ItemType Directory -Path $disableBackup -Force | Out-Null
Copy-Item -LiteralPath $targetHtml -Destination (Join-Path $disableBackup "enabled_8094.html") -Force
Copy-Item -LiteralPath $retainedAsset -Destination (Join-Path $disableBackup "bf-heat-dashboard-link.js") -Force

try {
    Copy-Item -LiteralPath $stageHtml -Destination $targetHtml -Force
    $cacheBust = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $pageResponse = Invoke-WebRequest -UseBasicParsing -TimeoutSec 60 `
        -Uri "http://127.0.0.1:8094/?heat_link_disabled=$cacheBust#overview"
    if ($pageResponse.StatusCode -ne 200) {
        throw "8094 HTTP verification failed"
    }
    if ($pageResponse.Content.Contains("bf-heat-dashboard-link.js")) {
        throw "8094 still loads the disabled heat-dashboard link"
    }
    if (-not $pageResponse.Content.Contains(
        "const NAVS = [['overview', '总览', '▣'], ['diagnosis', '炉况诊断', '◴'], ['optimization', '参数优化建议', '☷'], ['trend', '趋势分析', '▟'], ['qa', '智能问答/知识助手', '☻']]"
    )) {
        throw "8094 five-page navigation contract is missing"
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
        throw "Service or port health changed after disabling the link"
    }

    [ordered]@{
        ok = $true
        requirement = "REQ-8094-HEAT-DASHBOARD-LINK-20260726-DISABLED"
        previous_enabled_backup = $disableBackup
        restored_from = $stageHtml
        restored_hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $targetHtml).Hash
        retained_asset = $retainedAsset
        retained_asset_hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $retainedAsset).Hash
        task8094 = $taskAfter.State.ToString()
        ports = $portsAfter
        page_http = $pageResponse.StatusCode
        restart_performed = $false
    } | ConvertTo-Json -Depth 5
}
catch {
    Copy-Item -LiteralPath (Join-Path $disableBackup "enabled_8094.html") `
        -Destination $targetHtml -Force
    throw
}
