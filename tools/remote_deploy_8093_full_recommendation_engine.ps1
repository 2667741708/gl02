$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$stage = Join-Path $root 'logs\full_recommendation_engine_stage_20260715'
$htmlPath = Join-Path $root '高炉前端数据\frontend_dashboard_v3.server.html'
$bridgePath = Join-Path $root '自动诊断服务\local_pg_ws_bridge.py'
$adapterPath = Join-Path $root '自动诊断服务\recommendation_adapter.py'
$enginePath = Join-Path $root '调控结论生成引擎'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupRoot = Join-Path $root "backups\full_recommendation_engine_$stamp"
$python = 'C:\Program Files\Python311\python.exe'
$proxyService = 'BFV4PreviewProxy8093'
$wsService = 'BFV4PreviewWs8768'

function Wait-Port([int]$Port, [bool]$Listening, [int]$TimeoutSeconds = 75) {
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    $found = [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($found -eq $Listening) { return }
    Start-Sleep -Seconds 1
  } while ((Get-Date) -lt $deadline)
  throw "Port $Port did not reach listening=$Listening"
}

function Copy-Backup([string]$Source, [string]$RelativeTarget) {
  if (-not (Test-Path -LiteralPath $Source)) { return }
  $target = Join-Path $backupRoot $RelativeTarget
  $parent = Split-Path -Parent $target
  New-Item -ItemType Directory -Path $parent -Force | Out-Null
  if ((Get-Item -LiteralPath $Source).PSIsContainer) {
    Copy-Item -LiteralPath $Source -Destination $target -Recurse -Force
  } else {
    Copy-Item -LiteralPath $Source -Destination $target -Force
  }
}

$stageHtml = Join-Path $stage '高炉前端数据\frontend_dashboard_v3.server.html'
$stageBridge = Join-Path $stage '自动诊断服务\local_pg_ws_bridge.py'
$stageAdapter = Join-Path $stage '自动诊断服务\recommendation_adapter.py'
$stageEngine = Join-Path $stage '调控结论生成引擎'
$requiredFiles = @(
  $stageHtml,
  $stageBridge,
  $stageAdapter,
  (Join-Path $stageEngine 'main.py'),
  (Join-Path $stageEngine 'recommendation\__init__.py'),
  (Join-Path $stageEngine 'recommendation\core.py'),
  (Join-Path $stageEngine 'recommendation\action_templates.py'),
  (Join-Path $stageEngine 'recommendation\severity_mapper.py'),
  (Join-Path $stageEngine 'recommendation\combination.py'),
  (Join-Path $stageEngine 'recommendation\safety_gate.py'),
  (Join-Path $stageEngine 'recommendation\formatter.py')
)
foreach ($file in $requiredFiles) {
  if (-not (Test-Path -LiteralPath $file)) { throw "Staged file missing: $file" }
}
$htmlText = Get-Content -LiteralPath $stageHtml -Raw -Encoding UTF8
foreach ($marker in @('REQ-OPT-FULL-ENGINE-20260715','OptimizationEngineCockpitLayout','bfRecommendationEngineView','OptimizationTab=OptimizationEngineCockpitLayout;','topbar branded-topbar')) {
  if (-not $htmlText.Contains($marker)) { throw "Staged HTML missing marker: $marker" }
}
foreach ($file in $requiredFiles | Where-Object { $_.EndsWith('.py') }) {
  & $python -X utf8 -m py_compile $file
  if ($LASTEXITCODE -ne 0) { throw "Python compile failed: $file" }
}

$before = [pscustomobject]@{
  ProxyService = (Get-Service -Name $proxyService).Status.ToString()
  WsService = (Get-Service -Name $wsService).Status.ToString()
  Port8093 = [bool](Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
  Port8768 = [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
  HtmlHash = (Get-FileHash -LiteralPath $htmlPath -Algorithm SHA256).Hash
  BridgeHash = (Get-FileHash -LiteralPath $bridgePath -Algorithm SHA256).Hash
}
if (-not $before.Port8093 -or -not $before.Port8768) { throw '8093 or 8768 is not listening; refusing deployment.' }

New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
Copy-Backup $htmlPath '高炉前端数据\frontend_dashboard_v3.server.html'
Copy-Backup $bridgePath '自动诊断服务\local_pg_ws_bridge.py'
Copy-Backup $adapterPath '自动诊断服务\recommendation_adapter.py'
Copy-Backup $enginePath '调控结论生成引擎'

Stop-Service -Name $proxyService -Force
Wait-Port 8093 $false
Stop-Service -Name $wsService -Force
Wait-Port 8768 $false

try {
  New-Item -ItemType Directory -Path (Split-Path -Parent $htmlPath),(Split-Path -Parent $bridgePath),$enginePath -Force | Out-Null
  Copy-Item -LiteralPath $stageHtml -Destination $htmlPath -Force
  Copy-Item -LiteralPath $stageBridge -Destination $bridgePath -Force
  Copy-Item -LiteralPath $stageAdapter -Destination $adapterPath -Force
  Copy-Item -Path (Join-Path $stageEngine '*') -Destination $enginePath -Recurse -Force

  Start-Service -Name $wsService
  Wait-Port 8768 $true
  Start-Service -Name $proxyService
  Wait-Port 8093 $true
  Start-Sleep -Seconds 5

  $response = Invoke-WebRequest -Uri "http://127.0.0.1:8093/?ws_port=8768&t=$stamp#optimization" -UseBasicParsing -TimeoutSec 45
  foreach ($marker in @('REQ-OPT-FULL-ENGINE-20260715','OptimizationEngineCockpitLayout','OptimizationTab=OptimizationEngineCockpitLayout;')) {
    if (-not $response.Content.Contains($marker)) { throw "HTTP response missing marker: $marker" }
  }
} catch {
  try { Stop-Service -Name $proxyService -Force -ErrorAction SilentlyContinue } catch {}
  try { Stop-Service -Name $wsService -Force -ErrorAction SilentlyContinue } catch {}
  $backupHtml = Join-Path $backupRoot '高炉前端数据\frontend_dashboard_v3.server.html'
  $backupBridge = Join-Path $backupRoot '自动诊断服务\local_pg_ws_bridge.py'
  if (Test-Path -LiteralPath $backupHtml) { Copy-Item -LiteralPath $backupHtml -Destination $htmlPath -Force }
  if (Test-Path -LiteralPath $backupBridge) { Copy-Item -LiteralPath $backupBridge -Destination $bridgePath -Force }
  try { Start-Service -Name $wsService; Wait-Port 8768 $true } catch {}
  try { Start-Service -Name $proxyService; Wait-Port 8093 $true } catch {}
  throw
}

[pscustomobject]@{
  Before = $before
  BackupRoot = $backupRoot
  ProxyService = (Get-Service -Name $proxyService).Status.ToString()
  WsService = (Get-Service -Name $wsService).Status.ToString()
  Port8093 = [bool](Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
  Port8768 = [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
  HtmlHash = (Get-FileHash -LiteralPath $htmlPath -Algorithm SHA256).Hash
  BridgeHash = (Get-FileHash -LiteralPath $bridgePath -Algorithm SHA256).Hash
  HttpStatus = [int]$response.StatusCode
  Marker = 'REQ-OPT-FULL-ENGINE-20260715'
} | ConvertTo-Json -Depth 5
