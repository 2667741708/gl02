$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$path = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\高炉前端数据\frontend_dashboard_v3.8094_preview.server.html"
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
    task = (Get-ScheduledTask -TaskPath "\BlastFurnaceServices\" -TaskName "V3AutoPreviewProxy8094").State.ToString()
    listeners = $listeners
} | ConvertTo-Json -Depth 4 -Compress
