$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$service = 'BFV4PreviewProxy8093'
$html = Join-Path $root '高炉前端数据\frontend_dashboard_v3.server.html'
$stage = Join-Path $root 'logs\frontend_dashboard_v3.hide_decision_labels_20260715.staged.html'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backup = "$html.bak_hide_decision_labels_$stamp"

function Wait-Port([int]$Port, [bool]$Listening, [int]$TimeoutSeconds = 75) {
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    $found = [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($found -eq $Listening) { return }
    Start-Sleep -Seconds 1
  } while ((Get-Date) -lt $deadline)
  throw "Port $Port did not reach listening=$Listening"
}

function Get-Section([string]$Source, [string]$StartMarker, [string]$EndMarker) {
  $start = $Source.IndexOf($StartMarker, [StringComparison]::Ordinal)
  if ($start -lt 0) { throw "Section start marker missing: $StartMarker" }
  $end = $Source.IndexOf($EndMarker, $start + $StartMarker.Length, [StringComparison]::Ordinal)
  if ($end -lt 0) { throw "Section end marker missing: $EndMarker" }
  return $Source.Substring($start, $end - $start)
}

if (-not (Test-Path -LiteralPath $stage)) { throw "Staged HTML missing: $stage" }
$text = Get-Content -LiteralPath $stage -Raw -Encoding UTF8
foreach ($marker in @(
  'OptimizationEngineCockpitLayout',
  "{basisEvidence.join('；')",
  '<br/>{basisLogic}',
  'OptimizationTab=OptimizationEngineCockpitLayout;',
  'REQ-8093-OVERVIEW-TREND-JUMP-NO-OVERLAP-20260715'
)) {
  if (-not $text.Contains($marker)) { throw "Staged HTML missing marker: $marker" }
}
$component = Get-Section $text 'function OptimizationEngineCockpitLayout' 'OptimizationTab=OptimizationEngineCockpitLayout;'
foreach ($forbidden in @('规则判据：', '处置逻辑：')) {
  if ($component.Contains($forbidden)) { throw "Decision label still exists: $forbidden" }
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

$response = Invoke-WebRequest -Uri "http://127.0.0.1:8093/?ws_port=8768&t=$stamp#optimization" -UseBasicParsing -TimeoutSec 45
$httpComponent = Get-Section $response.Content 'function OptimizationEngineCockpitLayout' 'OptimizationTab=OptimizationEngineCockpitLayout;'
foreach ($forbidden in @('规则判据：', '处置逻辑：')) {
  if ($httpComponent.Contains($forbidden)) { throw "HTTP decision label still exists: $forbidden" }
}

[pscustomobject]@{
  Backup = $backup
  BeforeHash = $beforeHash
  AfterHash = (Get-FileHash -LiteralPath $html -Algorithm SHA256).Hash
  Service = (Get-Service -Name $service).Status.ToString()
  Port8093 = [bool](Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
  Port8768 = [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
  HttpStatus = [int]$response.StatusCode
  HiddenLabels = -not ($httpComponent.Contains('规则判据：') -or $httpComponent.Contains('处置逻辑：'))
} | ConvertTo-Json -Depth 3
