$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$frontend = Join-Path $root "高炉前端数据"
$backend = Join-Path $frontend "智能助手\backend"
$ports = 8093,8094,8768,8769,8770,11434
$listeners = foreach ($port in $ports) {
    $item = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    [ordered]@{ port = $port; pid = if ($item) { [int]$item.OwningProcess } else { $null } }
}
$task8094 = Get-ScheduledTask -TaskPath "\BlastFurnaceServices\" -TaskName "V3AutoPreviewProxy8094" -ErrorAction SilentlyContinue
$task8769 = Get-ScheduledTask -TaskPath "\BlastFurnaceServices\" -TaskName "V4PreviewWs8769" -ErrorAction SilentlyContinue
[ordered]@{
    listeners = $listeners
    task8094 = if ($task8094) { [string]$task8094.State } else { $null }
    task8769 = if ($task8769) { [string]$task8769.State } else { $null }
    htmlMarker = (Get-Content -LiteralPath (Join-Path $frontend "frontend_dashboard_v3.8094_preview.server.html") -Raw -Encoding UTF8).Contains("OPS-8094-MULTI-CONDITION-REVIEW-20260805")
    isolatedProxy = Test-Path -LiteralPath (Join-Path $backend "ollama_proxy_server_8094.py") -PathType Leaf
    restartScript = Test-Path -LiteralPath (Join-Path $root "tools\restart_22012_8094_preview.ps1") -PathType Leaf
    wsRunner = Test-Path -LiteralPath (Join-Path $root "tools\run_22012_8094_ws8769.ps1") -PathType Leaf
} | ConvertTo-Json -Depth 5
