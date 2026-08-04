$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$service = 'BFV4PreviewProxy8093'
$html = Join-Path $root '高炉前端数据\frontend_dashboard_v3.server.html'
$stage = Join-Path $root 'logs\frontend_dashboard_v3.decision_basis_20260715.staged.html'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backup = "$html.bak_decision_basis_$stamp"

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
foreach ($marker in @('OptimizationEngineCockpitLayout','evidenceMetricIdsByLabel','规则判据：','处置逻辑：','OptimizationTab=OptimizationEngineCockpitLayout;')) {
  if (-not $text.Contains($marker)) { throw "Staged HTML missing marker: $marker" }
}
if ($text.Contains('版本：{engine.meta.version')) { throw 'Visible engine version comment still exists.' }
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
$response = Invoke-WebRequest -Uri "http://127.0.0.1:8093/?ws_port=8768&t=$stamp#optimization" -UseBasicParsing -TimeoutSec 45
foreach ($marker in @('evidenceMetricIdsByLabel','规则判据：','处置逻辑：')) {
  if (-not $response.Content.Contains($marker)) { throw "HTTP response missing marker: $marker" }
}
if ($response.Content.Contains('版本：{engine.meta.version')) { throw 'HTTP still contains visible engine version comment.' }
[pscustomobject]@{
  Backup = $backup
  BeforeHash = $beforeHash
  AfterHash = (Get-FileHash -LiteralPath $html -Algorithm SHA256).Hash
  Service = (Get-Service -Name $service).Status.ToString()
  Port8093 = [bool](Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
  Port8768 = [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
  HttpStatus = [int]$response.StatusCode
  VersionCommentVisible = $response.Content.Contains('版本：{engine.meta.version')
} | ConvertTo-Json -Depth 3
