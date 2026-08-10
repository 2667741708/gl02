$ErrorActionPreference = "Stop"

function Get-ListenerPid {
    param([int]$Port)
    $row = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $row) { return $null }
    return [int]$row.OwningProcess
}

function Find-LiveFile {
    param([string]$Filter)
    $matches = @(
        Get-ChildItem -LiteralPath (Get-Location).Path -Recurse -File -Filter $Filter -ErrorAction Stop |
            Where-Object { $_.FullName -notmatch "\\backups\\|\\logs\\|\\.tmp|\\.codex_stage\\" }
    )
    if ($matches.Count -ne 1) {
        throw "Expected exactly one live $Filter, found $($matches.Count)"
    }
    return $matches[0].FullName
}

$services = Get-Service -Name "BFV4PreviewProxy8093", "BFV4PreviewWs8768" |
    Select-Object Name, @{Name = "Status"; Expression = { $_.Status.ToString() } }
$pageResponse = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/frontend_dashboard_v3.server.html?audit=20260804" -TimeoutSec 10
$assetResponse = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/assets/bf-core-metrics-pspace-live-8093.js?audit=20260804" -TimeoutSec 10
$html8093 = Find-LiveFile -Filter "frontend_dashboard_v3.server.html"
$html8094 = Find-LiveFile -Filter "frontend_dashboard_v3.8094_preview.server.html"
$sharedAdapter = Find-LiveFile -Filter "bf3d-furnace-body-billboard-adapter.js"
$camera8094 = Find-LiveFile -Filter "bf3d-surface-camera-guard-8094.js"
$asset8093 = Find-LiveFile -Filter "bf-core-metrics-pspace-live-8093.js"
$backupRoot = Join-Path (Get-Location).Path "backups\8093_core_metrics_pspace_live_20260804"
$latestBackup = Get-ChildItem -LiteralPath $backupRoot -Directory -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

[pscustomobject]@{
    services = @($services)
    listeners = [ordered]@{
        p8093 = Get-ListenerPid -Port 8093
        p8094 = Get-ListenerPid -Port 8094
        p8768 = Get-ListenerPid -Port 8768
        p8770 = Get-ListenerPid -Port 8770
    }
    http_8093 = [int]$pageResponse.StatusCode
    page_marker = [bool]($pageResponse.Content -match "REQ-8093-CORE-PSPACE-REALTIME-20260804")
    history_merge_marker = [bool]($pageResponse.Content -match "BF_HISTORY_MERGE_TIMESTAMP_PRIMARY_WINS_8093")
    asset_http_8093 = [int]$assetResponse.StatusCode
    asset_schema = [bool]($assetResponse.Content -match "bf.core-metrics.pspace-live.8093.v1")
    hashes = [ordered]@{
        html_8093 = (Get-FileHash -LiteralPath $html8093 -Algorithm SHA256).Hash
        asset_8093 = (Get-FileHash -LiteralPath $asset8093 -Algorithm SHA256).Hash
        html_8094 = (Get-FileHash -LiteralPath $html8094 -Algorithm SHA256).Hash
        shared_adapter = (Get-FileHash -LiteralPath $sharedAdapter -Algorithm SHA256).Hash
        camera_8094 = (Get-FileHash -LiteralPath $camera8094 -Algorithm SHA256).Hash
    }
    latest_backup = if ($null -eq $latestBackup) { $null } else { $latestBackup.FullName }
} | ConvertTo-Json -Depth 6 -Compress
