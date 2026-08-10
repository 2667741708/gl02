$ErrorActionPreference = "Stop"
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$root = "F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW"
$tempPage = "C:\Users\Administrator\AppData\Local\Temp\frontend_dashboard_v3_zero_guard_20260807.html"
$frontend = Join-Path $root "高炉前端数据"
$page8093 = Join-Path $frontend "frontend_dashboard_v3.server.html"
$page8094 = Join-Path $frontend "frontend_dashboard_v3.8094_preview.server.html"
$tools = Join-Path $root "tools"
$manager = Join-Path $tools "manage_22012_managed_services.ps1"
$guardConfig = Join-Path $tools "service_configs\22012_BFV4PreviewProxy8093.json"
$restart8094 = Join-Path $tools "restart_22012_8094_preview.ps1"
$patch8094 = Join-Path $tools "patch_8094_multi_condition_review.py"
$python = "C:\Program Files\Python311\python.exe"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $root "backups\zero_guard_pages_20260807\$stamp"
$stage = Join-Path $root ".deploy_staging\zero_guard_pages_$stamp"
$stage8093 = Join-Path $stage "frontend_dashboard_v3.server.html"
$stage8094 = Join-Path $stage "frontend_dashboard_v3.8094_preview.server.html"
$guardPaused = $false
$mutationStarted = $false
$success = $false

function Get-Pid([int]$Port) { $item = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if ($item) { return [int]$item.OwningProcess }; return $null }
function Wait-Port([int]$Port, [bool]$Want, [int]$Timeout = 120) { $until = (Get-Date).AddSeconds($Timeout); do { if (($null -ne (Get-Pid $Port)) -eq $Want) { return }; Start-Sleep -Seconds 1 } while ((Get-Date) -lt $until); throw "Port $Port listening=$Want timeout" }
function Atomic-Copy([string]$Source, [string]$Target) { $tmp = "$Target.zero_guard.tmp"; Copy-Item -LiteralPath $Source -Destination $tmp -Force; Move-Item -LiteralPath $tmp -Destination $Target -Force }
function Get-Page([string]$Uri) { for ($i = 1; $i -le 12; $i++) { try { return Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 20 } catch { if ($i -eq 12) { throw }; Start-Sleep -Seconds 2 } } }

if (-not (Test-Path -LiteralPath $tempPage -PathType Leaf)) { throw "Uploaded page missing" }
foreach ($required in @($manager, $guardConfig, $restart8094, $patch8094)) { if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Required file missing: $required" } }
if ((Get-Service -Name BFV4PreviewWs8768 -ErrorAction Stop).Status -ne "Running") { throw "8768 service is not running" }
foreach ($port in @(8093, 8094, 8768)) { if (-not (Get-Pid $port)) { throw "Required port is not listening: $port" } }
if (-not (Get-Content -LiteralPath $tempPage -Raw -Encoding UTF8).Contains("REQ-FOREMAN-DUAL-CONTROL-ZERO-GUARD-20260807")) { throw "Uploaded page marker missing" }

New-Item -ItemType Directory -Path $backup -Force | Out-Null
New-Item -ItemType Directory -Path $stage -Force | Out-Null
$backup8093 = Join-Path $backup "frontend_dashboard_v3.server.html"
$backup8094 = Join-Path $backup "frontend_dashboard_v3.8094_preview.server.html"
Copy-Item -LiteralPath $page8093 -Destination $backup8093 -Force
Copy-Item -LiteralPath $page8094 -Destination $backup8094 -Force
Copy-Item -LiteralPath $tempPage -Destination $stage8093 -Force
Copy-Item -LiteralPath $page8094 -Destination $stage8094 -Force
& $python -X utf8 $patch8094 --target $stage8094 --feature-source $stage8093 --ws-port 8768
if ($LASTEXITCODE -ne 0) { throw "8094 page patch failed" }

try {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action stop -ConfigPath $guardConfig
    $guardPaused = $true
    Wait-Port 8093 $false 90
    $mutationStarted = $true
    Atomic-Copy $stage8093 $page8093
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action start -ConfigPath $guardConfig
    Wait-Port 8093 $true 150
    $guardPaused = $false
    Atomic-Copy $stage8094 $page8094
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $restart8094
    if ($LASTEXITCODE -ne 0) { throw "8094 restart failed" }
    $r8093 = Get-Page "http://127.0.0.1:8093/?zero_guard=20260807"
    $r8094 = Get-Page "http://127.0.0.1:8094/?zero_guard=20260807"
    foreach ($r in @($r8093, $r8094)) { if ($r.StatusCode -ne 200) { throw "HTTP status is not 200" }; if (-not $r.Content.Contains("REQ-FOREMAN-DUAL-CONTROL-ZERO-GUARD-20260807")) { throw "Zero guard marker missing" }; if ($r.Content.Contains("Number(action?.recommended_target)")) { throw "Old null-to-zero conversion remains" } }
    foreach ($port in @(8093, 8094, 8768)) { if (-not (Get-Pid $port)) { throw "Port $port is not listening after repair" } }
    $success = $true
    [ordered]@{ ok = $true; operation = "REQ-FOREMAN-DUAL-CONTROL-ZERO-GUARD-20260807"; backup = $backup; http8093 = [int]$r8093.StatusCode; http8094 = [int]$r8094.StatusCode; guardPaused = $true; guardRestored = $true; readOnly = $true } | ConvertTo-Json -Depth 5
}
catch {
    $failure = $_
    if ($guardPaused) { & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action start -ConfigPath $guardConfig -ErrorAction SilentlyContinue; Wait-Port 8093 $true 120; $guardPaused = $false }
    if ($mutationStarted) { Atomic-Copy $backup8093 $page8093; Atomic-Copy $backup8094 $page8094; & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $restart8094 -ErrorAction SilentlyContinue }
    throw $failure
}
finally {
    Remove-Item -LiteralPath $tempPage -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
}
