$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7 Core required.' }
$Utf8 = [Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8; [Console]::OutputEncoding = $Utf8; $OutputEncoding = $Utf8
$PSDefaultParameterValues['*:Encoding'] = 'utf8'

$Root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$Stage = 'C:\Users\Administrator\AppData\Local\Temp\curve_inspector_8093'
$Service = 'BFV4PreviewProxy8093'
$WsService = 'BFV4PreviewWs8768'
$Manager = Join-Path $Root 'tools\manage_22012_managed_services.ps1'
$Config = Join-Path $Root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$Pwsh = 'C:\Program Files\PowerShell\7\pwsh.exe'
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$Backup = Join-Path $Root "backups\curve_inspector_8093_$Stamp"
$Files = @(
  @{ Stage = Join-Path $Stage 'foreman_trend_preview.html'; Target = Join-Path $Root '高炉前端数据\foreman_trend_preview.html'; Marker = 'REQ-FOREMAN-TREND-STANDALONE-PREVIEW-20260805' },
  @{ Stage = Join-Path $Stage 'foreman-trend-preview.js'; Target = Join-Path $Root '高炉前端数据\assets\foreman-trend-preview.js'; Marker = 'applyManualRange' },
  @{ Stage = Join-Path $Stage 'curve-inspector.js'; Target = Join-Path $Root '高炉前端数据\assets\curve-inspector.js'; Marker = 'REQ-SENSOR-CURVE-INSPECTOR-HOURLY-RANGE-20260811' }
)

function Listener([int]$Port) { $row = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1; if ($row) { return [int]$row.OwningProcess }; return $null }
function WaitPort([int]$Port, [bool]$Expected) { $deadline = (Get-Date).AddSeconds(40); do { if (([bool](Listener $Port)) -eq $Expected) { return }; Start-Sleep -Milliseconds 250 } while ((Get-Date) -lt $deadline); throw "Port $Port listening=$Expected timeout" }
function Stop8093 { & $Pwsh -NoLogo -NoProfile -File $Manager -Action stop -ConfigPath $Config | Out-Null; WaitPort 8093 $false }
function Start8093 { & $Pwsh -NoLogo -NoProfile -File $Manager -Action start -ConfigPath $Config | Out-Null; WaitPort 8093 $true }
function WaitProtected { $deadline = (Get-Date).AddSeconds(45); do { $ok = $true; foreach ($port in @(8094,8768,8770,8892)) { if (-not (Listener $port)) { $ok = $false; break } }; if ($ok) { return }; Start-Sleep -Milliseconds 500 } while ((Get-Date) -lt $deadline); throw 'Protected ports did not stabilize before deployment' }

foreach ($file in $Files) { if (-not (Test-Path -LiteralPath $file.Stage -PathType Leaf)) { throw "Missing stage: $($file.Stage)" }; if (-not (Test-Path -LiteralPath $file.Target -PathType Leaf) -and $file.Target -notlike '*curve-inspector.js') { throw "Missing target: $($file.Target)" }; if (-not (Get-Content -LiteralPath $file.Stage -Raw -Encoding UTF8).Contains($file.Marker)) { throw "Marker missing: $($file.Marker)" } }
if (-not (Test-Path -LiteralPath $Manager) -or -not (Test-Path -LiteralPath $Config)) { throw '8093 service control files missing' }
$mutex = [Threading.Mutex]::new($false, 'Global\BFV4PreviewProxy8093Deployment')
if (-not $mutex.WaitOne(0)) { throw '8093 deployment mutex is busy' }
$before = $null
$old8093 = Listener 8093
$previous = @{}; $success = $false; $guardPaused = $false; $guardRestored = $false; $rollback = $false
try {
  if ((Get-Service $Service).Status -ne 'Running' -or (Get-Service $WsService).Status -ne 'Running') { throw '8093/8768 must be running before deployment' }
  WaitProtected
  $before = @{ '8094' = Listener 8094; '8768' = Listener 8768; '8770' = Listener 8770; '8892' = Listener 8892 }
  New-Item -ItemType Directory -Path $Backup -Force | Out-Null
  foreach ($file in $Files) { $leaf = Split-Path -Leaf $file.Target; $previous[$file.Target] = Join-Path $Backup $leaf; if (Test-Path -LiteralPath $file.Target -PathType Leaf) { Copy-Item -LiteralPath $file.Target -Destination $previous[$file.Target] -Force } else { $previous[$file.Target] = $null } }
  Stop8093; $guardPaused = $true
  foreach ($file in $Files) { $tmp = "$($file.Target).deploying-$Stamp"; Copy-Item -LiteralPath $file.Stage -Destination $tmp -Force; Move-Item -LiteralPath $tmp -Destination $file.Target -Force }
  Start8093; $guardRestored = $true
  $new8093 = Listener 8093
  if (-not $new8093 -or $new8093 -eq $old8093) { throw '8093 listener PID did not change after guarded update' }
  $page = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/foreman_trend_preview.html?ws_port=8768&pspace_ws_port=8770&curve_inspector=$Stamp" -TimeoutSec 30
  if ($page.StatusCode -ne 200 -or -not $page.Content.Contains('curve-inspector.js') -or -not $page.Content.Contains('trend-range-start')) { throw 'foreman page contract failed' }
  $js = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/assets/foreman-trend-preview.js?curve_inspector=$Stamp" -TimeoutSec 30
  $helper = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8093/assets/curve-inspector.js?curve_inspector=$Stamp" -TimeoutSec 30
  if ($js.StatusCode -ne 200 -or -not $js.Content.Contains('applyManualRange') -or $helper.StatusCode -ne 200 -or -not $helper.Content.Contains('contextmenu')) { throw 'curve assets contract failed' }
  $after = @{ '8094' = Listener 8094; '8768' = Listener 8768; '8770' = Listener 8770; '8892' = Listener 8892 }
  foreach ($port in $before.Keys) { if ($after[$port] -ne $before[$port]) { throw "Protected PID changed: $port" } }
  $success = $true
  [ordered]@{ ok = $true; requirement_id = 'REQ-SENSOR-CURVE-INSPECTOR-HOURLY-RANGE-20260811'; old_8093_pid = $old8093; new_8093_pid = $new8093; guard_paused = $guardPaused; guard_restored = $guardRestored; rollback_applied = $false; protected_before = $before; protected_after = $after; backup = $Backup; http_8093 = $page.StatusCode } | ConvertTo-Json -Depth 6
}
catch {
  $failure = $_.Exception.Message
  try { if ((Get-Service $Service).Status -ne 'Stopped') { Stop8093 }; foreach ($target in $previous.Keys) { if ($previous[$target]) { Copy-Item -LiteralPath $previous[$target] -Destination $target -Force } elseif (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Force } }; $rollback = $true; Start8093; $guardRestored = $true } catch { Write-Error "Rollback failed: $($_.Exception.Message)" }
  [ordered]@{ ok = $false; requirement_id = 'REQ-SENSOR-CURVE-INSPECTOR-HOURLY-RANGE-20260811'; failure = $failure; guard_paused = $guardPaused; guard_restored = $guardRestored; rollback_applied = $rollback; backup = $Backup; listener_8093 = Listener 8093 } | ConvertTo-Json -Depth 5
  throw
}
finally { $mutex.ReleaseMutex(); $mutex.Dispose() }
if (-not $success) { exit 1 }
