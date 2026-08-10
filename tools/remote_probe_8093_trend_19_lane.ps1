$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$path = Join-Path $root "高炉前端数据\frontend_dashboard_v3.server.html"
$content = Get-Content -LiteralPath $path -Raw -Encoding UTF8
$listeners = [ordered]@{}
foreach ($port in 8093,8094,8768,8770,11434) {
    $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    $listeners[[string]$port] = if ($listener) { [int]$listener.OwningProcess } else { $null }
}
[ordered]@{
    hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash
    marker = $content.Contains("REQ-TREND-19-LANE-MERGE-20260807")
    title = $content.Contains("19个核心变量趋势与预测")
    service8093 = (Get-Service -Name "BFV4PreviewProxy8093").Status.ToString()
    service8768 = (Get-Service -Name "BFV4PreviewWs8768").Status.ToString()
    task8094 = (Get-ScheduledTask -TaskPath "\BlastFurnaceServices\" -TaskName "V3AutoPreviewProxy8094").State.ToString()
    listeners = $listeners
} | ConvertTo-Json -Depth 4 -Compress
