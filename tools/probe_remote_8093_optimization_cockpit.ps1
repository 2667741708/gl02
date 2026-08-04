$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$htmlPath = Join-Path $root '高炉前端数据\frontend_dashboard_v3.server.html'
$service = Get-Service -Name 'BFV4PreviewProxy8093'
$html = Get-Content -LiteralPath $htmlPath -Raw -Encoding UTF8

[pscustomobject]@{
    service_status = [string]$service.Status
    port_8093_listening = [bool](Get-NetTCPConnection -State Listen -LocalPort 8093 -ErrorAction SilentlyContinue)
    port_8768_listening = [bool](Get-NetTCPConnection -State Listen -LocalPort 8768 -ErrorAction SilentlyContinue)
    html_exists = Test-Path -LiteralPath $htmlPath -PathType Leaf
    html_sha256 = (Get-FileHash -LiteralPath $htmlPath -Algorithm SHA256).Hash
    has_cockpit = $html.Contains('OptimizationCockpitLayout')
    has_legacy_v10 = $html.Contains('BFOptimizationWorkbenchV10')
    has_header = $html.Contains('topbar branded-topbar')
} | ConvertTo-Json -Compress
