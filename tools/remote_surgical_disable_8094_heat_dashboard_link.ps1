$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$v4Root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$frontend = Join-Path $v4Root "高炉前端数据"
$targetHtml = Join-Path $frontend "frontend_dashboard_v3.8094_preview.server.html"
$retainedAsset = Join-Path $frontend "assets\bf-heat-dashboard-link.js"
$taskPath = "\BlastFurnaceServices\"
$taskName = "V3AutoPreviewProxy8094"
$pattern = '(?ms)\r?\n[ \t]*<script src="assets/bf-heat-dashboard-link\.js\?v=20260726-r1"[ \t]*\r?\n[ \t]*data-url="http://127\.0\.0\.1:8890/heat"></script>'

foreach ($path in @($targetHtml, $retainedAsset)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Required path is missing: $path"
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
$backupDir = Join-Path $v4Root "backups\8094_heat_dashboard_link_surgical_disable_$stamp"
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
$replaceBackup = Join-Path $backupDir "before_disable.html"
$tempHtml = Join-Path $frontend "frontend_dashboard_v3.8094_preview.server.html.heat_link_disable.tmp"

$beforeHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $targetHtml).Hash
$text = Get-Content -LiteralPath $targetHtml -Raw -Encoding UTF8
$alreadyDisabled = -not $text.Contains("bf-heat-dashboard-link.js")
if (-not $alreadyDisabled) {
    $matches = [regex]::Matches($text, $pattern)
    if ($matches.Count -ne 1) {
        throw "Expected exactly one heat-dashboard script tag, found $($matches.Count)"
    }
    $patched = [regex]::Replace($text, $pattern, "", 1)
    foreach ($marker in @(
        "const NAVS = [['overview', '总览', '▣'], ['diagnosis', '炉况诊断', '◴'], ['optimization', '参数优化建议', '☷'], ['trend', '趋势分析', '▟'], ['qa', '智能问答/知识助手', '☻']]",
        "topbar branded-topbar"
    )) {
        if (-not $patched.Contains($marker)) {
            throw "Five-page staged marker is missing: $marker"
        }
    }
    [IO.File]::WriteAllText(
        $tempHtml,
        $patched,
        [Text.UTF8Encoding]::new($false)
    )
    [IO.File]::Replace($tempHtml, $targetHtml, $replaceBackup, $true)
}
else {
    Copy-Item -LiteralPath $targetHtml -Destination $replaceBackup -Force
}

$cacheBust = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
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
    mode = "surgical_current_file_patch"
    already_disabled = $alreadyDisabled
    backup = $replaceBackup
    before_hash = $beforeHash
    after_hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $targetHtml).Hash
    retained_asset = $retainedAsset
    retained_asset_hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $retainedAsset).Hash
    task8094 = $taskAfter.State.ToString()
    ports = $portsAfter
    page_http = $pageResponse.StatusCode
    restart_performed = $false
} | ConvertTo-Json -Depth 5
