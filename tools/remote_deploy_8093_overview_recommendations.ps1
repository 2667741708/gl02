$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$service = 'BFV4PreviewProxy8093'
$html = Join-Path $root '高炉前端数据\frontend_dashboard_v3.server.html'
$stage = Join-Path $root 'logs\frontend_dashboard_v3.overview_recommendations_20260715.staged.html'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backup = "$html.bak_overview_recommendations_$stamp"

function Wait-Port([int]$Port, [bool]$Listening, [int]$TimeoutSeconds = 75) {
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    $found = [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($found -eq $Listening) { return }
    Start-Sleep -Seconds 1
  } while ((Get-Date) -lt $deadline)
  throw "Port $Port did not reach listening=$Listening"
}

if (-not (Test-Path -LiteralPath $stage)) { throw "Staged HTML missing: $stage" }
$text = Get-Content -LiteralPath $stage -Raw -Encoding UTF8
foreach ($marker in @(
  'REQ-8093-OVERVIEW-SHARED-RECOMMENDATION-20260715',
  'BFOverviewRightThreeColumnV12',
  'bfRecommendationEngineView(diagnosis)',
  'engine.actions.slice(0,3)',
  '完整引擎 · 前三条摘要',
  'OptimizationTab=OptimizationEngineCockpitLayout;'
)) {
  if (-not $text.Contains($marker)) { throw "Staged HTML missing marker: $marker" }
}
$component = $text.Split('OverviewRight=function BFOverviewRightThreeColumnV12', 2)[1].Split('OverviewTab=function BFOverviewTabThreeColumnV12', 2)[0]
if ($component.Contains("titles=['优化送风制度','调整布料策略']")) {
  throw 'Final overview component still uses fixed recommendation titles.'
}
if (-not [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)) {
  throw '8768 is not listening; refusing deployment.'
}

$beforeHash = (Get-FileHash -LiteralPath $html -Algorithm SHA256).Hash
Stop-Service -Name $service -Force
Wait-Port 8093 $false
Copy-Item -LiteralPath $html -Destination $backup -Force
Copy-Item -LiteralPath $stage -Destination $html -Force
Start-Service -Name $service
Wait-Port 8093 $true
Start-Sleep -Seconds 4

$response = Invoke-WebRequest -Uri "http://127.0.0.1:8093/?ws_port=8768&t=$stamp#overview" -UseBasicParsing -TimeoutSec 45
foreach ($marker in @(
  'REQ-8093-OVERVIEW-SHARED-RECOMMENDATION-20260715',
  'engine.actions.slice(0,3)',
  'OptimizationTab=OptimizationEngineCockpitLayout;'
)) {
  if (-not $response.Content.Contains($marker)) { throw "HTTP response missing marker: $marker" }
}

[pscustomobject]@{
  Backup = $backup
  BeforeHash = $beforeHash
  AfterHash = (Get-FileHash -LiteralPath $html -Algorithm SHA256).Hash
  Service = (Get-Service -Name $service).Status.ToString()
  Port8093 = [bool](Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
  Port8768 = [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
  HttpStatus = [int]$response.StatusCode
  SharedRecommendationMarker = $response.Content.Contains('REQ-8093-OVERVIEW-SHARED-RECOMMENDATION-20260715')
} | ConvertTo-Json -Depth 3
