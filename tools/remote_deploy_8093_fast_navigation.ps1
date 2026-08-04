$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$service = 'BFV4PreviewProxy8093'
$python = 'C:\Program Files\Python311\python.exe'
$html = Join-Path $root '高炉前端数据\frontend_dashboard_v3.server.html'
$patch = Join-Path $root 'tools\patch_22012_8093_core_metric_groups.py'
$stage = Join-Path $root 'logs\patch_8093_fast_navigation_20260715.staged.py'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$htmlBackup = "$html.bak_fast_navigation_$stamp"
$patchBackup = "$patch.bak_fast_navigation_$stamp"

function Wait-Port([int]$Port, [bool]$Listening, [int]$TimeoutSeconds = 75) {
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    $found = [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($found -eq $Listening) { return }
    Start-Sleep -Seconds 1
  } while ((Get-Date) -lt $deadline)
  throw "Port $Port did not reach listening=$Listening"
}

function Assert-PageContract([string]$Text, [string]$Source) {
  foreach ($marker in @(
    'REQ-8093-FAST-IN-APP-NAV-20260715',
    'aria-label="进入趋势分析"',
    'OPS-8093-OVERVIEW-THREE-COLUMN-V12',
    'OptimizationEngineCockpitLayout',
    'topbar branded-topbar',
    'logo/冀南钢铁集团logo.png',
    'logo/燕山大学logo.png'
  )) {
    if (-not $Text.Contains($marker)) { throw "$Source missing marker: $marker" }
  }
  if ($Text.Contains('window.location.hash=hash;window.location.reload()')) {
    throw "$Source still contains forced full-page navigation reload"
  }
}

if (-not (Test-Path -LiteralPath $stage)) { throw "Staged patch missing: $stage" }
if (-not (Test-Path -LiteralPath $python)) { throw "Python missing: $python" }
if (-not [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)) {
  throw '8768 is not listening; refusing deployment.'
}

$stagedText = Get-Content -LiteralPath $stage -Raw -Encoding UTF8
foreach ($marker in @('REQ-8093-FAST-IN-APP-NAV-20260715', 'aria-label="进入趋势分析"', 'upgrade_fast_in_app_navigation')) {
  if (-not $stagedText.Contains($marker)) { throw "Staged patch missing marker: $marker" }
}

$beforeHash = (Get-FileHash -LiteralPath $html -Algorithm SHA256).Hash
Copy-Item -LiteralPath $html -Destination $htmlBackup -Force
Copy-Item -LiteralPath $patch -Destination $patchBackup -Force

try {
  Copy-Item -LiteralPath $stage -Destination $patch -Force
  $patchOutput = & $python $patch 2>&1 | Out-String
  if ($LASTEXITCODE -ne 0) { throw "Patch failed: $patchOutput" }
  $afterText = Get-Content -LiteralPath $html -Raw -Encoding UTF8
  Assert-PageContract $afterText 'Patched file'

  Stop-Service -Name $service -Force
  Wait-Port 8093 $false
  Start-Service -Name $service
  Wait-Port 8093 $true
  Start-Sleep -Seconds 4

  $response = Invoke-WebRequest -Uri "http://127.0.0.1:8093/?ws_port=8768&fast_navigation=$stamp#overview" -UseBasicParsing -TimeoutSec 45
  Assert-PageContract $response.Content 'HTTP response'
  if (-not [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)) {
    throw '8768 stopped listening during 8093 deployment.'
  }

  [pscustomobject]@{
    Backup = $htmlBackup
    PatchBackup = $patchBackup
    BeforeHash = $beforeHash
    AfterHash = (Get-FileHash -LiteralPath $html -Algorithm SHA256).Hash
    PatchOutput = $patchOutput.Trim()
    Service = (Get-Service -Name $service).Status.ToString()
    Port8093 = [bool](Get-NetTCPConnection -LocalPort 8093 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
    Port8768 = [bool](Get-NetTCPConnection -LocalPort 8768 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1)
    HttpStatus = [int]$response.StatusCode
    HasFastNavigation = $response.Content.Contains('REQ-8093-FAST-IN-APP-NAV-20260715')
    HasForcedReload = $response.Content.Contains('window.location.hash=hash;window.location.reload()')
  } | ConvertTo-Json -Depth 4
}
catch {
  Copy-Item -LiteralPath $htmlBackup -Destination $html -Force
  Copy-Item -LiteralPath $patchBackup -Destination $patch -Force
  if ((Get-Service -Name $service).Status -ne 'Running') { Start-Service -Name $service }
  Wait-Port 8093 $true
  throw
}
