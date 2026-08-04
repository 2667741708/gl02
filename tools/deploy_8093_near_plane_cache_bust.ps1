$ErrorActionPreference = "Stop"

$projectRoot = (Get-Location).Path
$page = Join-Path $projectRoot "高炉前端数据\frontend_dashboard_v3.server.html"
$oldMarker = "assets/bf3d-surface-camera-guard-8093.js?v=20260801-8093-sync-r1"
$newMarker = "assets/bf3d-surface-camera-guard-8093.js?v=20260801-8093-near-plane-r4"
if (-not (Test-Path -LiteralPath $page)) {
    throw "8093 page not found: $page"
}

$utf8 = [System.Text.UTF8Encoding]::new($false)
$content = [System.IO.File]::ReadAllText($page, $utf8)
$oldCount = ([regex]::Matches($content, [regex]::Escape($oldMarker))).Count
$newCount = ([regex]::Matches($content, [regex]::Escape($newMarker))).Count
if ($oldCount -eq 1 -and $newCount -eq 0) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $backupRoot = Join-Path $projectRoot "backups\8093_near_plane_fix_20260801\$stamp"
    New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
    Copy-Item -LiteralPath $page -Destination (Join-Path $backupRoot "frontend_dashboard_v3.server.html.bak") -Force
    $content = $content.Replace($oldMarker, $newMarker)
    [System.IO.File]::WriteAllText($page, $content, $utf8)
} elseif ($oldCount -eq 0 -and $newCount -eq 1) {
    $backupRoot = $null
} else {
    throw "Unexpected 8093 camera cache markers: old=$oldCount new=$newCount"
}

$written = [System.IO.File]::ReadAllText($page, $utf8)
if (([regex]::Matches($written, [regex]::Escape($newMarker))).Count -ne 1) {
    throw "8093 camera cache marker verification failed"
}
$response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/?cache_probe=20260801_r4#overview" -TimeoutSec 3
if (-not $response.Content.Contains($newMarker)) {
    throw "8093 HTTP response does not contain the new camera cache marker"
}

[ordered]@{
    deployed = $true
    page_hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $page).Hash
    http_status = [int]$response.StatusCode
    marker = $newMarker
    backup = if ($backupRoot) { $backupRoot } else { "already-deployed" }
} | ConvertTo-Json -Depth 4
