[CmdletBinding()]
param(
  [Parameter(Mandatory)][string]$StageRoot,
  [Parameter(Mandatory)][string]$TargetRoot,
  [Parameter(Mandatory)][string]$HtmlName,
  [int]$Port
)
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$OutputEncoding = [Text.UTF8Encoding]::new($false)
$PSDefaultParameterValues['*:Encoding'] = 'utf8'
if ($PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 Core is required' }
$htmlTarget = Join-Path (Join-Path $TargetRoot '高炉前端数据') $HtmlName
$helperTarget = Join-Path (Join-Path $TargetRoot '高炉前端数据') 'assets\curve-inspector.js'
$htmlStage = Join-Path $StageRoot $HtmlName
$helperStage = Join-Path $StageRoot 'curve-inspector.js'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupDir = Join-Path $TargetRoot "backups\curve_inspector_static_${Port}_$stamp"
$htmlTemp = "$htmlTarget.__curve_inspector_$stamp.tmp"
$helperTemp = "$helperTarget.__curve_inspector_$stamp.tmp"
$ports = @(8093, 8094, 8095, 8096, 8768, 8770, 8892)
function Get-ListenerPid([int]$P) { $r = Get-NetTCPConnection -State Listen -LocalPort $P -ErrorAction SilentlyContinue | Select-Object -First 1; if ($r) { return [int]$r.OwningProcess }; return $null }
function Wait-Protected { $deadline = (Get-Date).AddSeconds(35); do { $missing = @($ports | Where-Object { -not (Get-ListenerPid $_) }); if ($missing.Count -eq 0) { return }; Start-Sleep -Milliseconds 500 } while ((Get-Date) -lt $deadline); throw "protected listeners missing: $($missing -join ',')" }
function Snapshot { $s = [ordered]@{}; foreach ($p in $ports) { $s[[string]$p] = Get-ListenerPid $p }; return $s }
function Stable($a, $b) { foreach ($p in $ports) { $k = [string]$p; if ([int]$a[$k] -ne [int]$b[$k]) { throw "protected PID changed for $p" } } }
$before = $null; $after = $null; $changed = $false; $rollback = $false
try {
  Wait-Protected
  if (-not (Test-Path -LiteralPath $htmlStage)) { throw "missing staged HTML: $htmlStage" }
  if (-not (Test-Path -LiteralPath $helperStage)) { throw "missing staged helper: $helperStage" }
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $htmlTarget), (Split-Path -Parent $helperTarget) | Out-Null
  $before = Snapshot
  $beforeHash = [ordered]@{ html = (Get-FileHash -LiteralPath $htmlTarget -Algorithm SHA256).Hash; helper = if (Test-Path -LiteralPath $helperTarget) { (Get-FileHash -LiteralPath $helperTarget -Algorithm SHA256).Hash } else { $null } }
  New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
  Copy-Item -LiteralPath $htmlTarget -Destination (Join-Path $backupDir $HtmlName)
  if (Test-Path -LiteralPath $helperTarget) { Copy-Item -LiteralPath $helperTarget -Destination (Join-Path $backupDir 'curve-inspector.js') }
  Copy-Item -LiteralPath $htmlStage -Destination $htmlTemp -Force; Move-Item -LiteralPath $htmlTemp -Destination $htmlTarget -Force; $changed = $true
  Copy-Item -LiteralPath $helperStage -Destination $helperTemp -Force; Move-Item -LiteralPath $helperTemp -Destination $helperTarget -Force
  Start-Sleep -Milliseconds 250
  $body = (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/?curve_inspector=20260811" -TimeoutSec 15).Content
  if (-not $body.Contains('curve-inspector.js') -or -not $body.Contains('BFCurveInspector')) { throw "curve inspector marker missing on port $Port" }
  Wait-Protected; $after = Snapshot; Stable $before $after
  $afterHash = [ordered]@{ html = (Get-FileHash -LiteralPath $htmlTarget -Algorithm SHA256).Hash; helper = (Get-FileHash -LiteralPath $helperTarget -Algorithm SHA256).Hash }
  [ordered]@{ ok = $true; requirement_id = 'REQ-SENSOR-CURVE-INSPECTOR-HOURLY-RANGE-20260811'; port = $Port; backup = $backupDir; before = $before; after = $after; before_hash = $beforeHash; after_hash = $afterHash } | ConvertTo-Json -Depth 8
} catch {
  if ($changed -and (Test-Path -LiteralPath (Join-Path $backupDir $HtmlName))) {
    Copy-Item -LiteralPath (Join-Path $backupDir $HtmlName) -Destination $htmlTemp -Force; Move-Item -LiteralPath $htmlTemp -Destination $htmlTarget -Force
    $backupHelper = Join-Path $backupDir 'curve-inspector.js'; if (Test-Path -LiteralPath $backupHelper) { Copy-Item -LiteralPath $backupHelper -Destination $helperTemp -Force; Move-Item -LiteralPath $helperTemp -Destination $helperTarget -Force }
    $rollback = $true
  }
  [ordered]@{ ok = $false; requirement_id = 'REQ-SENSOR-CURVE-INSPECTOR-HOURLY-RANGE-20260811'; port = $Port; rollback_applied = $rollback; error = $_.Exception.Message } | ConvertTo-Json -Depth 8
  exit 1
} finally { Remove-Item -LiteralPath $htmlTemp,$helperTemp -Force -ErrorAction SilentlyContinue }
