$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$serviceName = 'BFV4PreviewProxy8093'
$htmlPath = Join-Path $root '高炉前端数据\frontend_dashboard_v3.server.html'
$stagedPath = Join-Path $root 'logs\frontend_dashboard_v3.category_risk.staged.html'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupPath = "$htmlPath.bak_category_risk_$stamp"
$required = @(
  'OPS-LOCAL-DIAGNOSIS-CATEGORY-RISK-LAYERS-20260711',
  'DIAG_CATEGORY_COLORS',
  'BFDiagnosisRankListCategoryRisk',
  'BFDiagnosisSummaryCategoryRisk',
  'BFDiagScoreTrendOptionCategoryRisk',
  'topbar branded-topbar'
)

function Wait-Port([int]$Port, [bool]$Listening, [int]$TimeoutSeconds = 45) {
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    $found = [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($found -eq $Listening) { return }
    Start-Sleep -Seconds 1
  } while ((Get-Date) -lt $deadline)
  throw "Port $Port did not reach listening=$Listening"
}

if (-not (Test-Path -LiteralPath $htmlPath)) { throw "Target HTML missing: $htmlPath" }
if (-not (Test-Path -LiteralPath $stagedPath)) { throw "Staged HTML missing: $stagedPath" }
$stagedText = Get-Content -LiteralPath $stagedPath -Raw -Encoding UTF8
foreach ($marker in $required) { if (-not $stagedText.Contains($marker)) { throw "Staged HTML missing marker: $marker" } }

$before = [pscustomobject]@{
  Service = (Get-Service -Name $serviceName).Status.ToString()
  Port8093 = [bool](Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
  Port8768 = [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
  Hash = (Get-FileHash -LiteralPath $htmlPath -Algorithm SHA256).Hash
}
if (-not $before.Port8768) { throw '8768 data bridge is not listening; refusing replacement.' }

Stop-Service -Name $serviceName -Force
Wait-Port 8093 $false
if (-not [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)) { throw '8768 stopped unexpectedly; refusing replacement.' }
Copy-Item -LiteralPath $htmlPath -Destination $backupPath
Copy-Item -LiteralPath $stagedPath -Destination $htmlPath -Force
Start-Service -Name $serviceName
Wait-Port 8093 $true
Start-Sleep -Seconds 5

$response = Invoke-WebRequest -Uri "http://127.0.0.1:8093/?t=$stamp#diagnosis" -UseBasicParsing -TimeoutSec 45
foreach ($marker in $required) { if (-not $response.Content.Contains($marker)) { throw "HTTP response missing marker: $marker" } }
[pscustomobject]@{
  Before = $before
  BackupPath = $backupPath
  AfterService = (Get-Service -Name $serviceName).Status.ToString()
  Port8093 = [bool](Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
  Port8768 = [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
  FileHash = (Get-FileHash -LiteralPath $htmlPath -Algorithm SHA256).Hash
  HttpStatus = [int]$response.StatusCode
} | ConvertTo-Json -Depth 4
