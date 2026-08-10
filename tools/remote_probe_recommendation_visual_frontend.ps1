$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String("Rjpc6auY54KJ54K86ZOB6aG555uuLXJlYWwtc2Vuc29yLXYyX1Y0XzgwOTNfUFJFVklFVw=="))
$frontendName = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String("6auY54KJ5YmN56uv5pWw5o2u"))
$frontend = Join-Path $root $frontendName
$page8093 = Join-Path $frontend "frontend_dashboard_v3.server.html"
$page8094 = Join-Path $frontend "frontend_dashboard_v3.8094_preview.server.html"

function Get-ListenerPid([int]$Port) {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) { return [int]$listener.OwningProcess }
    return $null
}

function Get-PageState([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    $text = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    return [ordered]@{
        sha256 = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
        visualMarker = $text.Contains("REQ-OPT-VISUAL-COCKPIT-RESTORE-20260806")
        visualAssignment = $text.Contains("OptimizationTab = OptimizationVisualWorkbenchLayout;")
        shared8768 = $text.Contains("get('ws_port') || '8768'")
    }
}

$http8093 = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/?visual_probe=1" -TimeoutSec 15
$http8094 = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8094/?visual_probe=1" -TimeoutSec 15
[ordered]@{
    pid8093 = Get-ListenerPid 8093
    pid8094 = Get-ListenerPid 8094
    pid8768 = Get-ListenerPid 8768
    pid8770 = Get-ListenerPid 8770
    pid11434 = Get-ListenerPid 11434
    service8093 = [string](Get-Service -Name "BFV4PreviewProxy8093" -ErrorAction SilentlyContinue).Status
    service8768 = [string](Get-Service -Name "BFV4PreviewWs8768" -ErrorAction SilentlyContinue).Status
    http8093 = [int]$http8093.StatusCode
    http8094 = [int]$http8094.StatusCode
    page8093 = Get-PageState $page8093
    page8094 = Get-PageState $page8094
} | ConvertTo-Json -Depth 5
