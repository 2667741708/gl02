$ErrorActionPreference = "Stop"
$frontend = if ($env:BF_FRONTEND_DIR) {
    $env:BF_FRONTEND_DIR
} else {
    "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\高炉前端数据"
}
$page = Join-Path $frontend "frontend_dashboard_v3.8094_preview.server.html"
$model = Join-Path $frontend "models\gl02_blast_furnace.glb"
$manifestPath = Join-Path $frontend "models\gl02_furnace_body_billboards.v1.json"
$html = Get-Content -LiteralPath $page -Raw -Encoding UTF8
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
$task = Get-ScheduledTask -TaskPath "\BlastFurnaceServices\" -TaskName "V3AutoPreviewProxy8094"
$listeners = @(Get-NetTCPConnection -LocalPort 8094 -State Listen -ErrorAction SilentlyContinue)
$result = [ordered]@{
    task_state = $task.State
    listener_pids = @($listeners | ForEach-Object OwningProcess)
    html_cache_bust = $html.Contains("bf3d-furnace-body-billboard-adapter.js?v=20260725-r2")
    html_viewer_contract = $html.Contains("getBuffer: () => bufRef.current")
    html_flow_runtime = $html.Contains("assets/bf3d-internal-simulation.js")
    manifest_schema = $manifest.schema
    manifest_formal_count = $manifest.counts.formal_sensor_115
    manifest_static_pressure_count = $manifest.counts.static_pressure_18
    manifest_total = $manifest.counts.total
    model_sha256 = (Get-FileHash -LiteralPath $model -Algorithm SHA256).Hash
    page_sha256 = (Get-FileHash -LiteralPath $page -Algorithm SHA256).Hash
}
$result | ConvertTo-Json -Compress
