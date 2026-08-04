$ErrorActionPreference = "Stop"

$assetRoot = Join-Path (Get-Location).Path "高炉前端数据\assets"
$entryPath = Join-Path $assetRoot "bf3d-surface-camera-guard-8093.js"
$sharedPath = Join-Path $assetRoot "bf3d-surface-camera-guard-8094.js"
$entry = Get-Content -LiteralPath $entryPath -Raw
$shared = Get-Content -LiteralPath $sharedPath -Raw
$entryResponse = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/assets/bf3d-surface-camera-guard-8093.js?probe=20260801_r4" -TimeoutSec 3
$sharedResponse = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/assets/bf3d-surface-camera-guard-8094.js?probe=20260801_r4" -TimeoutSec 3
$pagePath = Join-Path (Get-Location).Path "高炉前端数据\frontend_dashboard_v3.server.html"
$pageMarker = "assets/bf3d-surface-camera-guard-8093.js?v=20260801-8093-near-plane-r4"
$pageResponse = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/?probe=20260801_r4#overview" -TimeoutSec 3
$backupBase = Join-Path (Get-Location).Path "backups\8093_near_plane_fix_20260801"
$backupDirectories = Get-ChildItem -LiteralPath $backupBase -Directory -ErrorAction SilentlyContinue
$latestAssetBackup = $backupDirectories |
    Where-Object {
        (Test-Path -LiteralPath (Join-Path $_.FullName "bf3d-surface-camera-guard-8093.js")) -and
        (Test-Path -LiteralPath (Join-Path $_.FullName "bf3d-surface-camera-guard-8094.js"))
    } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
$latestPageBackup = $backupDirectories |
    Where-Object {
        Test-Path -LiteralPath (Join-Path $_.FullName "frontend_dashboard_v3.server.html.bak")
    } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

$result = [ordered]@{
    entry_hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $entryPath).Hash
    shared_hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $sharedPath).Hash
    entry_marker_on_disk = $entry.Contains("20260801-8093-near-plane-r4")
    shared_marker_on_disk = $shared.Contains('PORT_SCOPE === "8093" ? 0.05 : null')
    entry_http_status = [int]$entryResponse.StatusCode
    shared_http_status = [int]$sharedResponse.StatusCode
    entry_marker_served = $entryResponse.Content.Contains("20260801-8093-near-plane-r4")
    shared_marker_served = $sharedResponse.Content.Contains('PORT_SCOPE === "8093" ? 0.05 : null')
    page_hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $pagePath).Hash
    page_marker_served = $pageResponse.Content.Contains($pageMarker)
    latest_asset_backup = if ($latestAssetBackup) { $latestAssetBackup.FullName } else { $null }
    latest_asset_backup_file_count = if ($latestAssetBackup) {
        (Get-ChildItem -LiteralPath $latestAssetBackup.FullName -File).Count
    } else {
        0
    }
    latest_page_backup = if ($latestPageBackup) { $latestPageBackup.FullName } else { $null }
}

if (-not $result.entry_marker_on_disk -or -not $result.shared_marker_on_disk) {
    throw "8093 near-plane files are not deployed on disk"
}
if (-not $result.entry_marker_served -or -not $result.shared_marker_served) {
    throw "8093 server is not serving the deployed near-plane files"
}
if (-not $result.page_marker_served) {
    throw "8093 page is not serving the new camera cache marker"
}
if (-not $result.latest_asset_backup -or $result.latest_asset_backup_file_count -ne 2) {
    throw "8093 near-plane rollback backup is incomplete"
}
if (-not $result.latest_page_backup) {
    throw "8093 near-plane page cache rollback backup is missing"
}

$result | ConvertTo-Json -Depth 3
