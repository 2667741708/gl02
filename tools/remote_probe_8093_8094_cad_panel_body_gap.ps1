$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$html8093 = Join-Path $root "高炉前端数据\frontend_dashboard_v3.server.html"
$html8094 = Join-Path $root "高炉前端数据\frontend_dashboard_v3.8094_preview.server.html"
$revisionMarker = "BUG-BF3D-CAD-PANEL-BODY-GAP-20260804-R2"

function Get-ListenerPid {
    param([int]$Port)
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($listener) { return [int]$listener.OwningProcess }
    return $null
}

function Get-HttpProbe {
    param([int]$Port)
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/?cad_panel_gap_probe=$(Get-Date -Format yyyyMMddHHmmss)" -TimeoutSec 30
        return [ordered]@{
            status = [int]$response.StatusCode
            revision_marker = $response.Content.Contains($revisionMarker)
            panel_padding_zero = $response.Content.Contains("padding-bottom: 0 !important")
        }
    }
    catch {
        return [ordered]@{ status = 0; revision_marker = $false; panel_padding_zero = $false; error = $_.Exception.Message }
    }
}

$text8093 = Get-Content -LiteralPath $html8093 -Raw -Encoding UTF8
$text8094 = Get-Content -LiteralPath $html8094 -Raw -Encoding UTF8

[ordered]@{
    schema = "ops.cad-panel-body-gap.probe.v1"
    task8094 = (Get-ScheduledTask -TaskPath "\BlastFurnaceServices\" -TaskName "V3AutoPreviewProxy8094").State.ToString()
    service8093 = (Get-Service -Name "BFV4PreviewProxy8093").Status.ToString()
    service8768 = (Get-Service -Name "BFV4PreviewWs8768").Status.ToString()
    pid8093 = Get-ListenerPid -Port 8093
    pid8094 = Get-ListenerPid -Port 8094
    pid8768 = Get-ListenerPid -Port 8768
    pid8770 = Get-ListenerPid -Port 8770
    file8093 = [ordered]@{
        revision_marker = $text8093.Contains($revisionMarker)
        panel_padding_zero = $text8093.Contains("padding-bottom: 0 !important")
        sha256 = (Get-FileHash -LiteralPath $html8093 -Algorithm SHA256).Hash
    }
    file8094 = [ordered]@{
        revision_marker = $text8094.Contains($revisionMarker)
        panel_padding_zero = $text8094.Contains("padding-bottom: 0 !important")
        sha256 = (Get-FileHash -LiteralPath $html8094 -Algorithm SHA256).Hash
    }
    http8093 = Get-HttpProbe -Port 8093
    http8094 = Get-HttpProbe -Port 8094
} | ConvertTo-Json -Depth 6
