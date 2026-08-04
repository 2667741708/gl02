$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$path = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\高炉前端数据\frontend_dashboard_v3.8094_preview.server.html"
$text = Get-Content -LiteralPath $path -Raw -Encoding UTF8
[ordered]@{
    Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash
    Length = (Get-Item -LiteralPath $path).Length
    LastWrite = (Get-Item -LiteralPath $path).LastWriteTime.ToString("s")
    LoadsHeatLink = $text.Contains("bf-heat-dashboard-link.js")
    HasFiveNav = $text.Contains("const NAVS = [['overview', '总览', '▣'], ['diagnosis', '炉况诊断', '◴'], ['optimization', '参数优化建议', '☷'], ['trend', '趋势分析', '▟'], ['qa', '智能问答/知识助手', '☻']]")
    HasBillboard = $text.Contains("bf3d-furnace-body-billboard-adapter.js?v=20260726-pspace-live-r3")
    HasInternalSimulation = $text.Contains("bf3d-internal-simulation.js")
    HasLayerControls = $text.Contains("gl02-layered-cad-controls-v1")
} | ConvertTo-Json -Compress
