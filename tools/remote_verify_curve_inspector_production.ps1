$ErrorActionPreference = 'Stop'
$urls = [ordered]@{
  '8093' = 'http://127.0.0.1:8093/foreman_trend_preview.html?curve_verify=20260811'
  '8094' = 'http://127.0.0.1:8094/?curve_verify=20260811'
  '8095' = 'http://127.0.0.1:8095/?curve_verify=20260811'
  '8096' = 'http://127.0.0.1:8096/?curve_verify=20260811'
  '8892' = 'http://127.0.0.1:8892/?curve_verify=20260811'
}
$pages = [ordered]@{}
foreach ($key in $urls.Keys) {
  $response = Invoke-WebRequest -UseBasicParsing -Uri $urls[$key] -TimeoutSec 15
  $body = $response.Content
  $pages[$key] = [ordered]@{
    status = [int]$response.StatusCode
    bytes = $body.Length
    helper = $body.Contains('curve-inspector.js')
    chart_install = $body.Contains('BFCurveInspector')
    hourly_step = $body.Contains('3600')
    range_context = $body.Contains('contextmenu') -or $body.Contains('range-prev')
  }
}
$helperRuntime = [ordered]@{}
foreach ($port in @(8093, 8094, 8095, 8096)) {
  try {
    $asset = (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$port/assets/curve-inspector.js?curve_verify=20260811" -TimeoutSec 15).Content
    $helperRuntime[[string]$port] = [ordered]@{ status = 200; bytes = $asset.Length; hourly_step = $asset.Contains('3600'); contextmenu = $asset.Contains('contextmenu'); point_id = $asset.Contains('点位ID'); timestamp = $asset.Contains('时间戳') }
  } catch { $helperRuntime[[string]$port] = [ordered]@{ status = $null; error = $_.Exception.Message } }
}
$replayJs = (Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8892/soft-zone-replay.js?curve_verify=20260811' -TimeoutSec 15).Content
$pages['8892_js'] = [ordered]@{
  bytes = $replayJs.Length
  range_buttons = $replayJs.Contains('rangePrevButton') -and $replayJs.Contains('rangeNextButton')
  contextmenu = $replayJs.Contains('contextmenu')
  point_id = $replayJs.Contains('点位ID')
  timestamp = $replayJs.Contains('时间戳')
}
$listeners = [ordered]@{}
foreach ($port in @(8093,8094,8095,8096,8768,8770,8892)) {
  $row = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
  $listeners[[string]$port] = if ($row) { [int]$row.OwningProcess } else { $null }
}
$helper = Join-Path 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW' '高炉前端数据\assets\curve-inspector.js'
[ordered]@{
  ok = ($pages['8093'].status -eq 200 -and $pages['8093'].helper -and $pages['8094'].status -eq 200 -and $pages['8094'].helper -and $pages['8094'].chart_install -and $pages['8095'].status -eq 200 -and $pages['8095'].helper -and $pages['8095'].chart_install -and $pages['8096'].status -eq 200 -and $pages['8096'].helper -and $pages['8096'].chart_install -and $helperRuntime.Values.status -notcontains $null -and ($helperRuntime.Values | Where-Object { -not $_.hourly_step -or -not $_.contextmenu -or -not $_.point_id -or -not $_.timestamp }).Count -eq 0 -and $pages['8892'].status -eq 200 -and $pages['8892'].hourly_step -and $pages['8892_js'].range_buttons -and $pages['8892_js'].contextmenu -and $pages['8892_js'].point_id -and $pages['8892_js'].timestamp)
  pages = $pages
  helper_runtime = $helperRuntime
  listeners = $listeners
  helper = [ordered]@{ exists = Test-Path -LiteralPath $helper; hash = if (Test-Path -LiteralPath $helper) { (Get-FileHash -LiteralPath $helper -Algorithm SHA256).Hash } else { $null } }
  service_8093 = (Get-Service BFV4PreviewProxy8093).Status.ToString()
} | ConvertTo-Json -Depth 8
