$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$taskPath = "\BlastFurnaceServices\"
$taskName = "StandaloneHeatDashboard8891"
$base = "http://127.0.0.1:8891"

function Get-Json($uri) {
    $response = Invoke-WebRequest -UseBasicParsing -Uri $uri -TimeoutSec 60
    return [ordered]@{
        status = $response.StatusCode
        body = ($response.Content | ConvertFrom-Json)
    }
}

$root = Invoke-WebRequest -UseBasicParsing -Uri "$base/" -TimeoutSec 10
$heat = Invoke-WebRequest -UseBasicParsing -Uri "$base/heat" -TimeoutSec 10
$overview = Get-Json "$base/api/overview"
$heats = Get-Json "$base/api/heats?limit=3&furnace=2"
$heatBody = $heats.body
$detail = $null
if ($heatBody.summary.latest_meltno) {
    $detail = Get-Json ("$base/api/heat-detail?meltno=" + [uri]::EscapeDataString([string]$heatBody.summary.latest_meltno) + "&window=pre_tap&group=core")
}
$page8094 = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8094/" -TimeoutSec 12

[ordered]@{
    task = Get-ScheduledTask -TaskPath $taskPath -TaskName $taskName | Select-Object TaskName,State,TaskPath
    listener = @(Get-NetTCPConnection -State Listen -LocalPort 8891 | Select-Object LocalAddress,LocalPort,OwningProcess)
    root_http_status = $root.StatusCode
    root_has_dashboard_title = $root.Content -match "GL02 数据库仪表盘"
    heat_http_status = $heat.StatusCode
    heat_has_heat_title = $heat.Content -match "GL02 炉次质量与传感器分析"
    overview_http_status = $overview.status
    overview_ok = $overview.body.ok
    overview_sensor_tags = $overview.body.sensor.tags
    overview_sensor_rows = $overview.body.sensor.rows
    heats_http_status = $heats.status
    heats_ok = $heatBody.ok
    heats_count = @($heatBody.heats).Count
    summary = $heatBody.summary
    latest_meltno = $heatBody.summary.latest_meltno
    sources = $heatBody.sources
    detail_http_status = if ($detail) { $detail.status } else { $null }
    detail_ok = if ($detail) { $detail.body.ok } else { $null }
    detail_meltno = if ($detail) { $detail.body.heat.meltno } else { $null }
    detail_sensor_point_count = if ($detail) { $detail.body.sensor_window.point_count } else { $null }
    detail_diagnosis_count = if ($detail) { $detail.body.diagnosis.count } else { $null }
    page8094_http_status = $page8094.StatusCode
    page8094_heat_link_present = $page8094.Content -match "bf-heat-dashboard-link\.js|炉次分析"
    protected_listeners = @(Get-NetTCPConnection -State Listen -LocalPort 8093,8094,8768,8770 | Select-Object LocalAddress,LocalPort,OwningProcess)
    first_heat = if (@($heatBody.heats).Count -gt 0) {
        $heatBody.heats[0] | Select-Object meltno,open_ts,close_ts,hot_metal_sample_count,slag_sample_count,alignment_status,hot_metal_si_summary
    } else { $null }
} | ConvertTo-Json -Depth 12
