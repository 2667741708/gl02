[CmdletBinding()]
param(
  [string]$StageRoot = 'C:\Users\Administrator\AppData\Local\Temp\curve_inspector_8094',
  [string]$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
)

$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$OutputEncoding = [Text.UTF8Encoding]::new($false)
$PSDefaultParameterValues['*:Encoding'] = 'utf8'
if ($PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 Core is required' }

$htmlTarget = Join-Path $Root '高炉前端数据\frontend_dashboard_v3.8094_preview.server.html'
$helperTarget = Join-Path $Root '高炉前端数据\assets\curve-inspector.js'
$htmlStage = Join-Path $StageRoot 'frontend_dashboard_v3.8094_preview.server.html'
$helperStage = Join-Path $StageRoot 'curve-inspector.js'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupDir = Join-Path $Root "backups\curve_inspector_8094_$stamp"
$htmlTemp = "$htmlTarget.__curve_inspector_$stamp.tmp"
$helperTemp = "$helperTarget.__curve_inspector_$stamp.tmp"
$ports = @(8093, 8094, 8768, 8770, 8892)

function Get-ListenerPid([int]$Port) {
  $row = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($row) { return [int]$row.OwningProcess }
  return $null
}

function Wait-Protected {
  param([int]$TimeoutSec = 30)
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  do {
    $missing = @($ports | Where-Object { -not (Get-ListenerPid $_) })
    if ($missing.Count -eq 0) { return }
    Start-Sleep -Milliseconds 500
  } while ((Get-Date) -lt $deadline)
  throw "protected listeners missing: $($missing -join ',')"
}

function Get-ProtectedSnapshot {
  $result = [ordered]@{}
  foreach ($port in $ports) { $result[([string]$port)] = Get-ListenerPid $port }
  return $result
}

function Assert-SnapshotStable($Before, $After) {
  foreach ($port in $ports) {
    $key = [string]$port
    if ([int]$Before[$key] -ne [int]$After[$key]) { throw "protected PID changed for $port" }
  }
}

function Assert-Page {
  $body = (Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8094/?curve_inspector=20260811' -TimeoutSec 15).Content
  if (-not $body.Contains('curve-inspector.js')) { throw '8094 HTML does not expose curve inspector helper' }
  if (-not $body.Contains('BFCurveInspector')) { throw '8094 HTML does not install curve inspector into ChartBox' }
  return $body.Length
}

$before = $null
$after = $null
$rollbackApplied = $false
$changed = $false
try {
  Wait-Protected
  if (-not (Test-Path -LiteralPath $htmlStage)) { throw "missing staged HTML: $htmlStage" }
  if (-not (Test-Path -LiteralPath $helperStage)) { throw "missing staged helper: $helperStage" }
  $before = Get-ProtectedSnapshot
  $beforeHash = [ordered]@{ html = (Get-FileHash -LiteralPath $htmlTarget -Algorithm SHA256).Hash; helper = if (Test-Path -LiteralPath $helperTarget) { (Get-FileHash -LiteralPath $helperTarget -Algorithm SHA256).Hash } else { $null } }
  New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
  Copy-Item -LiteralPath $htmlTarget -Destination (Join-Path $backupDir 'frontend_dashboard_v3.8094_preview.server.html')
  if (Test-Path -LiteralPath $helperTarget) { Copy-Item -LiteralPath $helperTarget -Destination (Join-Path $backupDir 'curve-inspector.js') }
  Copy-Item -LiteralPath $htmlStage -Destination $htmlTemp -Force
  Move-Item -LiteralPath $htmlTemp -Destination $htmlTarget -Force
  Copy-Item -LiteralPath $helperStage -Destination $helperTemp -Force
  Move-Item -LiteralPath $helperTemp -Destination $helperTarget -Force
  $changed = $true
  Start-Sleep -Milliseconds 250
  $pageLength = Assert-Page
  Wait-Protected
  $after = Get-ProtectedSnapshot
  Assert-SnapshotStable $before $after
  $afterHash = [ordered]@{ html = (Get-FileHash -LiteralPath $htmlTarget -Algorithm SHA256).Hash; helper = (Get-FileHash -LiteralPath $helperTarget -Algorithm SHA256).Hash }
  [ordered]@{ ok = $true; requirement_id = 'REQ-SENSOR-CURVE-INSPECTOR-HOURLY-RANGE-20260811'; changed = $changed; rollback_applied = $false; backup = $backupDir; page_length = $pageLength; before = $before; after = $after; before_hash = $beforeHash; after_hash = $afterHash; protected_ports = $ports } | ConvertTo-Json -Depth 8
} catch {
  if ($changed -and (Test-Path -LiteralPath (Join-Path $backupDir 'frontend_dashboard_v3.8094_preview.server.html'))) {
    Copy-Item -LiteralPath (Join-Path $backupDir 'frontend_dashboard_v3.8094_preview.server.html') -Destination $htmlTemp -Force
    Move-Item -LiteralPath $htmlTemp -Destination $htmlTarget -Force
    $backupHelper = Join-Path $backupDir 'curve-inspector.js'
    if (Test-Path -LiteralPath $backupHelper) { Copy-Item -LiteralPath $backupHelper -Destination $helperTemp -Force; Move-Item -LiteralPath $helperTemp -Destination $helperTarget -Force }
    $rollbackApplied = $true
  }
  [ordered]@{ ok = $false; requirement_id = 'REQ-SENSOR-CURVE-INSPECTOR-HOURLY-RANGE-20260811'; rollback_applied = $rollbackApplied; error = $_.Exception.Message; before = $before; after = $after } | ConvertTo-Json -Depth 8
  exit 1
} finally {
  Remove-Item -LiteralPath $htmlTemp,$helperTemp -Force -ErrorAction SilentlyContinue
}
