$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding

$root = 'F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW'
$manager = Join-Path $root 'tools\manage_22012_managed_services.ps1'
$configPath = Join-Path $root 'tools\service_configs\22012_BFV4PreviewProxy8093.json'
$payloadRoot = 'C:\Users\Administrator\AppData\Local\Temp'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupRoot = Join-Path $root "logs\deploy_backups\diagnosis_core19_mount_r9_$stamp"
$payloads = @(
    [pscustomobject]@{ source = (Join-Path $payloadRoot 'ollama_proxy_server.py'); target = (Join-Path $root '高炉前端数据\智能助手\backend\ollama_proxy_server.py') },
    [pscustomobject]@{ source = (Join-Path $payloadRoot 'bf-diagnosis-review-local.js'); target = (Join-Path $root '高炉前端数据\assets\bf-diagnosis-review-local.js') },
    [pscustomobject]@{ source = (Join-Path $payloadRoot 'bf-diagnosis-manual-score-local.js'); target = (Join-Path $root '高炉前端数据\assets\bf-diagnosis-manual-score-local.js') }
)
$protectedPorts = @(8094, 8768, 8770, 11434)
$deploymentMutex = [Threading.Mutex]::new($false, 'Global\BFV4PreviewProxy8093Deployment')
$lockTaken = $false

function Get-ListenerPid([int]$Port) {
    $row = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($row) { return [int]$row.OwningProcess }
    return $null
}

function Wait-Port([int]$Port, [bool]$Listening, [int]$TimeoutSeconds) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        if (($null -ne (Get-ListenerPid $Port)) -eq $Listening) { return }
        Start-Sleep -Seconds 1
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "port $Port did not reach listening=$Listening"
}

function Invoke-Manager([string]$Action) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $manager -Action $Action -ConfigPath $configPath | Out-Null
}

function Install-Atomically([string]$Source, [string]$Target) {
    $temporary = "$Target.codex-r9.tmp"
    Copy-Item -LiteralPath $Source -Destination $temporary -Force
    Move-Item -LiteralPath $temporary -Destination $Target -Force
}

foreach ($required in @($manager, $configPath) + @($payloads | ForEach-Object { $_.source })) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "required file missing: $required" }
}
$proxyPayload = Get-Content -LiteralPath $payloads[0].source -Raw -Encoding UTF8
$manualPayload = Get-Content -LiteralPath $payloads[2].source -Raw -Encoding UTF8
$reviewPayload = Get-Content -LiteralPath $payloads[1].source -Raw -Encoding UTF8
if (-not $proxyPayload.Contains('20260806-core19-r9') -or $proxyPayload.Contains('<script defer src="/assets/bf-diagnosis-manual-score-local.js?v=20260806-core19-r9')) {
    throw 'r9 proxy payload markers are invalid'
}
if (-not $manualPayload.Contains('setInterval(function(){if(bootWhenBodyReady())clearInterval(bootPoll);},50)')) { throw 'manual-score body-poll marker missing' }
if (-not $reviewPayload.Contains('setInterval(function(){if(bootWhenBodyReady())clearInterval(bootPoll);},50)')) { throw 'review body-poll marker missing' }

$before = [ordered]@{}
foreach ($port in $protectedPorts) {
    $listenerPid = Get-ListenerPid $port
    if (-not $listenerPid) { throw "protected port $port is not listening" }
    $before[[string]$port] = $listenerPid
}
if (-not (Get-ListenerPid 8093)) { throw '8093 must be listening before deployment' }

New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
$manifest = @()
foreach ($payload in $payloads) {
    $backup = Join-Path $backupRoot ([IO.Path]::GetFileName($payload.target))
    Copy-Item -LiteralPath $payload.target -Destination $backup -Force
    $manifest += [pscustomobject]@{ target = $payload.target; backup = $backup }
}

$applied = $false
$guardPaused = $false
$guardRestored = $false
try {
    $lockTaken = $deploymentMutex.WaitOne([TimeSpan]::FromSeconds(120))
    if (-not $lockTaken) { throw 'timed out waiting for the 8093 deployment mutex' }
    Invoke-Manager 'stop'
    $guardPaused = $true
    Wait-Port 8093 $false 30
    foreach ($port in $protectedPorts) {
        if ((Get-ListenerPid $port) -ne $before[[string]$port]) { throw "protected port $port changed while pausing 8093" }
    }
    foreach ($payload in $payloads) { Install-Atomically $payload.source $payload.target }
    $applied = $true
}
catch {
    if ($applied) {
        foreach ($entry in $manifest) { Copy-Item -LiteralPath $entry.backup -Destination $entry.target -Force }
    }
    throw
}
finally {
    Invoke-Manager 'start'
    $guardRestored = $true
    if ($lockTaken) { $deploymentMutex.ReleaseMutex() }
    $deploymentMutex.Dispose()
}

try {
    Wait-Port 8093 $true 120
    $page = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8093/?t=core19-mount-r9' -TimeoutSec 30
    if ($page.StatusCode -ne 200 -or -not $page.Content.Contains('20260806-core19-r9')) { throw '8093 page does not expose r9' }
    $manual = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8093/assets/bf-diagnosis-manual-score-local.js?t=r9' -TimeoutSec 30
    if (-not $manual.Content.Contains('bootWhenBodyReady')) { throw 'manual-score r9 asset is unavailable' }
    $core = (Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8093/api/diagnosis-core-evidence?label=normal' -TimeoutSec 45).Content | ConvertFrom-Json
    $seriesCount = @($core.evidence.core_variable_evidence | Where-Object { @($_.series_60m).Count -gt 0 }).Count
    if ([int]$core.evidence.core_variable_count -ne 19 -or $seriesCount -ne 19) { throw 'core19 endpoint contract failed' }
    foreach ($port in $protectedPorts) {
        if ((Get-ListenerPid $port) -ne $before[[string]$port]) { throw "protected port $port changed during deployment" }
    }
    [ordered]@{
        ok = $true
        operation = 'OPS-8093-DIAGNOSIS-CORE19-MOUNT-R9-20260806'
        guardPaused = $guardPaused
        guardRestored = $guardRestored
        backup = $backupRoot
        http8093 = [int]$page.StatusCode
        assetVersion = '20260806-core19-r9'
        coreVariableCount = [int]$core.evidence.core_variable_count
        coreSeriesCount = $seriesCount
        protectedPidsUnchanged = $true
        deployedFiles = @($payloads | ForEach-Object { [ordered]@{ path = $_.target; sha256 = (Get-FileHash -LiteralPath $_.target -Algorithm SHA256).Hash } })
    } | ConvertTo-Json -Depth 6
}
catch {
    Invoke-Manager 'stop'
    Wait-Port 8093 $false 30
    foreach ($entry in $manifest) { Copy-Item -LiteralPath $entry.backup -Destination $entry.target -Force }
    Invoke-Manager 'start'
    Wait-Port 8093 $true 120
    throw "r9 mount deployment rolled back: $($_.Exception.Message)"
}
